**PII Masker Pro: Governance-by-Design for AI Readiness**

📌 Visione Strategica

In un panorama aziendale dominato dall'integrazione di LLM (Large Language Models) e workflow agentici, la protezione dei dati sensibili non può essere delegata esclusivamente a modelli probabilistici cloud-based. 
PII Masker Pro è un framework di anonimizzazione locale progettato secondo i principi della Governance-by-Design. Il tool funge da "filtro di sicurezza" on-premise, ripulendo i dati dai PII (Personally Identifiable Information) prima che lascino il perimetro aziendale, garantendo la compliance al GDPR e riducendo il rischio di data leak.

**🛠️ Architettura Tecnica: Approccio Ibrido**
Il sistema supera i limiti dei singoli approcci utilizzando una pipeline a due stadi:
1. Stadio Deterministico (RegEx): Identificazione ad alta precisione di pattern strutturati come Email, Numeri di Telefono e Codice Fiscale Italiano.
2. Stadio Probabilistico (NLP): Utilizzo di spaCy (modello it_core_news_lg) per il Named Entity Recognition (NER). A differenza di approcci standard, il sistema è configurato per mascherare selettivamente solo le entità di tipo PER (Persone), preservando LOC (Luoghi) e ORG (Organizzazioni) per non distruggere il valore analitico e geografico del dato per il business.

**🚀 Caratteristiche Principali**
- Timestamp Protection: Algoritmo di tokenizzazione temporanea per proteggere i log temporali da falsi positivi.
- Business Context Preservation: Evita l'over-masking tipico degli agenti AI, mantenendo intatti i riferimenti a città e aziende.
- Idempotenza: Garantita dalla suite di test; processare più volte lo stesso testo non corrompe i placeholder.
- Zero Cloud Leak: Elaborazione interamente locale tramite Miniconda e modelli spaCy scaricati on-premise.

**🚦 Testing & Quality Assurance**
Il progetto include una suite di test rigorosa (test.py) basata su unittest che verifica:
- Correttezza delle RegEx.
- Capacità di astrazione del modello NER.
- Negative Controls: Verifica che le entità geografiche e aziendali NON vengano mascherate erroneamente.

```bash
# Per eseguire i test di validazione
python test.py
```

**💻 Requisiti e Installazione**
- Ambiente: Python 3.11+ (consigliato Miniconda).
- Dipendenze: pip install spacy.
- Modello Linguistico: python -m spacy download it_core_news_lg.
