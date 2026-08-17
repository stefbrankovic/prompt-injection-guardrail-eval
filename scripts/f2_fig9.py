#!/usr/bin/env python3
"""f2_fig9.py — radna karakteristika: gde uopste lezi odluka.

Samostalna skripta, ne dira f2_figs.py. Crta TPR i FPR kao funkcije praga
iz vec zapisanog results/raw/t4_external_scores.jsonl. Nijedan poziv modela.

Poenta figure nije oblik krive nego SIRINA x-ose: kod deepset-a ceo prostor
odluke stane u ~5e-4, kod Prompt Guard-a se prostire preko celog [0, 1].
Zato se x-osa NE normalizuje — sirina se ispisuje u naslovu panela.

    python scripts/f2_fig9.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402

RAW = Path("results/raw")
FIG = Path("results/figures")

C_BEN = "#4C78A8"
C_MAL = "#E45756"
C_GREY = "#9A9A9A"
NICE = {"promptguard2_86m": "PG2-86M", "promptguard2_22m": "PG2-22M",
        "protectai_v2": "ProtectAI v2", "deepset": "Deepset"}


def rate(vals, t):
    return sum(1 for v in vals if v >= t) / len(vals) if vals else float("nan")


def thr_at(neg, target):
    s = sorted(neg, reverse=True)
    k = int(len(s) * target)
    if k <= 0:
        return s[0] + 1e-9
    return 0.0 if k >= len(s) else s[k] + 1e-9


def main() -> int:
    p = RAW / "t4_external_scores.jsonl"
    if not p.exists():
        print(f"nema {p} — pokreni scripts/f2_t4_external.py")
        return 1
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("mode", "naive") == "naive"]
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["detector"]][r["set"]].append(float(r["score"]))

    dets = [d for d in ("deepset", "protectai_v2", "promptguard2_86m",
                        "promptguard2_22m") if d in by] or list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(4.6 * len(dets), 4.4), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        neg = by[d].get("benign", [])
        if not neg:
            continue
        grid = sorted({v for vs in by[d].values() for v in vs})
        if len(grid) > 400:
            grid = grid[::len(grid) // 400]
        ax.plot(grid, [rate(neg, t) for t in grid], color=C_BEN, linewidth=2.2,
                label="FPR (benign)")
        for sname, col, lab in (("agentdojo_imp", C_GREY, "TPR — AgentDojo #imp"),
                                ("ipi_arena", C_MAL, "TPR — IPI Arena")):
            if sname in by[d]:
                ax.plot(grid, [rate(by[d][sname], t) for t in grid], color=col,
                        linewidth=2.2, label=lab)
        for target, ls in ((0.01, "--"), (0.05, ":")):
            t = thr_at(neg, target)
            ax.axvline(t, color="#333333", linestyle=ls, linewidth=1.2)
            ax.text(t, 1.10, f"FPR={target:.0%}", rotation=90, fontsize=7,
                    ha="right", va="top", color="#333333")
        span = grid[-1] - grid[0]
        ax.set_xlim(grid[0], grid[-1])
        ax.set_ylim(0, 1.12)
        ax.tick_params(axis="x", labelsize=7)
        ax.legend(fontsize=7, frameon=False, loc="center left")
        ax.set_title(f"{NICE.get(d, d)}\nfull score range: {span:.2e}", fontsize=11, pad=10)
        ax.set_xlabel("decision threshold", fontsize=10)
        if d == dets[0]:
            ax.set_ylabel("rate", fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.25, linewidth=0.6)
        ax.set_axisbelow(True)
    fig.suptitle("Where the decision actually lives — the x-axis width is the point",
                 fontsize=12, y=1.04)
    FIG.mkdir(parents=True, exist_ok=True)
    out = FIG / "fig9_operating_curves.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
