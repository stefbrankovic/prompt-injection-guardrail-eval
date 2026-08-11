# CyrEvade — PSIML 11

**Napad na filtere AI agenata koji ljudsko oko ne vidi, mehanizam koji ga objašnjava, i odbrana koja ga hvata.**

Stefan Branković, Katarina · Mentor: Kristina Nikolić (ETH, SPY Lab)

## Šta je ovo
LLM ne razlikuje instrukciju od podatka, pa se agent može oteti instrukcijom sakrivenom u tekstu koji pročita. Odbrana (Prompt Guard 2) pokriva 8 jezika; srpski nije među njima. Zamenom latiničnih karaktera **vizuelno identičnim** srpskim ćiriličnim homoglifima činimo injection nevidljivim za filter, a čitljivim i modelu i čoveku. Zatim gradimo odbranu koja umesto teksta čita **aktivacije modela** — pa je robusna na napad uz nula dodatne latencije — i pokušavamo da razbijemo i nju.

## Odakle početi (redosled čitanja)
0. **`docs/SETUP.md`** — instalacija, VS Code, conda, git, AgentDojo. **Uradi prvo, večeras.**
1. **`docs/TEORIJA.md`** — svi pojmovi od nule (token, injection, TPR/FPR, probe...). ~40 min. **Pročitati prvo.**
2. **`MASTERPLAN.md`** — ceo plan po činovima i danima.
3. **`docs/MEETING_2026-08-10.md`** — priprema za sastanak, plan za D1.
4. `docs/MENTOR_PITCH.md` — definicija problema i prezentacija.

## Brzi start
```bash
conda env create -f environment.yml
conda activate psiml
pip install -e .
pytest -q                                    # mora da prođe
python -m psiml.cli.demo_attack              # demo napada (bez modela, radi na laptopu)
python scripts/detector_sanity.py --mock     # zasto TPR bez FPR ne znaci nista
python scripts/check_access.py               # POKRENUTI VECERAS (gated modeli!)
```

## Struktura
| Putanja | Šta |
|---|---|
| `src/psiml/attack/homoglyphs.py` | latinica↔ćirilica homoglif mapa (jezgro Čina I) |
| `src/psiml/attack/search.py` | CyrEvade greedy/beam pretraga |
| `src/psiml/defense/` | ActProbe — probe nad aktivacijama (Čin III) |
| `src/psiml/eval/` | AgentDojo integracija, metrike (ASR, evazija) |
| `src/psiml/viz/` | krive evazije, heatmapovi |
| `configs/experiments/` | YAML po eksperimentu |
| `results/tables/`, `results/figures/` | finalni artefakti |
| `docs/TEORIJA.md` | **svi pojmovi od nule — počni odavde** |
| `scripts/detector_sanity.py` | test detektora sa kontrolnom grupom (TPR **i** FPR) |
| `scripts/check_access.py` | provera HF pristupa, gated modeli |
| `docs/MENTOR_PITCH.md` | definicija problema+rešenja, prezentacija |
| `docs/GIT_WORKFLOW.md` | git za dvoje na 6 dana |
| `docs/READING_PROTOCOL.md` | kako se čita literatura (budžet 4h) |

## Status
- [x] Homoglif jezgro + pretraga (testirano, `tests/test_attack.py`)
- [ ] Prompt Guard 2 integracija (D1)
- [ ] Kriva evazije (D2)
- [ ] ActProbe (D4–D5)
- [ ] Adaptivni napad (D6)

## Etika
Prompt Guard je javno objavljen model. Nalaze prijavljujemo Meti pre javne objave (PurpleLlama report kanal). Ovo je odbrambeno istraživanje.
