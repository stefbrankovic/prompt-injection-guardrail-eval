#!/usr/bin/env python3
"""T4 — da li ista od ovoga vazi na napadima koji su stvarno radili.

Ceo projekat je do sada meren na 35 AgentDojo injection zadataka. To su
sablonski ciljevi (`GOAL` string) plus jedan te isti omotac. Nijedan od njih
nije nikad prosao ni na jednom agentu — oni su specifikacija napada, ne napad.

IPI Arena (arXiv:2603.15714, Dziemian et al. 2026, Gray Swan) daje suprotnu
distribuciju: 95 stringova koje su ljudi rucno pisali na takmicenju i koji su
STVARNO uspeli protiv Qwen agenta. Duzi su, koriste HTML komentare, lazne
sistemske blokove, tool-call sintaksu, nevidljive Unicode karaktere.

Pitanje: detektor koji na AgentDojo `#imp` ima TPR blizu 1.00 — koliki TPR
ima na napadima koji su stvarno radili, pri ISTOM pragu?

Meri se cetiri stvari:
  1. TPR@FPR=1% po skupu napada (AgentDojo #imp, #raw, IPI Arena)
  2. AUC sa klasterskim intervalom (klaster = injection_task / behavior_id)
  3. TPR po duzinskim razredima — spaja se sa T3: da li promasaji dolaze od
     duzine (odsecanje) ili od sadrzaja
  4. Isti IPI skup sa klizecim prozorom — koliko od promasaja vraca odbrana
     iz T3; razlika izmedju ta dva broja je "koliko je krivo odsecanje"

    export PYTHONPATH=src
    python scripts/f2_t4_external.py --detectors deepset promptguard2_86m
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.data import load_jsonl                                  # noqa: E402
from psiml.metrics import auc_ci, rate_above, threshold_at_fpr     # noqa: E402
from psiml.scoring import Scorer, score_chunked                    # noqa: E402

BUCKETS = [(0, 500), (500, 1500), (1500, 4000), (4000, 10 ** 9)]
DETECTORS = ["deepset", "protectai_v2", "promptguard2_86m", "promptguard2_22m"]


def bucket(n: int) -> str:
    for lo, hi in BUCKETS:
        if lo <= n < hi:
            return f"{lo}-{hi if hi < 10 ** 9 else 'inf'}"
    return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacks", type=Path, default=Path("data/injections/agentdojo_en.jsonl"))
    ap.add_argument("--ipi", type=Path, default=Path("data/injections/ipi_arena_en.jsonl"))
    ap.add_argument("--benign-full", type=Path,
                    default=Path("data/injections/agentdojo_benign_full_en.jsonl"))
    ap.add_argument("--detectors", nargs="+", default=DETECTORS)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--win", type=int, default=1200)
    ap.add_argument("--stride", type=int, default=600)
    ap.add_argument("--fpr", type=float, default=0.01)
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    ad = load_jsonl(a.attacks)
    ipi = load_jsonl(a.ipi)
    ben = load_jsonl(a.benign_full)
    sets = {
        "agentdojo_imp": [s for s in ad if s.wrap == "important"],
        "agentdojo_raw": [s for s in ad if s.wrap == "raw"],
        "ipi_arena": ipi,
    }
    lens = sorted(len(s.text) for s in ipi)
    print(f"IPI Arena: n={len(ipi)}, duzina med={lens[len(lens) // 2]}, max={lens[-1]} znakova")
    print(f"AgentDojo #imp: med={sorted(len(s.text) for s in sets['agentdojo_imp'])[17]} znakova")

    rows, table, buck = [], [], []
    for d in a.detectors:
        sc = Scorer(d, device=a.device, batch_size=a.batch_size)
        ben_s = sc.score([s.text for s in ben], label="benign")
        thr = threshold_at_fpr(ben_s, a.fpr)
        print(f"\n{d}: prag={thr:.6f}  (n_benign={len(ben_s)})")
        neg = [(s.id, v) for s, v in zip(ben, ben_s)]
        for s, x in zip(ben, ben_s):
            rows.append({"detector": d, "set": "benign", "id": s.id, "mode": "naive",
                         "n_chars": len(s.text), "score": round(x, 6)})

        for sname, samples in sets.items():
            v = sc.score([s.text for s in samples], label=sname)
            for s, x in zip(samples, v):
                rows.append({"detector": d, "set": sname, "id": s.id, "mode": "naive",
                             "n_chars": len(s.text), "score": round(x, 6)})
            clus = [(s.id.split("#")[0] if "#" in s.id else
                     getattr(s, "suite", "") + "__" + s.id.rsplit("__", 1)[0], x)
                    for s, x in zip(samples, v)]
            auc, lo, hi = auc_ci(clus, neg, n_boot=1000)
            table.append({"detector": d, "set": sname, "mode": "naive", "n": len(v),
                          "thr": round(thr, 6), "tpr": round(rate_above(v, thr), 4),
                          "auc": round(auc, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
                          "mean": round(sum(v) / len(v), 4)})
            print(f"   {sname:16s} TPR@FPR{a.fpr:.0%}={table[-1]['tpr']:.2f}  "
                  f"AUC={auc:.3f} [{lo:.3f}, {hi:.3f}]")

            if sname == "ipi_arena":
                vc, cnt = score_chunked(sc, [s.text for s in samples], a.win, a.stride,
                                        label="ipi/chunked")
                for s, x in zip(samples, vc):
                    rows.append({"detector": d, "set": sname, "id": s.id, "mode": "chunked",
                                 "n_chars": len(s.text), "score": round(x, 6)})
                auc2, lo2, hi2 = auc_ci([(c, x) for (c, _), x in zip(clus, vc)], neg, n_boot=1000)
                table.append({"detector": d, "set": sname, "mode": "chunked", "n": len(vc),
                              "thr": round(thr, 6), "tpr": round(rate_above(vc, thr), 4),
                              "auc": round(auc2, 4), "ci_lo": round(lo2, 4), "ci_hi": round(hi2, 4),
                              "mean": round(sum(vc) / len(vc), 4)})
                print(f"   {'ipi_arena+prozor':16s} TPR={table[-1]['tpr']:.2f}  "
                      f"AUC={auc2:.3f} [{lo2:.3f}, {hi2:.3f}]  "
                      f"(prosek {sum(cnt) / len(cnt):.1f} prozora)")
                by: dict[str, list[tuple[float, float]]] = {}
                for s, x, y in zip(samples, v, vc):
                    by.setdefault(bucket(len(s.text)), []).append((x, y))
                for b, pairs in sorted(by.items(), key=lambda kv: int(kv[0].split("-")[0])):
                    buck.append({"detector": d, "bucket_chars": b, "n": len(pairs),
                                 "tpr_naive": round(rate_above([p[0] for p in pairs], thr), 3),
                                 "tpr_chunked": round(rate_above([p[1] for p in pairs], thr), 3)})
                    print(f"      duzina {b:>10}: n={len(pairs):>3} "
                          f"TPR naive={buck[-1]['tpr_naive']:.2f} chunked={buck[-1]['tpr_chunked']:.2f}")

    (a.out / "raw").mkdir(parents=True, exist_ok=True)
    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    with (a.out / "raw" / "t4_external_scores.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for name, data in (("t4_external.csv", table), ("t4_by_length.csv", buck)):
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
