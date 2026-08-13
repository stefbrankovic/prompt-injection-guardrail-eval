"""Figure iz `results/raw/<run>/` u `results/figures/`.

Pravilo iz plana: figure se prave u finalnom kvalitetu od prvog dana, da se
poslednji dan ne trosi na crtanje. Zato ova skripta cita SAMO artefakte koje
je `psiml.eval.sweep` vec zapisao — nikad ne poziva model. Regeneracija svih
figura je `make figures` i traje sekunde.

Fig. 1  TPR/FPR po varijanti i detektoru — "koliko detektor vidi napad".
Fig. 2  Kriva evazije: udeo probijenih napada u zavisnosti od budzeta zamena.
        Ovo je prvi grafik iz MASTERPLAN-a (gate za D2).
Fig. 3  Pad score-a po napadu: pre vs posle pretrage, sa pragom.
Fig. 4  Cin II: porast fertility-ja vs pad score-a (samo ako je pokrenut
        `python -m psiml.analysis.fertility`).

Pokretanje:
    python -m psiml.viz.make_figures                       # svi run-ovi
    python -m psiml.viz.make_figures --run results/raw/cyrevade
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FIG_DIR = Path("results/figures")
plt.rcParams.update({"figure.dpi": 160, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True})


def _load(run: Path) -> tuple[dict, list[dict]]:
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    apath = run / "attacks.jsonl"
    attacks = []
    if apath.exists():
        attacks = [json.loads(l) for l in apath.read_text(encoding="utf-8").splitlines() if l]
    return summary, attacks


def fig_tpr_fpr(summary: dict, out: Path) -> Path | None:
    """Grupisani stubici: TPR full, FPR srafiran - po varijanti."""
    dets = list(summary["detectors"])
    variants = summary["variants"]
    if not dets:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    width = 0.8 / max(1, len(dets))
    for ax, metric, title in zip(axes, ("tpr", "fpr"), ("TPR (attacks)", "FPR (benign)")):
        for i, det in enumerate(dets):
            vals = [summary["detectors"][det]["variants"][v][metric] for v in variants]
            ax.bar([x + i * width for x in range(len(variants))], vals, width, label=det)
        ax.set_xticks([x + 0.4 - width / 2 for x in range(len(variants))])
        ax.set_xticklabels(variants, rotation=20)
        ax.set_ylim(0, 1.05)
        ax.set_title(title)
    axes[0].set_ylabel(f"Detection Rate (treshold {summary['threshold']})")
    axes[1].legend(fontsize=7, loc="upper right")
    fig.suptitle("Detection Rate by Attack Variant", y=1.02)
    fig.tight_layout()
    path = out / "fig1_tpr_fpr_po_varijanti.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_evasion_curve(summary: dict, out: Path) -> Path | None:
    """Udeo napada koji su probili detektor sa najvise b zamena."""
    curves = {
        det: e["search"]["curve"]
        for det, e in summary["detectors"].items()
        if "search" in e and e["search"]
    }
    if not curves:
        return None
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for det, curve in curves.items():
        ax.plot([p["budget"] for p in curve], [p["evasion_rate"] for p in curve],
                marker="o", ms=3, label=det)
    ax.set_xlabel("Perturbation Budget (Replaced Characters)")
    ax.set_ylabel("ASR")   # attack success rate
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Evasion Curve (greedy)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    path = out / "fig2_kriva_evazije.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_score_drop(summary: dict, attacks: list[dict], out: Path) -> Path | None:
    """Pre/posle po napadu — pokazuje da pad nije prosek nego pravilo."""
    if not attacks:
        return None
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for r in attacks:
        if not r.get("detektovan_original", True):
            continue    # detektor ga nije ni video; nije nas uspeh
        ax.plot([0, 1], [r["orig_score"], r["pg2_score"]],
                color="tab:red" if r["evaded"] else "tab:gray", alpha=0.5, lw=0.8)
    ax.axhline(summary["threshold"], ls="--", color="k", lw=1)
    ax.text(1.01, summary["threshold"], "threshold", va="center", fontsize=7)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["original", "after"])
    ax.set_ylabel("Detector Score")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Detector Score Drop per Attack (Red = Evaded)")
    fig.tight_layout()
    path = out / "fig3_pad_scorea.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_fertility(run: Path, out: Path) -> Path | None:
    """Cin II: da li je pad score-a objasnjen fragmentacijom tokena."""
    fpath = run / "fertility.json"
    if not fpath.exists():
        return None
    res = json.loads(fpath.read_text(encoding="utf-8"))
    pairs = res.get("_pairs", [])
    cyr = res.get("_cyrevade", [])
    if not pairs and not cyr:
        return None

    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    if pairs:
        xs = [p["d_fertility"] for p in pairs]
        ys = [p["d_score"] for p in pairs]
        ax.scatter(xs, ys, s=12, alpha=0.5, label="fiksne varijante")
    if cyr:
        ax.scatter([a["fertility_posle"] - a["fertility_pre"] for a in cyr],
                   [a["pg2_score"] - a["orig_score"] for a in cyr],
                   s=14, alpha=0.7, marker="^", label="CyrEvade pretraga")
    # fitovana linija kroz sve tacke (najmanji kvadrati, bez numpy-ja)
    xs = ([p["d_fertility"] for p in pairs]
          + [a["fertility_posle"] - a["fertility_pre"] for a in cyr])
    ys = ([p["d_score"] for p in pairs]
          + [a["pg2_score"] - a["orig_score"] for a in cyr])
    if len(xs) > 2:
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den:
            k = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
            x0, x1 = min(xs), max(xs)
            ax.plot([x0, x1], [my + k * (x0 - mx), my + k * (x1 - mx)],
                    color="k", lw=1, ls="--")
    r = res.get("korelacija_delta", {}).get("pearson")
    ax.set_xlabel("Fertility Increase (Tokens per Word)")
    ax.set_ylabel("Detector Score Change ($\Delta$ Score)")
    ax.axhline(0, color="gray", lw=0.6)
    ax.set_title("Mechanism: Token Fertility Increase vs. Detection Drop"
                 + (f"  (r={r:+.2f})" if r is not None else ""))
    ax.legend(fontsize=7)
    fig.tight_layout()
    path = out / "fig4_fertility.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerisi figure iz results/raw")
    ap.add_argument("--run", type=Path, default=None, help="jedan run; podrazumevano svi")
    ap.add_argument("--out", type=Path, default=FIG_DIR)
    args = ap.parse_args()

    runs = [args.run] if args.run else sorted(
        p.parent for p in Path("results/raw").glob("*/summary.json")
    )
    if not runs:
        print("Nema nijednog results/raw/*/summary.json — prvo pokreni `make baseline`.")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for run in runs:
        summary, attacks = _load(run)
        out = args.out / run.name
        out.mkdir(parents=True, exist_ok=True)
        made = [
            fig_tpr_fpr(summary, out),
            fig_evasion_curve(summary, out),
            fig_score_drop(summary, attacks, out),
            fig_fertility(run, out),
        ]
        for p in made:
            if p:
                print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
