#!/usr/bin/env python3
"""f2_figs.py — all presentation figures generated from precomputed CSV tables.

Does not call models. Does not compute statistics. Only plots data that
`f2_analyze.py` and tracks T1-T4 have already saved in `results/tables/`.

    python scripts/f2_figs.py            # generate everything possible
    python scripts/f2_figs.py --only 1 3 # only figures 1 and 3

Each figure is skipped if its required input CSV is missing, and a log message
is printed. No missing file crashes the remaining figures.

Output: results/figures/figN_*.png  (150 dpi, ready for slides)
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt        # noqa: E402

TAB = Path("results/tables")
FIG = Path("results/figures")

# Palette: high contrast for both projectors and grayscale printing
C_BEN = "#4C78A8"      # benign
C_MAL = "#E45756"      # malicious
C_ALT = "#72B7B2"      # alternative variant (e.g., with windowing)
C_GREY = "#9A9A9A"
DET_NICE = {
    "promptguard2_86m": "PG2-86M",
    "promptguard2_22m": "PG2-22M",
    "protectai_v2": "ProtectAI v2",
    "deepset": "Deepset",
}


def nice(d: str) -> str:
    return DET_NICE.get(d, d)


def load(name: str) -> list[dict] | None:
    p = TAB / name
    if not p.exists():
        print(f"  skipping — missing {p}")
        return None
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    return rows or None


def f(x, default=float("nan")) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    p = FIG / name
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  -> {p}")


def style(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=12, pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# FIGURE 1 — T1: Five cells per detector + wrapper effect indicators
# ---------------------------------------------------------------------------
def fig1() -> None:
    print("[fig1] T1 — envelope or letter")
    cells = load("t1_cells.csv")
    if not cells:
        return
    dec = load("t1_decomposition.csv") or []

    order = ["C_ben_raw", "A_mal_raw", "D_ben_imp", "B_mal_imp", "E_empty_imp"]
    label = {"C_ben_raw": "benign\nraw", "A_mal_raw": "malicious\nraw",
             "D_ben_imp": "benign\nIN WRAPPER", "B_mal_imp": "malicious\nin wrapper",
             "E_empty_imp": "empty\nwrapper"}
    color = {"C_ben_raw": C_BEN, "A_mal_raw": C_MAL,
             "D_ben_imp": C_BEN, "B_mal_imp": C_MAL, "E_empty_imp": C_GREY}

    by = defaultdict(dict)
    for r in cells:
        by[r["detector"]][r["cell"]] = f(r["mean"])
    dets = [d for d in ["promptguard2_86m", "deepset", "protectai_v2", "promptguard2_22m"]
            if d in by] or list(by)

    w = defaultdict(dict)
    for r in dec:
        w[r["detector"]][r["quantity"]] = (f(r["value"]), f(r["lo"]), f(r["hi"]))

    fig, axes = plt.subplots(1, len(dets), figsize=(4.0 * len(dets), 4.4), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        present = [c for c in order if c in by[d]]
        vals = [by[d][c] for c in present]
        bars = ax.bar(range(len(present)), vals,
                      color=[color[c] for c in present], width=0.68,
                      edgecolor="white", linewidth=1.2)
        for c, b, v in zip(present, bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                    ha="center", fontsize=9)
            if c.endswith("imp") and c != "E_empty_imp":
                b.set_hatch("//")
        ax.set_xticks(range(len(present)))
        ax.set_xticklabels([label[c] for c in present], fontsize=8)
        ax.set_ylim(0, 1.12)
        wb = w.get(d, {}).get("W_ben")
        sub = f"wrapper on benign: {wb[0]:+.2f}" if wb else ""
        style(ax, f"{nice(d)}\n{sub}", "", "average score" if d == dets[0] else "")
    fig.suptitle("Same wrapper, two different contents — individual contributions to score",
                 fontsize=13, y=1.02)
    save(fig, "fig1_t1_wrapper.png")


# ---------------------------------------------------------------------------
# FIGURE 1b — T1: Decomposition with confidence intervals
# ---------------------------------------------------------------------------
def fig1b() -> None:
    print("[fig1b] T1 — decomposition with confidence intervals")
    dec = load("t1_decomposition.csv")
    if not dec:
        return
    want = ["W_ben", "W_mal", "D_raw", "D_imp", "I"]
    txt = {"W_ben": "wrapper on benign\n(paired)",
           "W_mal": "wrapper on malicious\n(paired)",
           "D_raw": "set difference, raw\n(unpaired)",
           "D_imp": "set difference, in wrapper\n(unpaired)",
           "I": "INTERACTION\n(unconfounded)"}
    by = defaultdict(dict)
    for r in dec:
        by[r["detector"]][r["quantity"]] = (f(r["value"]), f(r["lo"]), f(r["hi"]))
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(3.9 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        ys, vs, los, his, cols = [], [], [], [], []
        for i, q in enumerate(want):
            if q not in by[d]:
                continue
            v, lo, hi = by[d][q]
            ys.append(len(ys))
            vs.append(v)
            los.append(v - lo)
            his.append(hi - v)
            cols.append("#2E5496" if q in ("W_ben", "W_mal") else
                        ("#B45309" if q == "I" else C_GREY))
        ax.axvline(0, color="black", linewidth=0.9)
        ax.errorbar(vs, ys, xerr=[los, his], fmt="o", markersize=7,
                    capsize=4, linewidth=1.6, ecolor="#444444",
                    markerfacecolor="white", markeredgewidth=2)
        for y, v, c in zip(ys, vs, cols):
            ax.plot([v], [y], "o", color=c, markersize=7)
        ax.set_yticks(range(len(ys)))
        ax.set_yticklabels([txt[q] for q in want if q in by[d]], fontsize=8)
        ax.invert_yaxis()
        style(ax, nice(d), "difference in average score", "")
    fig.suptitle("If INTERACTION is near zero — wrapper elevates benign and malicious equally",
                 fontsize=12, y=1.03)
    save(fig, "fig1b_t1_decomposition.png")


# ---------------------------------------------------------------------------
# FIGURE 2 — T3: Attack by payload position
# ---------------------------------------------------------------------------
def fig2() -> None:
    print("[fig2] T3 — score by payload position")
    rows = load("t3_position.csv")
    if not rows:
        return
    win = load("t3_effective_window.csv") or []
    cutoff = {}
    for r in win:
        if r.get("corpus") == "en":
            cutoff.setdefault(r["detector"], {})["en"] = f(r["chars_in_512_tokens"])
        if r.get("corpus") == "sr_cyrl":
            cutoff.setdefault(r["detector"], {})["sr"] = f(r["chars_in_512_tokens"])

    by = defaultdict(lambda: defaultdict(lambda: {"n": [], "c": []}))
    for r in rows:
        d, off = r["detector"], int(f(r["offset"], 0))
        by[d][off]["n"].append(f(r["flag_naive"]))
        by[d][off]["c"].append(f(r["flag_chunked"]))
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(5.2 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        offs = sorted(by[d])
        tn = [sum(by[d][o]["n"]) / len(by[d][o]["n"]) for o in offs]
        tc = [sum(by[d][o]["c"]) / len(by[d][o]["c"]) for o in offs]
        ax.plot(offs, tn, "-o", color=C_MAL, linewidth=2.2, markersize=6,
                label="vanilla detector")
        if any(x == x for x in tc):
            ax.plot(offs, tc, "--s", color=C_ALT, linewidth=2.0, markersize=5,
                    label="with sliding window")
        cu = cutoff.get(d, {})
        if cu.get("en"):
            ax.axvline(cu["en"], color="#333333", linestyle=":", linewidth=1.6)
            ax.text(cu["en"], 1.04, f" ~512 tok. limit\n English", fontsize=7.5,
                    ha="left", va="bottom")
        if cu.get("sr"):
            ax.axvline(cu["sr"], color="#8A5A00", linestyle=":", linewidth=1.6)
            ax.text(cu["sr"], 0.88, " Serbian\n (Cyrillic)", fontsize=7.5,
                    ha="right", va="bottom", color="#8A5A00")
        ax.set_ylim(-0.04, 1.12)
        ax.legend(fontsize=8, frameon=False, loc="lower left")
        style(ax, nice(d), "payload position in document (characters)",
              "ratio of detected attacks" if d == dets[0] else "")
    fig.suptitle("Same attack, pushed further down in the document", fontsize=13, y=1.02)
    save(fig, "fig2_t3_position.png")


# ---------------------------------------------------------------------------
# FIGURE 3 — T2: Language and script at English-calibrated threshold
# ---------------------------------------------------------------------------
def fig3(fpr_target: float = 0.01) -> None:
    print("[fig3] T2 — language and script")
    rows = load("t2_corrected.csv")
    if not rows:
        return
    sel = [r for r in rows if r.get("family") == "L_jezik_pismo"
           and abs(f(r["fpr_target"]) - fpr_target) < 1e-9]
    if not sel:
        print("  no family L rows — is T2 completed?")
        return
    by = defaultdict(dict)
    for r in sel:
        by[r["detector"]][(r["ref"], r["condition"])] = r
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(4.6 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        conds, vals, errs, cols = [], [], [], []
        seen = set()
        for (ref, cond), r in by[d].items():
            for name, key in ((ref, "fpr_ref"), (cond, "fpr_cond")):
                if name in seen:
                    continue
                seen.add(name)
                conds.append(name)
                vals.append(f(r[key]))
                errs.append(0.0)
                cols.append({"en_parallel": C_GREY, "en_orig": C_GREY,
                             "sr_latn_orig": C_BEN, "sr_cyrl_orig": C_MAL}.get(name, C_GREY))
        idx = {"en_parallel": 0, "en_orig": 0, "sr_latn_orig": 1, "sr_cyrl_orig": 2}
        z = sorted(zip(conds, vals, cols), key=lambda t: idx.get(t[0], 9))
        conds, vals, cols = [list(t) for t in zip(*z)]
        pretty = {"en_parallel": "English\n(same content)", "en_orig": "English\n(AgentDojo)",
                  "sr_latn_orig": "Serbian\nLATIN", "sr_cyrl_orig": "Serbian\nCYRILLIC"}
        ax.bar(range(len(conds)), vals, color=cols, width=0.62,
               edgecolor="white", linewidth=1.2)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.015, f"{v:.2f}", ha="center", fontsize=9)
        ax.axhline(fpr_target, color="black", linestyle="--", linewidth=1.2)
        ax.text(len(conds) - 0.4, fpr_target + 0.012,
                f"threshold set here ({fpr_target:.0%})", fontsize=7.5, ha="right")
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels([pretty.get(c, c) for c in conds], fontsize=8)
        ax.set_ylim(0, max(1.05, max(vals) * 1.2))
        style(ax, nice(d), "", "ratio of BENIGN text\nblocked" if d == dets[0] else "")
    fig.suptitle("Threshold calibrated on English, evaluated on Serbian text", fontsize=13, y=1.02)
    save(fig, "fig3_t2_language_script.png")


# ---------------------------------------------------------------------------
# FIGURE 4 — T2: Dose-response curve
# ---------------------------------------------------------------------------
def fig4(fpr_target: float = 0.01) -> None:
    print("[fig4] T2 — how many substitutions are enough")
    rows = load("t2_corrected.csv")
    if not rows:
        return
    sel = [r for r in rows if r.get("family") == "kriva_deskriptivno"
           and abs(f(r["fpr_target"]) - fpr_target) < 1e-9]
    if not sel:
        print("  descriptive curve not found")
        return

    def budget(c: str):
        t = c.rsplit("_", 1)[-1]
        if t.endswith("%"):
            return None
        try:
            return int(t.replace("ch", ""))
        except ValueError:
            return None

    fams = {"en_mix_": ("English + Cyrillic homoglyphs", C_GREY),
            "sr_latn_mix_": ("Serbian Latin + Cyrillic homoglyphs", C_BEN),
            "sr_cyrl_mix_": ("Serbian Cyrillic + Latin homoglyphs", C_MAL)}
    by = defaultdict(lambda: defaultdict(list))
    for r in sel:
        for pref in fams:
            if r["condition"].startswith(pref):
                b = budget(r["condition"])
                if b is not None:
                    by[r["detector"]][pref].append((b, f(r["fpr_cond"])))
    dets = list(by)
    if not dets:
        return
    fig, axes = plt.subplots(1, len(dets), figsize=(4.8 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        for pref, (lab, col) in fams.items():
            pts = sorted(by[d].get(pref, []))
            if not pts:
                continue
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o",
                    color=col, linewidth=2.0, markersize=5, label=lab)
        ax.axhline(fpr_target, color="black", linestyle="--", linewidth=1.1)
        ax.set_ylim(-0.04, 1.08)
        ax.legend(fontsize=7.5, frameon=False, loc="lower right")
        style(ax, nice(d), "number of substituted characters",
              "ratio of blocked\nbenign text" if d == dets[0] else "")
    fig.suptitle("How many invisible substitutions trigger benign text blockages",
                 fontsize=13, y=1.02)
    save(fig, "fig4_t2_curve.png")


# ---------------------------------------------------------------------------
# FIGURE 5 — T4: Benchmark templates vs wild attacks
# ---------------------------------------------------------------------------
def fig5(fpr_target: float = 0.01) -> None:
    print("[fig5] T4 — AgentDojo vs IPI Arena")
    rows = load("t4_corrected.csv")
    if not rows:
        return
    sel = [r for r in rows if abs(f(r["fpr_target"]) - fpr_target) < 1e-9
           and r["mode"] in ("naive", "chunked")]
    if not sel:
        return
    order = [("agentdojo_imp", "naive"), ("agentdojo_raw", "naive"),
             ("ipi_arena", "naive"), ("ipi_arena", "chunked")]
    pretty = {("agentdojo_imp", "naive"): "AgentDojo\nin wrapper",
              ("agentdojo_raw", "naive"): "AgentDojo\nraw payload",
              ("ipi_arena", "naive"): "IPI Arena\n(effective on Qwen)",
              ("ipi_arena", "chunked"): "IPI Arena\n+ sliding window"}
    cols = {("agentdojo_imp", "naive"): C_GREY, ("agentdojo_raw", "naive"): C_GREY,
            ("ipi_arena", "naive"): C_MAL, ("ipi_arena", "chunked"): C_ALT}
    by = defaultdict(dict)
    ncl = {}
    for r in sel:
        by[r["detector"]][(r["set"], r["mode"])] = r
        if r["set"] == "ipi_arena":
            ncl[r["detector"]] = (r["n_strings"], r["n_clusters"])
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(4.6 * len(dets), 4.4), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        keys = [k for k in order if k in by[d]]
        vals = [f(by[d][k]["tpr"]) for k in keys]
        lo = [max(0, f(by[d][k]["tpr"]) - f(by[d][k]["tpr_lo"])) for k in keys]
        hi = [max(0, f(by[d][k]["tpr_hi"]) - f(by[d][k]["tpr"])) for k in keys]
        ax.bar(range(len(keys)), vals, color=[cols[k] for k in keys], width=0.62,
               edgecolor="white", linewidth=1.2)
        ax.errorbar(range(len(keys)), vals, yerr=[lo, hi], fmt="none",
                    ecolor="#333333", capsize=4, linewidth=1.4)
        for i, v in enumerate(vals):
            ax.text(i, min(1.04, v + max(hi[i], 0.02) + 0.03), f"{v:.2f}",
                    ha="center", fontsize=9)
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels([pretty[k] for k in keys], fontsize=8)
        ax.set_ylim(0, 1.15)
        n = ncl.get(d)
        sub = f"IPI: {n[0]} strings / {n[1]} behaviors" if n else ""
        style(ax, f"{nice(d)}\n{sub}", "",
              f"ratio of detected attacks\n(at FPR={fpr_target:.0%})" if d == dets[0] else "")
    fig.suptitle("Near-perfect on templates — performance on actual working attacks",
                 fontsize=13, y=1.02)
    save(fig, "fig5_t4_external.png")


# ---------------------------------------------------------------------------
# FIGURE 6 — T3: Cost of windowing, FPR by document length
# ---------------------------------------------------------------------------
def fig6() -> None:
    print("[fig6] T3 — sliding window cost")
    rows = load("t3_defense_cost.csv")
    if not rows:
        return
    by = defaultdict(list)
    for r in rows:
        by[r["detector"]].append((f(r["doc_chars"]), f(r["fpr_naive"]),
                                  f(r["fpr_chunked"]), f(r["windows"])))
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(4.8 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        pts = sorted(by[d])
        x = [p[0] for p in pts]
        ax.plot(x, [p[1] for p in pts], "-o", color=C_GREY, linewidth=2.0,
                markersize=5, label="vanilla detector")
        ax.plot(x, [p[2] for p in pts], "-s", color=C_ALT, linewidth=2.2,
                markersize=5, label="with sliding window")
        for xx, p in zip(x, pts):
            ax.annotate(f"{p[3]:.0f}", (xx, p[2]), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=7, color="#555555")
        ax.set_xscale("log")
        ax.legend(fontsize=8, frameon=False, loc="upper left")
        style(ax, nice(d), "document length (characters, log scale)",
              "ratio of blocked\nbenign text" if d == dets[0] else "")
    fig.suptitle("Cost of windowing: number above point indicates windows per document",
                 fontsize=12, y=1.02)
    save(fig, "fig6_t3_cost.png")


# ---------------------------------------------------------------------------
# FIGURE 7 — T3: Aggregation rules
# ---------------------------------------------------------------------------
def fig7() -> None:
    print("[fig7] T3 — aggregation rules")
    rows = load("t3_aggregation.csv")
    if not rows:
        return
    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by[r["detector"]][r["rule"]][r["kind"]] = f(r["rate"])
    dets = list(by)
    fig, axes = plt.subplots(1, len(dets), figsize=(5.0 * len(dets), 4.2), sharey=True)
    if len(dets) == 1:
        axes = [axes]
    for ax, d in zip(axes, dets):
        rules = list(by[d])
        kinds = sorted({k for r in by[d].values() for k in r})
        atk = [k for k in kinds if k.startswith("position")]
        ben = [k for k in kinds if k.startswith("carrier")]
        wdt = 0.36
        for i, (grp, lab, col) in enumerate(((atk, "attack caught", C_MAL),
                                             (ben, "benign text blocked", C_BEN))):
            if not grp:
                continue
            vals = [sum(by[d][r].get(k, 0) for k in grp) / len(grp) for r in rules]
            ax.bar([j + (i - 0.5) * wdt for j in range(len(rules))], vals,
                   width=wdt, color=col, label=lab, edgecolor="white", linewidth=1.0)
        ax.set_xticks(range(len(rules)))
        ax.set_xticklabels(rules, fontsize=8)
        ax.set_ylim(0, 1.1)
        ax.legend(fontsize=8, frameon=False)
        style(ax, nice(d), "window aggregation rule",
              "ratio" if d == dets[0] else "")
    fig.suptitle("\"max across windows\" is the most expensive rule — cheaper alternatives exist",
                 fontsize=12, y=1.02)
    save(fig, "fig7_t3_aggregation.png")


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=None,
                    help="e.g., --only 1 2 5   (1b is passed as 1b)")
    ap.add_argument("--fpr", type=float, default=0.01)
    a = ap.parse_args()

    todo = {
        "1": fig1, "1b": fig1b, "2": fig2,
        "3": lambda: fig3(a.fpr), "4": lambda: fig4(a.fpr),
        "5": lambda: fig5(a.fpr), "6": fig6, "7": fig7,
    }
    keys = a.only or list(todo)
    made = 0
    for k in keys:
        if k not in todo:
            print(f"unknown figure: {k}")
            continue
        try:
            todo[k]()
            made += 1
        except Exception as e:                                   # noqa: BLE001
            print(f"  figure {k} FAILED: {type(e).__name__}: {e}")
    print(f"\ndone — attempted {len(keys)}, completed without errors {made}")
    print(f"figures saved to {FIG}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())