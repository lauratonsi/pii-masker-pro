"""Italian-specific PII recognizers.

Each recognizer matches a structural pattern *and* validates it with the real
control algorithm (checksum / control character). This is the key difference
from naive regex masking: ``RSSMRA80A01H501W`` is masked because its control
character is correct, while a random 16-char lookalike is rejected, so we avoid
the flood of false positives the original tool produced.
"""

from __future__ import annotations

import re
from typing import Optional

from presidio_analyzer import (
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerResult,
)

from ..config import IT_FISCAL_CODE, IT_VAT_NUMBER, IT_VEHICLE_PLATE


# --------------------------------------------------------------------------- #
# Codice Fiscale
# --------------------------------------------------------------------------- #

_CF_ODD = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17,
    "8": 19, "9": 21, "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13,
    "G": 15, "H": 17, "I": 19, "J": 21, "K": 2, "L": 4, "M": 18, "N": 20,
    "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14, "U": 16, "V": 10,
    "W": 22, "X": 25, "Y": 24, "Z": 23,
}
_CF_EVEN = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5,
    "G": 6, "H": 7, "I": 8, "J": 9, "K": 10, "L": 11, "M": 12, "N": 13,
    "O": 14, "P": 15, "Q": 16, "R": 17, "S": 18, "T": 19, "U": 20, "V": 21,
    "W": 22, "X": 23, "Y": 24, "Z": 25,
}


def is_valid_fiscal_code(code: str) -> bool:
    """Validate an Italian Codice Fiscale via its control character."""
    code = code.strip().upper()
    if len(code) != 16 or not code.isalnum():
        return False
    total = 0
    for i, char in enumerate(code[:15]):
        table = _CF_ODD if i % 2 == 0 else _CF_EVEN  # 1-based odd == index 0,2,4...
        if char not in table:
            return False
        total += table[char]
    expected = chr(ord("A") + total % 26)
    return expected == code[15]


class ItalianFiscalCodeRecognizer(PatternRecognizer):
    """Codice Fiscale (16 chars) validated by its control character."""

    # Digit positions may carry omocodia letters (L M N P Q R S T U V).
    PATTERNS = [
        Pattern(
            name="codice_fiscale",
            regex=r"\b[A-Za-z]{6}[0-9LMNPQRSTUVlmnpqrstuv]{2}[A-Za-z]"
            r"[0-9LMNPQRSTUVlmnpqrstuv]{2}[A-Za-z][0-9LMNPQRSTUVlmnpqrstuv]{3}[A-Za-z]\b",
            score=0.4,
        )
    ]
    # No context words on purpose: the control character is authoritative, so a
    # nearby "CF:" must not rescue a code that fails the checksum.

    def __init__(self) -> None:
        super().__init__(
            supported_entity=IT_FISCAL_CODE,
            patterns=self.PATTERNS,
            supported_language="it",
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return is_valid_fiscal_code(pattern_text)


# --------------------------------------------------------------------------- #
# Partita IVA (VAT number)
# --------------------------------------------------------------------------- #

def is_valid_vat(number: str) -> bool:
    """Validate an 11-digit Italian Partita IVA (Luhn-style check digit)."""
    digits = "".join(ch for ch in number if ch.isdigit())
    if len(digits) != 11:
        return False
    total = 0
    for i, ch in enumerate(digits[:10]):
        d = int(ch)
        if i % 2 == 1:  # even position (1-based) -> double
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - total % 10) % 10
    return check == int(digits[10])


