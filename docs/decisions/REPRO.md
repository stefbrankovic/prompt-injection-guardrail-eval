# Reprodukcija svakog broja u prezentaciji

| Broj / slika | Komanda | Config | Traje |
|---|---|---|---|
| Tabela 1 | `python -m psiml.cli.run --config configs/experiments/...` | | |


## Baseline (PG2-86M, Colab, 10.08) — reprodukovati sa:
`python scripts/detector_sanity.py -d promptguard2_86m --save results/raw/sanity_pg2.json`

Očekivani red veličine (n=3 po varijanti):
- en napad "Ignore...": ~0.999
- en_homoglyph isti napad: ~0.517  ← cilj pretrage: ispod 0.5
- svi benign: ~0.0005 (FPR 0%)
