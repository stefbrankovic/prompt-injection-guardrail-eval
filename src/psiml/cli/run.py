"""Glavna ulazna tacka. `python -m psiml.cli.run --config configs/experiments/baseline_en.yaml`"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from psiml.utils.io import load_config
from psiml.utils.repro import set_seed, write_run_manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="PSIML eksperiment runner")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None, help="izlazni direktorijum")
    ap.add_argument("-d", "--detector", action="append", default=None,
                    help="pregazi listu detektora iz configa (moze vise puta)")
    ap.add_argument("--limit", type=int, default=None, help="prvih N napada i N benignih")
    ap.add_argument("--search", action="store_true", help="ukljuci CyrEvade pretragu")
    args = ap.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg.get("logging", {}).get("level", "INFO"),
                        format="%(message)s")
    set_seed(cfg["seed"])

    # CLI pregazi config — da se za brzu probu ne dira YAML.
    if args.detector:
        cfg.setdefault("sweep", {})["detectors"] = args.detector
    if args.limit is not None:
        cfg.setdefault("sweep", {})["limit"] = args.limit
    if args.search:
        cfg.setdefault("sweep", {})["search"] = True

    out_dir = args.out or Path(cfg["paths"]["results_raw"]) / args.config.stem
    write_run_manifest(out_dir, cfg)
    logging.info("Run inicijalizovan -> %s", out_dir)

    if "sweep" not in cfg:
        raise SystemExit(f"Config {args.config} nema sekciju `sweep:` — nema sta da se radi.")

    from psiml.eval.sweep import run_sweep

    summary = run_sweep(cfg, out_dir)
    for det, entry in summary["detectors"].items():
        for variant, m in entry["variants"].items():
            print(
                f"{det:<18}{variant:<10}TPR {m['tpr']:.2f}  FPR {m['fpr']:.2f}  "
                f"razdvojenost {m['separation']:.3f}"
            )
        if "search" in entry:
            s = entry["search"]
            print(
                f"{det:<18}{'cyrevade':<10}evazija {s['evasion_rate']:.2f} "
                f"(od {s['n_detektovan']} detektovanih; {s['n_nedetektovan']} "
                f"detektor nije ni video)  medijana budzeta {s['median_budget']}"
            )
    print(f"\nRezultati: {out_dir}")


if __name__ == "__main__":
    main()