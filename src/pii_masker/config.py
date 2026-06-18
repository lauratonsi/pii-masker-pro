"""Configuration: which entities are masked and how they are rendered.

Business rule (inherited from the original tool and kept on purpose):
LOCATION and ORGANIZATION are *not* masked by default, so the analytical and
geographic value of the data is preserved. Only personally identifying data is
removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Custom Italian entity labels (must match the recognizers in recognizers/italian.py)
IT_FISCAL_CODE = "IT_FISCAL_CODE"
IT_VAT_NUMBER = "IT_VAT_NUMBER"
IT_VEHICLE_PLATE = "IT_VEHICLE_PLATE"

# Placeholder shown in the anonymized output for each entity type.
PLACEHOLDERS: dict[str, str] = {
    "PERSON": "[PERSON]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "PHONE_NUMBER": "[PHONE]",
    "CREDIT_CARD": "[CREDIT_CARD]",
    "IBAN_CODE": "[IBAN]",
    "IP_ADDRESS": "[IP]",
    IT_FISCAL_CODE: "[FISCAL_CODE]",
    IT_VAT_NUMBER: "[VAT]",
    IT_VEHICLE_PLATE: "[PLATE]",
}

# Entities masked unless the caller overrides the selection.
# Deliberately excludes LOCATION / ORGANIZATION / NRP / DATE_TIME / URL.
DEFAULT_ENTITIES: tuple[str, ...] = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    IT_FISCAL_CODE,
    IT_VAT_NUMBER,
    IT_VEHICLE_PLATE,
)

SUPPORTED_LANGUAGES: tuple[str, ...] = ("it", "en")

# spaCy models loaded per language. Large models give the best NER recall.
SPACY_MODELS: dict[str, str] = {
    "it": "it_core_news_lg",
    "en": "en_core_web_lg",
}


@dataclass
class MaskConfig:
    """Runtime knobs for a masking session."""

    language: str = "it"
    entities: tuple[str, ...] = field(default=DEFAULT_ENTITIES)
    # Below this confidence a detection is ignored. Custom recognizers that
    # pass a checksum report 1.0 and are unaffected.
    score_threshold: float = 0.35
    placeholders: dict[str, str] = field(default_factory=lambda: dict(PLACEHOLDERS))

    def placeholder_for(self, entity_type: str) -> str:
        return self.placeholders.get(entity_type, f"[{entity_type}]")
