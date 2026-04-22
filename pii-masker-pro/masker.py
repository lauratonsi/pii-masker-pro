from __future__ import annotations

import re
import argparse
from dataclasses import dataclass
from typing import Callable, Optional

import spacy

@dataclass(frozen=True)
class TestCase:
    id: str
    category: str
    text: str
    expected: Optional[str] = None
    extra_checks: tuple[Callable[[str, str, 'PIIMasker'], Optional[str]], ...] = ()

class PIIMasker:
    def __init__(self):
        # 1. Regex per dati deterministici
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        )
        self.phone_pattern = re.compile(
            r"(?<!\w)\+?(?:\(\d{2,4}\)[ .-]?)?\d(?:[ .-]?\d){6,14}(?!\w)"
        )
        self.fiscal_code_pattern = re.compile(
            r"(?<!\w)[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z](?!\w)",
            re.IGNORECASE,
        )
        # Protezione per i log temporali (evita che vengano scambiati per telefoni)
        self._timestamp_re = re.compile(
            r"\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\]"
        )

        # 2. Modello NLP per i dati probabilistici (Nomi Propri)
        try:
            self.nlp = spacy.load("it_core_news_lg")
        except OSError:
            raise RuntimeError(
                "Modello spaCy 'it_core_news_lg' non trovato. "
                "Installalo con: python -m spacy download it_core_news_lg"
            )

    def mask(self, text: str) -> str:
        # Step A: Proteggi i timestamp estraendoli temporaneamente
        ts_map: dict[str, str] = {}
        def _protect_ts(m: re.Match) -> str:
            tok = f"PII_TIME_TOKEN_{len(ts_map)}"
            ts_map[tok] = m.group(0)
            return tok

        protected = self._timestamp_re.sub(_protect_ts, text)

        # Step B: Mascheramento deterministico (RegEx)
        masked = self.email_pattern.sub("[EMAIL]", protected)
        masked = self.phone_pattern.sub("[PHONE]", masked)
        masked = self.fiscal_code_pattern.sub("[FISCAL_CODE]", masked)

        # Step C: Mascheramento probabilistico (NLP)
        masked = self.mask_entities(masked)

        # Step D: Ripristina i timestamp
        for tok, original in ts_map.items():
            masked = masked.replace(tok, original)
            
        return masked

    def mask_entities(self, text: str) -> str:
        """
        Usa spaCy per individuare SOLO le persone (PER). 
        LA REGOLA DI BUSINESS: Ignora luoghi (LOC) e organizzazioni (ORG) 
        per preservare il valore geografico e aziendale del database.
        """
        doc = self.nlp(text)
        
        # Filtro restrittivo: solo entità classificate con certezza come PERSONE
        target_entities = [ent for ent in doc.ents if ent.label_ == "PER"]
        
        if not target_entities:
            return text
            
        new_text = text
        # Sostituzione da destra a sinistra per non corrompere gli indici della stringa
        for ent in sorted(target_entities, key=lambda e: e.start_char, reverse=True):
            new_text = new_text[:ent.start_char] + "[PERSON]" + new_text[ent.end_char:]
            
        return new_text


# --- SEZIONE DI TESTING (GOVERNANCE-DRIVEN) ---

TEST_CASES: list[TestCase] = [
    # A) Persone
    TestCase("A01", "person", "Ho parlato con Mario Rossi ieri.", "Ho parlato con [PERSON] ieri."),
    TestCase("A02", "person", "L’avv. Giuseppe Bianchi ha chiamato.", "L’avv. [PERSON] ha chiamato."),
    
    # D) Email e Telefoni
    TestCase("D01", "email", "Scrivi a mario.rossi@gmail.com per info.", "Scrivi a [EMAIL] per info."),
    TestCase("E01", "phone", "Chiamami al +39 329 1234567.", "Chiamami al [PHONE]."),
    
    # F) Codice Fiscale
    TestCase("F01", "fiscal_code", "CF: RSSMRA80A01H501W", "CF: [FISCAL_CODE]"),
    
    # L) Log complessi con Timestamp
    TestCase("L01", "log", "[2026-04-21 10:22] Cliente: Anna Del Monte", "[2026-04-21 10:22] Cliente: [PERSON]"),

    # H) I CONTROLLI NEGATIVI: Il vero valore del business (NON mascherare)
    TestCase("H01", "org_loc", "L'azienda Verdi S.p.A. ha sede a Milano.", "L'azienda Verdi S.p.A. ha sede a Milano."),
    TestCase("H02", "org_loc", "Università di Milano: segreteria@unimi.it", "Università di Milano: [EMAIL]"),
    TestCase("H03", "org_loc", "Comune di Roma: tel +39 06 0606", "Comune di Roma: tel [PHONE]"),
    TestCase("H04", "org_loc", "Via Giuseppe Verdi 10, Milano", "Via [PERSON] 10, Milano"), 
]

def run_pii_masking_tests(masker: PIIMasker) -> int:
    passed = 0
    failures = 0

    print("\n=== AVVIO TEST DI GOVERNANCE PII MASKING ===\n")
    for tc in TEST_CASES:
        output = masker.mask(tc.text)
        if tc.expected is not None and output != tc.expected:
            failures += 1
            print(f"❌ FAIL | TEST {tc.id} ({tc.category})")
            print(f"   Input:    {tc.text}")
            print(f"   Output:   {output}")
            print(f"   Expected: {tc.expected}\n")
        else:
            passed += 1
            print(f"✅ PASS | TEST {tc.id} ({tc.category})")

    print(f"\nRisultato Finale: {passed} / {len(TEST_CASES)} test superati.")
    return 0 if failures == 0 else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PII Masker Validation")
    args = parser.parse_args()

    masker = PIIMasker()
    raise SystemExit(run_pii_masking_tests(masker))