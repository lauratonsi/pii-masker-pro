"""Streamlit front-end for PII Masker Pro.

A dead-simple local web UI: paste text or drop a file, press one button, get the
anonymized result back. Everything runs on localhost — no data leaves the machine.

Run it with:
    streamlit run app.py
(or double-click the avvia.command / avvia.bat launcher).
"""

from __future__ import annotations

import json
from collections import Counter

import streamlit as st

from pii_masker import PIIMasker, MaskConfig

# Friendly Italian labels for the detection summary.
_LABELS = {
    "PERSON": "persona",
    "EMAIL_ADDRESS": "email",
    "PHONE_NUMBER": "telefono",
    "CREDIT_CARD": "carta",
    "IBAN_CODE": "IBAN",
    "IP_ADDRESS": "indirizzo IP",
    "IT_FISCAL_CODE": "codice fiscale",
    "IT_VAT_NUMBER": "partita IVA",
    "IT_VEHICLE_PLATE": "targa",
}
_LANGS = {"Italiano": "it", "English": "en"}


@st.cache_resource(show_spinner="Carico il modello (solo la prima volta)…")
def load_masker() -> PIIMasker:
    return PIIMasker()


def summarize(entities: list[dict]) -> str:
    counts = Counter(e["entity_type"] for e in entities)
    if not counts:
        return "Nessun dato personale trovato."
    parts = [f"{n} {_LABELS.get(t, t)}" for t, n in counts.items()]
    return "Trovati: " + " · ".join(parts)


def main() -> None:
    st.set_page_config(page_title="PII Masker Pro", page_icon="🛡️", layout="centered")
    st.title("🛡️ PII Masker Pro")
    st.caption("Rimuove i dati personali dal testo. Tutto in locale: niente cloud.")

    col1, col2 = st.columns([3, 2])
    with col1:
        lang_label = st.selectbox("Lingua del testo", list(_LANGS))
    with col2:
        reversible = st.toggle(
            "Modalità reversibile",
            help="Usa token unici e permette di ricostruire l'originale "
            "(utile per i round-trip con un'AI).",
        )
    language = _LANGS[lang_label]

    uploaded = st.file_uploader("Trascina un file di testo (opzionale)", type=["txt", "csv", "md", "log"])
    default_text = ""
    if uploaded is not None:
        default_text = uploaded.read().decode("utf-8", errors="replace")

    text = st.text_area(
        "Oppure incolla qui il testo",
        value=default_text,
        height=200,
        placeholder="Es. Chiama Mario Rossi al 3291234567, mail mario@esempio.it",
    )

    if st.button("🔒 Maschera", type="primary", use_container_width=True):
        if not text.strip():
            st.warning("Inserisci del testo o carica un file.")
            return

        masker = load_masker()
        config = MaskConfig(language=language)

        if reversible:
            result = masker.mask_reversible(text, language=language, config=config)
        else:
            result = masker.mask_detailed(text, language=language, config=config)

        st.subheader("Risultato")
        st.code(result.text, language=None)  # st.code gives a built-in copy button
        st.success(summarize(result.entities))

        st.download_button(
            "💾 Scarica risultato",
            data=result.text,
            file_name="testo_mascherato.txt",
            mime="text/plain",
            use_container_width=True,
        )

        if reversible and result.mapping:
            st.download_button(
                "🔑 Scarica mappa di ripristino (JSON)",
                data=json.dumps(result.mapping, ensure_ascii=False, indent=2),
                file_name="mappa_ripristino.json",
                mime="application/json",
                use_container_width=True,
            )
            st.info(
                "Conserva la mappa al sicuro: serve a ricostruire i dati originali "
                "dalla risposta dell'AI. Chiunque la possieda può de-anonimizzare il testo."
            )


if __name__ == "__main__":
    main()
