#!/usr/bin/env python3
"""f2_defense.py — predlozena odbrana i njene izmerene slabosti (traka C + E).

Do sada smo merili KAKO detektori otkazuju. Ovde se te tri ispravke sastave u
jednu proceduru i izmeri se sta ona vrati, a sta ne vrati.

Cetiri pravila, sva merena na ISTOM budzetu laznih uzbuna, na istim dugackim
bezopasnim nosacima (16000 znakova) koje smo koristili u T3:

  naive             ceo dokument u jednom pozivu; sve preko 512 tokena se odseca
  window_max        klizeci prozor, skor dokumenta = maksimum po prozorima
  window_max_hc     isto + ispravljena pokrivenost glave dokumenta
  window_count2_hc  isto, ali se trazi da DVA prozora predju prag

Zasto "ispravljena pokrivenost glave": sa win=1200, stride=600, prvih 600
znakova dokumenta leze u tacno jednom prozoru, a sve ostalo u dva. Zbog toga
pravilo `count>=2` strukturno ne moze da opali na payload na samom vrhu — sto
se u T3 videlo kao 0.20 na offsetu 0 prema 1.00 dublje u dokumentu. To NIJE
osobina napada nego artefakt merenja. Ispravka je jedan dodatni prozor
`text[:stride]`, cime svaki karakter lezi u tacno dva prozora.

Prag se za SVAKO pravilo bira zasebno, tako da svako pravilo trosi isti budzet
laznih uzbuna. Bez toga se pravila ne mogu porediti — pravilo koje trazi dva
prozora je po konstrukciji konzervativnije i na fiksnom pragu bi izgledalo
bolje po FPR-u samo zato sto rede opali.

    export PYTHONPATH=src
    python scripts/f2_defense.py --detectors deepset promptguard2_86m protectai_v2

Izlaz: results/tables/defense_rules.csv, results/raw/defense_windows.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.data import load_jsonl                                  # noqa: E402
from psiml.scoring import Scorer, windows                          # noqa: E402

DETECTORS = ["deepset", "protectai_v2", "promptguard2_86m"]


def make_carrier(texts: list[str], n_chars: int, seed_offset: int = 0) -> str:
    """Isti nosac kao u f2_t3_window.py — namerno identican string, zbog kesa."""
    parts, i, total = [], seed_offset, 0
    while total < n_chars:
        t = texts[i % len(texts)]
        parts.append(t)
        total += len(t) + 2
        i += 1
    return "\n\n".join(parts)[:n_chars]


def doc_windows(text: str, size: int, stride: int, head_cover: bool) -> list[str]:
    """Prozori dokumenta, opciono sa ispravljenom pokrivenoscu glave."""
    w = windows(text, size, stride)
    if head_cover and len(text) > size:
        w = [text[:stride]] + w
    return w


# --- pravila agregacije -----------------------------------------------------
def rule_max(scores: list[float], thr: float) -> bool:
    return max(scores) >= thr


def rule_count2(scores: list[float], thr: float) -> bool:
    return sum(1 for s in scores if s >= thr) >= 2


RULES = {
    "naive":            ("naive", rule_max),
    "window_max":       ("plain", rule_max),
    "window_max_hc":    ("hc", rule_max),
    "window_count2_hc": ("hc", rule_count2),
}


def calibrate(neg_docs: list[list[float]], rule, target: float) -> float:
    """Najnizi prag na kome pravilo jos uvek trosi <= target laznih uzbuna.

    FPR je monotono nerastuca funkcija praga, pa je dovoljan jedan prolaz kroz
    kandidate u opadajucem redosledu. Kandidati su sami benigni skorovi: prag
    izmedju dva susedna skora ne moze promeniti nijednu odluku.
    """
    cands = sorted({s for d in neg_docs for s in d}, reverse=True)
    best = cands[0] + 1e-9 if cands else 1.0
    for t in cands:
        fpr = sum(1 for d in neg_docs if rule(d, t)) / len(neg_docs)
        if fpr <= target:
            best = t
        else:
            break
    return best


def rate(docs: list[list[float]], rule, thr: float) -> float:
    return sum(1 for d in docs if rule(d, thr)) / len(docs) if docs else float("nan")


def tpr_cluster_ci(docs, clusters, rule, thr, n_boot=2000, alpha=0.05, seed=0):
    """Interval za TPR uzorkovanjem KLASTERA sa vracanjem, ne stringova.

    95 IPI stringova pokriva samo 28 razlicitih ponasanja; vise stringova
    napada isto ponasanje. Tretiranje kao 95 nezavisnih uzoraka suzilo bi
    interval za ~sqrt(95/28) = 1.8 puta — lazna preciznost.
    """
    by = {}
    for d, c in zip(docs, clusters):
        by.setdefault(c, []).append(1.0 if rule(d, thr) else 0.0)
    keys = list(by)
    rng = random.Random(seed)
    out = []
    for _ in range(n_boot):
        pick = [by[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [v for g in pick for v in g]
        out.append(sum(flat) / len(flat))
    out.sort()
    return out[int(n_boot * alpha / 2)], out[int(n_boot * (1 - alpha / 2))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipi", type=Path, default=Path("data/injections/ipi_arena_en.jsonl"))
    ap.add_argument("--benign-full", type=Path,
                    default=Path("data/injections/agentdojo_benign_full_en.jsonl"))
    ap.add_argument("--detectors", nargs="+", default=DETECTORS)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--n-carriers", type=int, default=40)
    ap.add_argument("--carrier-chars", type=int, default=16000)
    ap.add_argument("--win", type=int, default=1200)
    ap.add_argument("--stride", type=int, default=600)
    ap.add_argument("--embed", type=int, default=None, metavar="OFFSET",
                    help="ubaci svaki napad u nosac iste duzine, na dati offset. "
                         "Bez ovoga bezopasna strana ima 26 prozora a napadi 1, "
                         "pa je poredjenje namesteno protiv prozora.")
    ap.add_argument("--fpr", type=float, default=0.05,
                    help="rezolucija je 1/n_carriers; pri 40 nosaca 0.05 = 2 dokumenta")
    ap.add_argument("--holdout", action="store_true",
                    help="kalibrisi prag na prvoj polovini nosaca, prijavi FPR na drugoj. "
                         "Bez ovoga je FPR nametnut konstrukcijom, ne izmeren.")
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    ben = load_jsonl(a.benign_full)
    ben_texts = [s.text for s in ben]
    ipi = load_jsonl(a.ipi)
    carriers = [make_carrier(ben_texts, a.carrier_chars, 7 * k + 1)
                for k in range(a.n_carriers)]
    # isti kljuc klastera kao u f2_t4_external.py — 95 stringova, ali 28 ponasanja
    clusters = [s.id.split("#")[0] if "#" in s.id else
                getattr(s, "suite", "") + "__" + s.id.rsplit("__", 1)[0] for s in ipi]
    if a.embed is None:
        atk_texts = [s.text for s in ipi]
    else:
        atk_texts = []
        for k, s in enumerate(ipi):
            c = make_carrier(ben_texts, a.carrier_chars, 1000 + 7 * k)
            off = min(a.embed, len(c))
            atk_texts.append(c[:off] + "\n\n" + s.text + "\n\n" + c[off:])
    print(f"bezopasnih nosaca {len(carriers)} po {a.carrier_chars} znakova, "
          f"IPI napada {len(ipi)} stringova / {len(set(clusters))} ponasanja")
    med_n = sorted(len(t) for t in carriers)[len(carriers) // 2]
    med_p = sorted(len(t) for t in atk_texts)[len(atk_texts) // 2]
    print(f"medijana duzine: bezopasni {med_n}, napadi {med_p} znakova"
          + ("" if a.embed is None else f"  (napadi ubaceni na offset {a.embed})"))
    if a.embed is None and med_p * 3 < med_n:
        print("  UPOZORENJE: strane nisu iste duzine. Prag postavlja 26 prozora")
        print("  bezopasnog dokumenta, a napad ima jedan — poredjenje naive vs")
        print("  window i pravilo count>=2 NISU valjani. Pokreni sa --embed 4000.")
    print(f"budzet laznih uzbuna: {a.fpr:.0%}  (= {int(len(carriers) * a.fpr)} od "
          f"{len(carriers)} nosaca)")

    rows, raw = [], []
    for d in a.detectors:
        sc = Scorer(d, device=a.device, batch_size=a.batch_size)
        pools: dict[str, dict[str, list[list[float]]]] = {}

        # naive: ceo dokument, jedan poziv (kes iz T3/T4)
        pools["naive"] = {
            "neg": [[v] for v in sc.score(carriers, label="odbrana/naive/ben")],
            "pos": [[v] for v in sc.score(atk_texts, label="odbrana/naive/ipi")],
        }
        # prozori, sa i bez ispravljene pokrivenosti glave
        for mode, hc in (("plain", False), ("hc", True)):
            out = {}
            for side, texts in (("neg", carriers), ("pos", atk_texts)):
                per = [doc_windows(t, a.win, a.stride, hc) for t in texts]
                flat = [w for ws in per for w in ws]
                v = sc.score(flat, label=f"odbrana/{mode}/{side}")
                docs, i = [], 0
                for ws in per:
                    docs.append(v[i:i + len(ws)])
                    i += len(ws)
                out[side] = docs
            pools[mode] = out
            if mode == "hc":
                for side in ("neg", "pos"):
                    for j, ds in enumerate(pools[mode][side]):
                        for wi, s in enumerate(ds):
                            raw.append({"detector": d, "side": side, "doc_idx": j,
                                        "window_idx": wi, "score": round(s, 6)})

        print(f"\n=== {d} ===")
        print(f"  {'pravilo':>18} {'prag':>12} {'FPR':>7} {'TPR (IPI)':>10} {'95% CI':>16} {'prozora':>8}")
        for name, (mode, rule) in RULES.items():
            neg, pos = pools[mode]["neg"], pools[mode]["pos"]
            if a.holdout:
                h = len(neg) // 2
                thr = calibrate(neg[:h], rule, a.fpr)
                fpr = rate(neg[h:], rule, thr)
            else:
                thr = calibrate(neg, rule, a.fpr)
                fpr = rate(neg, rule, thr)
            tpr = rate(pos, rule, thr)
            lo, hi = tpr_cluster_ci(pos, clusters, rule, thr)
            nw = sum(len(x) for x in neg) / len(neg)
            print(f"  {name:>18} {thr:>12.6f} {fpr:>7.3f} {tpr:>10.3f}   [{lo:.3f}, {hi:.3f}] {nw:>8.1f}")
            rows.append({"detector": d, "rule": name, "thr": round(thr, 6),
                         "fpr_benign_16k": round(fpr, 4), "tpr_ipi": round(tpr, 4),
                         "tpr_lo": round(lo, 4), "tpr_hi": round(hi, 4),
                         "fpr_holdout": int(a.holdout),
                         "n_benign": len(neg), "n_attacks": len(pos),
                         "n_clusters": len(set(clusters)),
                         "embed_offset": -1 if a.embed is None else a.embed,
                         "mean_windows": round(nw, 1)})

    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    (a.out / "raw").mkdir(parents=True, exist_ok=True)
    with (a.out / "raw" / "defense_windows.jsonl").open("w", encoding="utf-8") as f:
        for r in raw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    p = a.out / "tables" / "defense_rules.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {p}")

    print("\nCITANJE — sta ova procedura POPRAVLJA:")
    print("  Razlika naive -> window_max je koliko je odsecanje na 512 tokena kostalo.")
    print("  Razlika window_max -> window_max_hc je artefakt pokrivenosti glave; ako je")
    print("  velika, dosadasnji brojevi za `count>=k` bili su pristrasni protiv payload-a")
    print("  na vrhu dokumenta. Razlika window_max_hc -> window_count2_hc pokazuje da li")
    print("  se lazne uzbune iz visestrukih poredjenja mogu skinuti bez gubitka TPR-a.")
    print("\nCITANJE — sta NE popravlja, i to se izgovara naglas:")
    print("  1. Jezik. Prag je i dalje kalibrisan na engleskom; T2 pokazuje 70.7% FPR na")
    print("     bezopasnom srpskom kod deepset-a. Nijedno pravilo agregacije to ne dira.")
    print("  2. Formu. T1 pokazuje da prazan omotac dobija skor pravog napada; prozor")
    print("     seckanjem ne menja to sto detektor gleda sablon a na nameru.")
    print("  3. Cenu. Dokument od 16000 znakova je ~27 poziva modela umesto 1.")
    print("  4. Agenta. I dalje merimo skorove detektora, ne da li bi agent poslusao.")
    print("  5. Uzorak. IPI Arena je selektovana po uspehu protiv jednog agenta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())