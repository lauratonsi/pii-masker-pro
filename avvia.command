#!/bin/bash
# Double-click this file (macOS) to launch PII Masker Pro in your browser.
# It runs entirely on your computer — no data is sent anywhere.

cd "$(dirname "$0")" || exit 1

# Find conda and run the app inside the dedicated environment.
if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate pii-masker 2>/dev/null
    exec streamlit run app.py
else
    echo "Conda non trovato. Apri un terminale ed esegui:"
    echo "    conda activate pii-masker && streamlit run app.py"
    read -r -p "Premi Invio per chiudere."
fi
