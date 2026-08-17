#!/usr/bin/env python3
"""T1 — koverta ili pismo: sta detektor zapravo klasifikuje.

Dizajn je 2x2 sa dodatom kontrolom, i sadrzaj je jedina stvar koja se menja:

                      goli tekst          u AgentDojo omotacu
    maliciozan cilj   A mal_raw           B mal_imp
    bezopasan cilj    C ben_raw           D ben_imp      <- kljucna celija
    bez cilja         —                   E empty_imp    (sam omotac)

Dve velicine koje izlaze iz tabele:
    delta_koverta = mean(D) - mean(C)   koliko doprinosi SAMO omotac
    delta_sadrzaj = mean(A) - mean(C)   koliko doprinosi SAMA namera

Ako je delta_koverta >> delta_sadrzaj, detektor klasifikuje formu. To je
tvrdnja koja stoji nezavisno od homoglifa, cirilice i svega ostalog u projektu,
i zato je ona osiguranje cele Faze 2.

Omotac se NE prepisuje rucno nego se izvodi iz samih podataka: uporedi se
`#imp` i `#raw` verzija istog zadatka i uzme zajednicki prefiks i sufiks. Time
je garantovano da testiramo tacno onaj omotac koji je u nasem skupu.

    export PYTHONPATH=src
    python scripts/f2_t1_envelope.py --detectors deepset promptguard2_86m
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.data import load_jsonl                            # noqa: E402
from psiml.metrics import rate_above, threshold_at_fpr       # noqa: E402
from psiml.scoring import Scorer                             # noqa: E402

DETECTORS = ["deepset", "protectai_v2", "promptguard2_86m", "promptguard2_22m"]


def derive_wrapper(samples) -> tuple[str, str]:
    """Iz para (#raw, #imp) istog zadatka izvuci prefiks i sufiks omotaca."""
    raw = {s.id.split("#")[0]: s.text for s in samples if s.wrap == "raw"}
    for s in samples:
        if s.wrap != "important":
            continue
        goal = raw.get(s.id.split("#")[0])
        if goal and goal in s.text:
            i = s.text.index(goal)
            return s.text[:i], s.text[i + len(goal):]
    raise SystemExit("Ne mogu da izvedem omotac — proveri da li fajl ima i #raw i #imp redove.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacks", type=Path, default=Path("data/injections/agentdojo_en.jsonl"))
    ap.add_argument("--benign-goals", type=Path, default=Path("data/injections/benign_goals_en.jsonl"))
    ap.add_argument("--benign-full", type=Path,
                    default=Path("data/injections/agentdojo_benign_full_en.jsonl"))
    ap.add_argument("--detectors", nargs="+", default=DETECTORS)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--fpr", type=float, default=0.01)
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    atk = load_jsonl(a.attacks)
    goals = load_jsonl(a.benign_goals)
    calib = load_jsonl(a.benign_full)
    pre, suf = derive_wrapper(atk)
    print(f"omotac izveden: prefiks {len(pre)} znakova, sufiks {len(suf)} znakova")

    conds: dict[str, list[tuple[str, str]]] = {
        "A_mal_raw": [(s.id, s.text) for s in atk if s.wrap == "raw"],
        "B_mal_imp": [(s.id, s.text) for s in atk if s.wrap == "important"],
        "C_ben_raw": [(s.id, s.text) for s in goals],
        "D_ben_imp": [(s.id, pre + s.text + suf) for s in goals],
        "E_empty_imp": [("wrapper_only", (pre + suf).strip())],
    }
    for k, v in conds.items():
        print(f"  {k:12s} n={len(v)}")

    rows, table = [], []
    for d in a.detectors:
        sc = Scorer(d, device=a.device, batch_size=a.batch_size)
        thr = threshold_at_fpr(sc.score([s.text for s in calib], label="kalibracija"), a.fpr)
        means = {}
        for cname, items in conds.items():
            vals = sc.score([t for _, t in items], label=cname)
            means[cname] = sum(vals) / len(vals)
            for (sid, _), v in zip(items, vals):
                rows.append({"detector": d, "condition": cname, "id": sid, "score": round(v, 6)})
            table.append({
                "detector": d, "condition": cname, "n": len(vals),
                "thr": round(thr, 6),
                "mean": round(means[cname], 4),
                "median": round(sorted(vals)[len(vals) // 2], 4),
                "flag_rate": round(rate_above(vals, thr), 4),
            })
            print(f"  {d:18s} {cname:12s} mean={means[cname]:.4f} "
                  f"flag@FPR{a.fpr:.0%}={rate_above(vals, thr):.2f}")
        d_env = means["D_ben_imp"] - means["C_ben_raw"]
        d_con = means["A_mal_raw"] - means["C_ben_raw"]
        table.append({"detector": d, "condition": "*delta_koverta", "n": 0, "thr": round(thr, 6),
                      "mean": round(d_env, 4), "median": "", "flag_rate": ""})
        table.append({"detector": d, "condition": "*delta_sadrzaj", "n": 0, "thr": round(thr, 6),
                      "mean": round(d_con, 4), "median": "", "flag_rate": ""})
        print(f"  >>> {d}: delta_koverta={d_env:+.3f}  delta_sadrzaj={d_con:+.3f}  "
              f"odnos={'inf' if abs(d_con) < 1e-6 else f'{d_env / d_con:.1f}x'}")

    (a.out / "raw").mkdir(parents=True, exist_ok=True)
    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    import json
    with (a.out / "raw" / "t1_envelope_scores.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tp = a.out / "tables" / "t1_envelope.csv"
    with tp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    print(f"\n-> {tp}")
    print("CITANJE: ako je D (bezopasno u omotacu) blizu B (maliciozno u omotacu),")
    print("         a A (maliciozno golo) blizu C (bezopasno golo) — detektor cita kovertu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
