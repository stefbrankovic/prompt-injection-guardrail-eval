# Git workflow — dvoje ljudi, 6 dana

Skraćena verzija, dogovoriti pre prvog paralelnog rada.

## Grane
```
main                  ← uvek prolazi `pytest -q`. Ovde se merge-uje.
stefan/<zadatak>      ← Stefanova aktivna grana (živi max 1 dan)
katarina/<zadatak>    ← Katarinina aktivna grana (živi max 1 dan)
```

## Dnevni ritam
```bash
# ujutru
git checkout main && git pull
git checkout -b stefan/actprobe

# tokom dana: commit-uj koliko hoćeš, poruke mogu biti aljkave

# kad je NEŠTO gotovo (ne "kad je kraj dana"):
pytest -q                       # OBAVEZNO, jedini gate
git checkout main && git pull
git merge --no-ff stefan/actprobe -m "feat: ActProbe defense klasa"
git push
```

## Pravila (dogovoriti danas)
| Pravilo | Zašto |
|---|---|
| `main` uvek prolazi `pytest -q` | da partner može da veruje pull-u |
| grane žive max 1 dan | 6-dnevni projekat ne podnosi duge grane |
| merge svoju granu sam, bez PR-a | review između dvoje za 6 dana je pozorište |
| sinhronizacija 13h i 20h, 10 min | sprečava paralelan rad na istom fajlu |
| moraš u isti fajl → javi pre | jeftinije od merge konflikta |

## Notebook-ovi
- `nbstripout` instaliran (skida output pre commita → nema JSON merge konflikata).
- Lični folderi: `notebooks/stefan/`, `notebooks/katarina/`. `notebooks/shared/` samo dogovorno.
- Kod koji proradi u notebook-u seli se u `src/psiml/` **istog dana**.

## Interfejs napad↔odbrana (ne menja se posle D1)
JSONL, jedan red po varijanti napada:
```json
{"injection_id": "ad_07", "jezik": "sr", "pismo": "cyr", "varijanta": "homoglif",
 "tekst": "...", "budget": 3, "pg2_score": 0.04, "evaded": true}
```
Napadačka strana (Katarina) piše ovaj fajl u `results/raw/attacks/`.
Odbrambena strana (Stefan) ga čita. Tako se ne sudarate u kodu.