class ItalianVatRecognizer(PatternRecognizer):
    """Partita IVA (11 digits) validated by its check digit."""

    PATTERNS = [
        Pattern(
            name="partita_iva",
            regex=r"\b(?:IT)?\d{11}\b",
            score=0.3,
        )
    ]
    # No context words: the check digit is authoritative (see fiscal code above).

    def __init__(self) -> None:
        super().__init__(
            supported_entity=IT_VAT_NUMBER,
            patterns=self.PATTERNS,
            supported_language="it",
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return is_valid_vat(pattern_text)


# --------------------------------------------------------------------------- #
# Vehicle plate (no checksum exists; format only)
# --------------------------------------------------------------------------- #

class ItalianVehiclePlateRecognizer(PatternRecognizer):
    """Italian car plate (post-1994 format AA000AA). No checksum exists."""

    PATTERNS = [
        Pattern(
            name="targa",
            regex=r"\b[A-Za-z]{2}\s?\d{3}\s?[A-Za-z]{2}\b",
            score=0.4,
        )
    ]
    CONTEXT = ["targa", "veicolo", "auto", "plate"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity=IT_VEHICLE_PLATE,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="it",
        )


# --------------------------------------------------------------------------- #
# Person names by context (boosts NER recall, high precision)
# --------------------------------------------------------------------------- #

# Capitalized name tokens, tolerating nobiliary particles (Del, Di, van, ...).
_NAME_TAIL = r"(?:[A-ZÀ-Þ][a-zà-ÿ']+|del|della|dei|degli|de|di|da|van|von|la|lo)"
# 1-to-3 tokens: used after an honorific (high precision, single surname is fine).
_NAME = rf"[A-ZÀ-Þ][a-zà-ÿ']+(?:\s+{_NAME_TAIL}){{0,2}}"
# 2-to-3 tokens (first + last at least): used after a verb, where a single
# capitalized token is far more likely to be a city/company than a person.
_NAME_MULTI = rf"[A-ZÀ-Þ][a-zà-ÿ']+(?:\s+{_NAME_TAIL}){{1,2}}"

# Honorifics / titles -> the following name is almost certainly a person.
_TITLES = (
    r"Sig\.ra|Sig\.|Sigg\.|Sig|Signora|Signor|Dott\.ssa|Dott\.|Dott|Dr\.|Dr|"
    r"Avv\.|Avv|Ing\.|Ing|Prof\.ssa|Prof\.|Prof|Geom\.|Rag\.|Cav\.|On\.|"
    r"Gentile|Egregi[oa]|Egr\.|Spett\.le|Car[oa]|Car[ie]ssim[oa]"
)

# Communication verbs -> the following capitalized token(s) are usually a person.
_VERBS = (
    r"chiama(?:to|re|mi|lo|la)?|contatta(?:re|to|mi|lo|la)?|telefona(?:re|to)?\s+a|"
    r"scriv[io](?:mi)?\s+a|parla(?:re|to)?\s+con|convoca(?:re|to)?|avvisa(?:re|to)?|"
    r"incontra(?:re|to)?|ringrazia(?:re|to)?|sentito|cerca(?:re)?"
)

# Case-insensitivity is scoped to the trigger only (?i:...); the name part stays
# case-sensitive so it must be genuinely capitalized (Titlecase), otherwise a
# verb would greedily swallow following lowercase words.
# Titles also allow one optional stacked title ("Gentile Sig.ra Anna ...").
_TITLE_RE = re.compile(
    rf"(?i:{_TITLES})\s+(?:(?i:{_TITLES})\s+)?(?P<name>{_NAME})"
)
_VERB_RE = re.compile(rf"(?i:{_VERBS})\s+(?P<name>{_NAME_MULTI})")


class ItalianPersonContextRecognizer(EntityRecognizer):
    """Detect person names that spaCy misses, using surrounding context.

    Two high-precision signals:

    * an honorific / title right before the name ("Avv. Bianchi", "Sig.ra Rossi");
    * a communication verb right before the name ("Chiama Mario Rossi") — this
      is exactly the sentence-initial case where spaCy mislabels the span.

    Only the name itself is masked, never the title or the verb. Titles score
    higher than verbs because they are less ambiguous.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="it",
            name="ItalianPersonContextRecognizer",
        )

    def load(self) -> None:  # required by EntityRecognizer
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        if "PERSON" not in entities:
            return []
        results: list[RecognizerResult] = []
        for regex, score in ((_TITLE_RE, 0.8), (_VERB_RE, 0.6)):
            for m in regex.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=m.start("name"),
                        end=m.end("name"),
                        score=score,
                        analysis_explanation=None,
                        recognition_metadata={
                            RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                            RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                        },
                    )
                )
        return results


def italian_recognizers() -> list[EntityRecognizer]:
    """All Italian recognizers, ready to register with the analyzer."""
    return [
        ItalianFiscalCodeRecognizer(),
        ItalianVatRecognizer(),
        ItalianVehiclePlateRecognizer(),
        ItalianPersonContextRecognizer(),
    ]
