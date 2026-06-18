"""Custom Italian PII recognizers with checksum validation."""

from .italian import (
    ItalianFiscalCodeRecognizer,
    ItalianVatRecognizer,
    ItalianVehiclePlateRecognizer,
    italian_recognizers,
)

__all__ = [
    "ItalianFiscalCodeRecognizer",
    "ItalianVatRecognizer",
    "ItalianVehiclePlateRecognizer",
    "italian_recognizers",
]
