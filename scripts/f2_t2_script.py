#!/usr/bin/env python3
"""T2 — pismo, mesanje pisama, i cena po karakteru.

Postojeci podaci (Faza 1) ne razdvajaju dve hipoteze:
    H_pismo    detektor kaznjava cirilicu kao takvu
    H_mesanje  detektor kaznjava mesanje pisama, bez obzira koje je bazno

Zato se meri pun kvadrat, sa sadrzajem drzanim koliko god je moguce fiksnim:

    en_orig          engleski benigni (AgentDojo okruzenja) — na njemu se
                     kalibrise prag na FPR=1%; to je situacija branioca
    en_parallel      ISTI sadrzaj kao sr_cyrl, ali engleski (FLORES) — postoji
                     samo ako je f2_data.py uspeo sa FLORES-om
    sr_cyrl_orig     cist srpski, cirilica
    sr_latn_orig     ISTI srpski tekst, latinica (deterministicka translit.)
    en_mix_B         engleski + cirilicni dvojnici          (lat2cyr)
    sr_latn_mix_B    srpska latinica + cirilicni dvojnici   (lat2cyr)
    sr_cyrl_mix_B    srpska cirilica + latinicni dvojnici   (cyr2lat)  <- kljuc

Svaki ishod je nalaz:
  - sr_cyrl_orig ima visok FPR                 -> kaznjava se PISMO
  - sr_cyrl_orig nizak a sr_cyrl_mix visok     -> kaznjava se MESANJE
  - oba niska, a en_mix visok                  -> kaznjava se ODSTUPANJE od
                                                  ocekivanog pisma za taj jezik
  - sve nisko                                  -> detektor je visejezicno u redu
                                                  i nalaz je gradijent po modelima

Drugi izlaz je naslovni broj: MEDIJAN BROJA KARAKTERA koji je dovoljan da
bezopasan tekst predje prag. To je uskracivanje usluge nad detektorom —
napad koji stvarno radi i koji je direktna posledica falsifikovane hipoteze.

    export PYTHONPATH=src
    python scripts/f2_t2_script.py --detectors deepset promptguard2_86m --limit 150
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.attack.mixing import mix_budget, mixing_ratio      # noqa: E402
from psiml.data import load_jsonl                             # noqa: E402
from psiml.metrics import rate_above, threshold_at_fpr        # noqa: E402
from psiml.scoring import Scorer                              # noqa: E402

BUDGETS: list[int | str] = [1, 2, 3, 5, 8, 13, 21, "25%", "50%", "100%"]
DOS_GRID: list[int] = [0, 1, 2, 3, 4, 5, 6, 8, 10, 13, 16, 21, 30, 45, 70]
DETECTORS = ["deepset", "protectai_v2", "promptguard2_86m", "promptguard2_22m"]


def tag(b: int | str) -> str:
    return str(b) if isinstance(b, str) else f"{b}ch"


def build_conditions(en, sr_cyrl, sr_latn, en_par) -> dict[str, list[tuple[str, str]]]:
    c: dict[str, list[tuple[str, str]]] = {
        "en_orig": [(s.id, s.text) for s in en],
        "sr_cyrl_orig": [(s.id, s.text) for s in sr_cyrl],
        "sr_latn_orig": [(s.id, s.text) for s in sr_latn],
    }
    if en_par:
        c["en_parallel"] = [(s.id, s.text) for s in en_par]
    for b in BUDGETS:
        c[f"en_mix_{tag(b)}"] = [(s.id, mix_budget(s.text, b, "lat2cyr")[0]) for s in en]
        c[f"sr_latn_mix_{tag(b)}"] = [(s.id, mix_budget(s.text, b, "lat2cyr")[0]) for s in sr_latn]
        c[f"sr_cyrl_mix_{tag(b)}"] = [(s.id, mix_budget(s.text, b, "cyr2lat")[0]) for s in sr_cyrl]
    return c


def min_budget_to_cross(sc: Scorer, samples, direction: str, thr: float) -> list[dict]:
    """Za svaki tekst najmanji broj zamena posle kojeg score predje prag.

    Sve tacke mreze se skoruju odjednom (batch), pa se cita prvo prelazenje.
    Ne pretpostavlja se monotonost — trazi se PRVO prelazenje i belezi se da li
    se do kraja mreze uopste desilo.
    """
    texts, meta = [], []
    for s in samples:
        for b in DOS_GRID:
            t, used, avail = mix_budget(s.text, b, direction)
            texts.append(t)
            meta.append((s.id, b, used, avail))
    vals = sc.score(texts, label=f"dos:{direction}")
    per: dict[str, list[tuple[int, int, float]]] = {}
    for (sid, b, used, avail), v in zip(meta, vals):
        per.setdefault(sid, []).append((b, used, v))
    out = []
    for sid, lst in per.items():
        lst.sort(key=lambda t: t[0])
        crossed = next((u for _, u, v in lst if v >= thr), None)
        out.append({"id": sid, "min_chars": crossed,
                    "base_score": round(lst[0][2], 6),
                    "max_score": round(max(v for _, _, v in lst), 6)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en-benign", type=Path,
                    default=Path("data/injections/agentdojo_benign_full_en.jsonl"))
    ap.add_argument("--sr-cyrl", type=Path, default=Path("data/benign/sr_cyrl.jsonl"))
    ap.add_argument("--sr-latn", type=Path, default=Path("data/benign/sr_latn.jsonl"))
    ap.add_argument("--en-parallel", type=Path, default=Path("data/benign/en_parallel.jsonl"))
    ap.add_argument("--detectors", nargs="+", default=DETECTORS)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--limit", type=int, default=150, help="max tekstova po korpusu (CPU!)")
    ap.add_argument("--fpr", type=float, default=0.01)
    ap.add_argument("--skip-dos", action="store_true")
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    en = load_jsonl(a.en_benign)[:a.limit]
    sr_c = load_jsonl(a.sr_cyrl)[:a.limit]
    sr_l = load_jsonl(a.sr_latn)[:a.limit]
    en_p = load_jsonl(a.en_parallel)[:a.limit] if a.en_parallel.exists() else []
    conds = build_conditions(en, sr_c, sr_l, en_p)
    n_tot = sum(len(v) for v in conds.values())
    print(f"uslova {len(conds)}, tekstova {n_tot} po detektoru "
          f"(+{len(en) * len(DOS_GRID)} za DoS)")

    rows, table, dos_rows = [], [], []
    for d in a.detectors:
        sc = Scorer(d, device=a.device, batch_size=a.batch_size)
        scores: dict[str, list[float]] = {}
        for cname, items in conds.items():
            v = sc.score([t for _, t in items], label=cname)
            scores[cname] = v
            for (sid, txt), s in zip(items, v):
                rows.append({"detector": d, "condition": cname, "id": sid,
                             "score": round(s, 6), "mix_ratio": round(mixing_ratio(txt), 4)})
        thr = threshold_at_fpr(scores["en_orig"], a.fpr)
        print(f"\n{d}: prag na en_orig pri FPR={a.fpr:.0%} je {thr:.6f}")
        for cname, v in scores.items():
            r = {"detector": d, "condition": cname, "n": len(v),
                 "thr_en": round(thr, 6), "fpr": round(rate_above(v, thr), 4),
                 "mean": round(sum(v) / len(v), 4),
                 "median": round(sorted(v)[len(v) // 2], 4)}
            table.append(r)
            if "mix" not in cname or cname.endswith(("1ch", "3ch", "100%")):
                print(f"   {cname:20s} FPR={r['fpr']:.3f} mean={r['mean']:.4f}")
        if not a.skip_dos:
            for direction, samples, name in (("lat2cyr", en, "en"),
                                             ("cyr2lat", sr_c, "sr_cyrl")):
                res = min_budget_to_cross(sc, samples, direction, thr)
                got = sorted(r["min_chars"] for r in res if r["min_chars"] is not None)
                for r in res:
                    dos_rows.append({"detector": d, "corpus": name, "direction": direction, **r})
                if got:
                    print(f"   DoS {name:8s}: {len(got)}/{len(res)} tekstova predje prag, "
                          f"medijan {got[len(got) // 2]} zamena "
                          f"(min {got[0]}, p90 {got[int(len(got) * 0.9)]})")
                else:
                    print(f"   DoS {name:8s}: nijedan tekst ne predje prag do {DOS_GRID[-1]} zamena")

    (a.out / "raw").mkdir(parents=True, exist_ok=True)
    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    with (a.out / "raw" / "t2_script_scores.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for name, data in (("t2_script.csv", table), ("t2_dos.csv", dos_rows)):
        if not data:
            continue
        p = a.out / "tables" / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
        print(f"-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
