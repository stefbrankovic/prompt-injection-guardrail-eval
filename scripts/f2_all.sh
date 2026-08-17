#!/usr/bin/env bash
# Cela Faza 2 jednom komandom. Svaki korak je idempotentan i kesiran, pa se
# skripta sme pustiti ponovo posle pada bez gubitka vec izmerenog.
#
#   bash scripts/f2_all.sh              # dva detektora, brzo
#   DETS="deepset protectai_v2 promptguard2_86m promptguard2_22m" bash scripts/f2_all.sh
#
# Kad se pusta po prvi put, pusti PRVO samo T1 (najkraci) da se izmeri brzina
# CPU-a, pa tek onda ostalo.
set -euo pipefail

export PYTHONPATH=src
DETS="${DETS:-deepset promptguard2_86m}"
LIMIT="${LIMIT:-150}"

echo "=== 0. podaci ==="
python scripts/f2_data.py all --n 300

echo "=== T1 koverta vs sadrzaj ==="
python scripts/f2_t1_envelope.py --detectors $DETS

echo "=== T3 prozor: napad, odbrana, cena ==="
python scripts/f2_t3_window.py --detectors $DETS

echo "=== T4 pravi napadi ==="
python scripts/f2_t4_external.py --detectors $DETS

echo "=== T2 pismo i mesanje ==="
python scripts/f2_t2_script.py --detectors $DETS --limit "$LIMIT"

echo "=== statistika ==="
python scripts/f2_stats.py fpr --raw results/raw/t2_script_scores.jsonl --ref en_orig
python scripts/f2_stats.py auc --raw results/raw/t4_external_scores.jsonl \
    --pos-set ipi_arena --a naive --b chunked

echo "=== figure ==="
python scripts/f2_figures.py

echo "gotovo. tabele: results/tables  figure: results/figures"
