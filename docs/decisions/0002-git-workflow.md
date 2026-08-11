# ADR-0002: finalna odluka o gitu i granama

**Datum:** 10.08.2026 · **Status:** prihvaćeno

## Odluka
**Trunk-based sa kratkotrajnim ličnim granama.** Bez `dev` grane, bez PR review-a.

```
main                    ← uvek prolazi `pytest -q`
├── stefan/<zadatak>    ← živi maksimum 1 dan
└── katarina/<zadatak>  ← živi maksimum 1 dan
```

## Zašto ne GitFlow
`dev` + `release` + PR review je za timove od 10 ljudi i tromesečne cikluse.
Za dvoje na 6 dana je čist overhead: PR review između dvoje ljudi koji sede
zajedno je pozorište, a `dev` grana samo dodaje jedan merge korak.

## Zašto ne "svi guraju na main"
Raspadne se čim jedno pushne polomljen kod, a drugo pullne. Otud jedan tvrd
gate: **`pytest -q` mora da prođe pre merge-a.**

## Pravila
1. `main` uvek prolazi testove. Bez izuzetaka.
2. Grana živi max 1 dan. Duže → merge pakao.
3. Merge svoju granu sam: `make sync` (pokreće testove pa merge-uje).
4. Sinhronizacija 13h i 20h, po 10 minuta.
5. Moraš u tuđi fajl → javi pre nego što počneš.

## Notebook-ovi
`nbstripout` instaliran (skida output → nema JSON konflikata).
Lični folderi `notebooks/stefan/` i `notebooks/katarina/`; `shared/` samo dogovorno.
Kod koji proradi seli se u `src/psiml/` istog dana.

## Interfejs napad↔odbrana (zaključan D1)
JSONL, `results/raw/`:
```json
{"injection_id":"ad_07","jezik":"sr","pismo":"cyr","varijanta":"homoglif",
 "tekst":"...","budget":3,"detector":"promptguard2_86m","score":0.04,"evaded":true}
```
Katarina (napad) piše. Stefan (odbrana/eval) čita. Tako se ne sudarate u kodu.
