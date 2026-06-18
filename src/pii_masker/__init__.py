"""PII Masker Pro — local, multilingual PII anonymization.

Public API:
    >>> from pii_masker import PIIMasker
    >>> masker = PIIMasker()
    >>> masker.mask("Scrivi a mario.rossi@gmail.com", language="it")
    'Scrivi a [EMAIL]'
"""

from .masker import PIIMasker, MaskResult
from .config import MaskConfig, DEFAULT_ENTITIES, PLACEHOLDERS

__all__ = [
    "PIIMasker",
    "MaskResult",
    "MaskConfig",
    "DEFAULT_ENTITIES",
    "PLACEHOLDERS",
]

__version__ = "0.1.0"
