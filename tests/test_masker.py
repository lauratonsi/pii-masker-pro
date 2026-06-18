"""End-to-end tests for the masker. These load the spaCy models once."""

import pytest

from pii_masker import PIIMasker, MaskConfig


@pytest.fixture(scope="module")
def masker() -> PIIMasker:
    return PIIMasker()


class TestDeterministic:
    def test_email(self, masker):
        assert masker.mask("Scrivi a mario.rossi@gmail.com per info.") == \
            "Scrivi a [EMAIL] per info."

    def test_phone(self, masker):
        assert masker.mask("Chiamami al +39 329 1234567.").count("[PHONE]") == 1

    def test_phone_without_prefix(self, masker):
        # Bare Italian number, no international prefix.
        assert "[PHONE]" in masker.mask("Chiamami al 3291234567 grazie.")

    def test_fiscal_code_valid(self, masker):
        assert masker.mask("CF: RSSMRA80A01H501U") == "CF: [FISCAL_CODE]"

    def test_fiscal_code_invalid_is_left_alone(self, masker):
        # Wrong control char -> not a real fiscal code -> must NOT be masked.
        out = masker.mask("CF: RSSMRA80A01H501W")
        assert "[FISCAL_CODE]" not in out

    def test_vat(self, masker):
        out = masker.mask("Partita IVA 00743110157")
        assert "[VAT]" in out

    def test_credit_card(self, masker):
        out = masker.mask("Carta 4111 1111 1111 1111")
        assert "[CREDIT_CARD]" in out


class TestPerson:
    def test_person_masked(self, masker):
        assert masker.mask("Ho parlato con Mario Rossi ieri.") == \
            "Ho parlato con [PERSON] ieri."


class TestPersonRecall:
    """Names spaCy alone tends to miss, recovered via context."""

    def test_name_after_communication_verb(self, masker):
        # spaCy mislabels the sentence-initial verb+name span; context recovers it.
        assert masker.mask("Chiama Mario Rossi domani.") == "Chiama [PERSON] domani."

    def test_name_after_title(self, masker):
        out = masker.mask("Gentile Sig.ra Anna Del Monte, la contatto.")
        assert "[PERSON]" in out
        assert "Anna" not in out and "Monte" not in out

    def test_verb_does_not_mask_single_token_place(self, masker):
        # "Scrivi a Milano" must NOT mask Milano (single token -> not a person).
        out = masker.mask("Scrivi a Milano per informazioni.")
        assert "Milano" in out
        assert "[PERSON]" not in out

    def test_verb_does_not_mask_single_token_org(self, masker):
        out = masker.mask("Contatta Vodafone per assistenza.")
        assert "Vodafone" in out


class TestNegativeControls:
    """Business value: locations and organizations must stay intact."""

    def test_location_not_masked(self, masker):
        out = masker.mask("L'azienda ha sede a Milano.")
        assert "Milano" in out
        assert "[" not in out

    def test_org_with_email(self, masker):
        out = masker.mask("Comune di Roma: tel +39 06 0606")
        assert "Roma" in out  # org/loc preserved
        assert "[PHONE]" in out  # phone still masked


class TestSpanRobustness:
    def test_trailing_newline_does_not_swallow_fiscal_code(self, masker):
        # Regression: a PERSON span extended over the trailing newline used to
        # win conflict resolution against the checksum-valid fiscal code.
        out = masker.mask("CF RSSMRA80A01H501U\n")
        assert "[FISCAL_CODE]" in out

    def test_person_span_does_not_cross_newline(self, masker):
        # Regression: spaCy tagged "RSSMRA80A01H501U\n- Partita" as one PERSON,
        # swallowing the fiscal code and the next line's first word.
        out = masker.mask("Codice Fiscale: RSSMRA80A01H501U\n- Partita IVA: 00743110157")
        assert "[FISCAL_CODE]" in out
        assert "[VAT]" in out
        assert "Partita" in out  # the next line must stay intact


class TestIdempotence:
    def test_double_masking_is_stable(self, masker):
        once = masker.mask("Scrivi a mario.rossi@gmail.com")
        twice = masker.mask(once)
        assert once == twice


class TestReversible:
    def test_round_trip_restores_original(self, masker):
        text = "Scrivi a mario.rossi@gmail.com o chiama Mario Rossi."
        result = masker.mask_reversible(text)
        assert "mario.rossi@gmail.com" not in result.text
        assert result.restore(result.text) == text

    def test_distinct_values_get_distinct_tokens(self, masker):
        text = "Mail a a@b.it e c@d.it"
        result = masker.mask_reversible(text)
        assert len(result.mapping) == 2


class TestMultilingual:
    def test_english(self, masker):
        cfg = MaskConfig(language="en")
        out = masker.mask("Please write to john.doe@example.com", language="en", config=cfg)
        assert "[EMAIL]" in out
        assert "john.doe@example.com" not in out
