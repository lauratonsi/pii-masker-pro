# PII Masker Pro

Local, multilingual anonymization of Personally Identifiable Information (PII).
Built on [Microsoft Presidio](https://microsoft.github.io/presidio/) with custom
**checksum-validated** Italian recognizers. Everything runs on-premise — no data
ever leaves the machine.

## Why

Detecting PII with plain regular expressions produces a flood of false positives
(any 16-character string "looks like" a fiscal code). This tool combines:

1. **Deterministic recognizers with real validation** — a Codice Fiscale is
   masked only if its *control character* is correct, a Partita IVA only if its
   *check digit* is correct, a credit card only if it passes *Luhn*. Structural
   lookalikes are left untouched.
2. **NER (spaCy)** for names, via Presidio's analyzer.
3. **A deliberate business rule**: people are masked, but **locations and
   organizations are kept**, so the geographic and commercial value of the data
   is preserved.

## What it detects

| Entity              | Placeholder      | Validation                |
|---------------------|------------------|---------------------------|
| Person (NER)        | `[PERSON]`       | spaCy NER                 |
| Email               | `[EMAIL]`        | regex                     |
| Phone               | `[PHONE]`        | `phonenumbers`            |
| Credit card         | `[CREDIT_CARD]`  | Luhn                      |
| IBAN                | `[IBAN]`         | Presidio IBAN check       |
| IP address          | `[IP]`           | regex                     |
| Codice Fiscale (IT) | `[FISCAL_CODE]`  | **control character**     |
| Partita IVA (IT)    | `[VAT]`          | **check digit**           |
| Vehicle plate (IT)  | `[PLATE]`        | format (no checksum)      |

Languages: **Italian** and **English** (spaCy `it_core_news_lg` / `en_core_web_lg`).

## Install

```bash
conda create -n pii-masker python=3.11 -y
conda activate pii-masker
pip install -e .
python -m spacy download it_core_news_lg
python -m spacy download en_core_web_lg
```

## CLI

```bash
# Inline text
pii-masker "Scrivi a mario.rossi@gmail.com"          # -> Scrivi a [EMAIL]

# From a file, to a file
pii-masker -f notes.txt -o clean.txt

# From stdin
cat notes.txt | pii-masker --lang it

# English
pii-masker "Call John at john@acme.com" --lang en

# See what was detected (JSON on stderr)
pii-masker -f notes.txt --report

# Reversible masking for LLM round-trips (unique tokens + restore map)
pii-masker -f notes.txt --reversible --map-out map.json
```

## Library

```python
from pii_masker import PIIMasker

masker = PIIMasker()                       # loads the models once; reuse it
masker.mask("Scrivi a mario.rossi@gmail.com", language="it")
# 'Scrivi a [EMAIL]'

# Round-trip through an external LLM and back
r = masker.mask_reversible("Contatta Mario Rossi: mario@x.it")
r.text                                     # '<PERSON_0>: <EMAIL_ADDRESS_0>'
# ... send r.text to an LLM, then:
r.restore(llm_response)                    # originals reinserted
```

## Testing

```bash
pytest
```

The suite covers positive detections, **negative controls** (locations and
organizations must stay intact), checksum validation (a fiscal code with a wrong
control character is *not* masked), idempotence, reversibility and the
trailing-newline span-conflict regression.

## Recall helpers

- **Italian phone numbers** are detected with or without an international prefix
  (`+39 329 1234567` and a bare `3291234567` both work).
- **Names spaCy misses** are recovered from context: a name after an honorific
  ("Avv. Bianchi", "Sig.ra Rossi") or after a communication verb
  ("Chiama Mario Rossi"). To avoid false positives, the verb rule only fires on a
  full first-plus-last name, so "Scrivi a Milano" / "Contatta Vodafone" stay intact.

## Known limitations

- **NER recall is not perfect.** Detection is best-effort, not a guarantee; treat
  the output as a strong filter, not a compliance certificate.
- A name after a verb that is a real person but written as a single token
  (e.g. only a first name) may still be missed.
- Locations/organizations are intentionally **not** masked.

## License

MIT.
