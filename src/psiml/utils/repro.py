"""Reproducibilnost: seed-ovanje i beleženje konteksta izvršavanja.

Svaki run mora da zabeleži git SHA, config i seed. Bez toga posle 4 dana
i 60 pokrenutih eksperimenata ne znaš koji je broj odakle došao.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
from datetime import datetime
from pathlib import Path


def set_seed(seed: int) -> None:
    """Seed-uje sve izvore slučajnosti koje koristimo."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def git_sha(short: bool = True) -> str:
    """Trenutni commit. Vraca 'dirty-<sha>' ako ima neispraćenih izmena."""
    try:
        args = ["git", "rev-parse", "--short" if short else "HEAD"]
        if short:
            args.append("HEAD")
        sha = subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.call(["git", "diff", "--quiet"], stderr=subprocess.DEVNULL) != 0
        return f"dirty-{sha}" if dirty else sha
    except Exception:
        return "nogit"


def write_run_manifest(out_dir: str | Path, config: dict) -> Path:
    """Upisuje manifest.json pored rezultata. Zovi ovo na pocetku SVAKOG run-a."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "config": config,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return path
