"""Core masking engine built on Microsoft Presidio.

The :class:`PIIMasker` wraps a multilingual Presidio analyzer (spaCy NER + our
validated Italian recognizers) and an anonymizer. It exposes three things:

* :meth:`analyze`  -> raw detections (entity type, span, score)
* :meth:`mask`     -> text with stable placeholders ([PERSON], [EMAIL], ...)
* :meth:`mask_reversible` -> text with unique tokens + a map to restore them,
  for round-tripping data through an external LLM and back.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Sequence

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from .config import (
    DEFAULT_ENTITIES,
    MaskConfig,
    SPACY_MODELS,
    SUPPORTED_LANGUAGES,
)
from .recognizers import italian_recognizers


@dataclass
class MaskResult:
    """Outcome of a masking call."""

    text: str
    entities: list[dict] = field(default_factory=list)
    # token -> original value (populated only by reversible masking)
    mapping: dict[str, str] = field(default_factory=dict)

    def restore(self, text: str) -> str:
        """Reinsert the original values into ``text`` (de-anonymization)."""
        for token, original in self.mapping.items():
            text = text.replace(token, original)
        return text


def _build_analyzer(languages: Sequence[str]) -> AnalyzerEngine:
    models = [
        {"lang_code": lang, "model_name": SPACY_MODELS[lang]} for lang in languages
    ]
    provider = NlpEngineProvider(
        nlp_configuration={"nlp_engine_name": "spacy", "models": models}
    )
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry(supported_languages=list(languages))
    registry.load_predefined_recognizers(
        languages=list(languages), nlp_engine=nlp_engine
    )
    # Presidio ships unvalidated Italian recognizers (plain regex, no checksum)
    # that collide with ours. Drop them so only our checksum-validated versions
    # decide what is a real Codice Fiscale / Partita IVA.
    for name in ("ItFiscalCodeRecognizer", "ItVatCodeRecognizer"):
        try:
            registry.remove_recognizer(name)
        except Exception:
            pass

    # The default PhoneRecognizer regions don't include Italy, so a bare Italian
    # number ("3291234567") is missed. Replace it with one that knows IT (plus
    # common regions) for every loaded language.
    try:
        registry.remove_recognizer("PhoneRecognizer")
    except Exception:
        pass
    phone_regions = ("IT", "US", "GB", "DE", "FR", "ES")
    for lang in languages:
        registry.add_recognizer(
            PhoneRecognizer(supported_language=lang, supported_regions=phone_regions)
        )

    for recognizer in italian_recognizers():
        registry.add_recognizer(recognizer)

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=list(languages),
    )


class PIIMasker:
    """Local, multilingual PII masker.

    Loading the spaCy models is expensive, so build one instance and reuse it.
    """

    def __init__(self, languages: Sequence[str] = SUPPORTED_LANGUAGES) -> None:
        unsupported = [l for l in languages if l not in SPACY_MODELS]
        if unsupported:
            raise ValueError(f"Unsupported language(s): {unsupported}")
        self.languages = tuple(languages)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.analyzer = _build_analyzer(self.languages)
        self.anonymizer = AnonymizerEngine()

    # -- detection ------------------------------------------------------- #

    def analyze(
        self, text: str, config: Optional[MaskConfig] = None
    ) -> list[RecognizerResult]:
        cfg = config or MaskConfig(language=self.languages[0])
        if cfg.language not in self.languages:
            raise ValueError(
                f"Language '{cfg.language}' not loaded. Available: {self.languages}"
            )
        results = self.analyzer.analyze(
            text=text,
            language=cfg.language,
            entities=list(cfg.entities),
            score_threshold=cfg.score_threshold,
        )
        return self._trim_spans(text, results)

    @staticmethod
    def _trim_spans(
        text: str, results: list[RecognizerResult]
    ) -> list[RecognizerResult]:
        """Normalize span edges so the right detection wins on overlap.

        spaCy sometimes stretches a PERSON entity across a line break, e.g. it
        tags ``"RSSMRA80A01H501U\\n- Partita"`` as one PERSON. That oversized
        span *contains* the checksum-valid fiscal code and would beat it during
        conflict resolution (longer span wins). We therefore:

        1. cut every span at the first internal newline (real names / PII never
           span lines), and
        2. strip surrounding whitespace.

        After this, the spurious PERSON span aligns with the fiscal code span,
        and the higher score (the validated code) wins. Empty spans are dropped.
        """
        cleaned: list[RecognizerResult] = []
        for r in results:
            newline = text.find("\n", r.start, r.end)
            if newline != -1:
                r.end = newline
            while r.start < r.end and text[r.start].isspace():
                r.start += 1
            while r.end > r.start and text[r.end - 1].isspace():
                r.end -= 1
            if r.start < r.end:
                cleaned.append(r)
        return cleaned

    # -- static masking (stable placeholders) ---------------------------- #

    def mask(
        self,
        text: str,
        language: str = "it",
        config: Optional[MaskConfig] = None,
    ) -> str:
        """Return ``text`` with PII replaced by stable placeholders."""
        return self.mask_detailed(text, language=language, config=config).text

    def mask_detailed(
        self,
        text: str,
        language: str = "it",
        config: Optional[MaskConfig] = None,
    ) -> MaskResult:
        cfg = config or MaskConfig(language=language)
        results = self.analyze(text, cfg)
        operators = {
            entity: OperatorConfig(
                "replace", {"new_value": cfg.placeholder_for(entity)}
            )
            for entity in cfg.entities
        }
        operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
        anonymized = self.anonymizer.anonymize(
            text=text, analyzer_results=results, operators=operators
        )
        entities = [
            {
                "entity_type": item.entity_type,
                "start": item.start,
                "end": item.end,
            }
            for item in anonymized.items
        ]
        return MaskResult(text=anonymized.text, entities=entities)

    # -- reversible masking (LLM round-trip) ----------------------------- #

    def mask_reversible(
        self,
        text: str,
        language: str = "it",
        config: Optional[MaskConfig] = None,
    ) -> MaskResult:
        """Mask with unique tokens and return a mapping to restore the originals.

        Each detection becomes ``<ENTITY_n>`` so distinct values never collide,
        which makes the operation losslessly reversible via :meth:`MaskResult.restore`.
        """
        cfg = config or MaskConfig(language=language)
        results = self.analyze(text, cfg)
        # Replace right-to-left so earlier character offsets stay valid.
        ordered = sorted(results, key=lambda r: r.start, reverse=True)
        counters: dict[str, int] = {}
        mapping: dict[str, str] = {}
        entities: list[dict] = []
        out = text
        for res in ordered:
            original = text[res.start : res.end]
            idx = counters.get(res.entity_type, 0)
            counters[res.entity_type] = idx + 1
            token = f"<{res.entity_type}_{idx}>"
            mapping[token] = original
            out = out[: res.start] + token + out[res.end :]
            entities.append(
                {
                    "entity_type": res.entity_type,
                    "start": res.start,
                    "end": res.end,
                    "token": token,
                }
            )
        entities.reverse()
        return MaskResult(text=out, entities=entities, mapping=mapping)


@lru_cache(maxsize=2)
def get_masker(languages: tuple[str, ...] = SUPPORTED_LANGUAGES) -> PIIMasker:
    """Cached masker so repeated CLI/library calls don't reload the models."""
    return PIIMasker(languages)
