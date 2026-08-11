"""Glavna ulazna tacka. `python -m psiml.cli.run --config configs/experiments/smoke.yaml`"""
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
    args = ap.parse_args()

    cfg = load_config(args.config)
    logging.basicConfig(level=cfg.get("logging", {}).get("level", "INFO"))
    set_seed(cfg["seed"])

    out_dir = args.out or Path(cfg["paths"]["results_raw"]) / args.config.stem
    write_run_manifest(out_dir, cfg)
    logging.info("Run inicijalizovan -> %s", out_dir)

    # TODO: ovde ide poziv ka psiml.eval.runner kad tema bude poznata
    raise SystemExit(0)


if __name__ == "__main__":
    main()
