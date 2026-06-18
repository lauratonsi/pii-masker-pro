"""Unit tests for the Italian checksum validators (no model loading needed)."""

from pii_masker.recognizers.italian import (
    is_valid_fiscal_code,
    is_valid_vat,
)


class TestFiscalCode:
    def test_valid(self):
        assert is_valid_fiscal_code("RSSMRA80A01H501U")
        assert is_valid_fiscal_code("rssmra80a01h501u")  # case-insensitive

    def test_wrong_control_char(self):
        # Structurally a fiscal code, but the control character is wrong.
        # (This is the value the original tool wrongly accepted.)
        assert not is_valid_fiscal_code("RSSMRA80A01H501W")

    def test_wrong_length(self):
        assert not is_valid_fiscal_code("RSSMRA80A01H501")
        assert not is_valid_fiscal_code("")


class TestVat:
    def test_valid(self):
        assert is_valid_vat("00743110157")  # known-valid example
        assert is_valid_vat("IT00743110157")  # tolerates IT prefix

    def test_invalid_checkdigit(self):
        assert not is_valid_vat("00743110158")

    def test_wrong_length(self):
        assert not is_valid_vat("1234567890")
