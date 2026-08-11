"""Ucitavanje konfiguracija sa podrskom za nasledjivanje preko `defaults:`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Rekurzivno spaja `override` preko `base`; override uvek pobedjuje."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path) -> dict[str, Any]:
    """Ucitava YAML i razresava lanac `defaults:` (relativno na configs/)."""
    path = Path(path)
    cfg = yaml.safe_load(path.read_text()) or {}
    parent_name = cfg.pop("defaults", None)
    if parent_name is None:
        return cfg
    # `defaults` se trazi prvo pored fajla, pa u configs/
    candidates = [path.parent / parent_name, path.parent.parent / parent_name]
    parent_path = next((c for c in candidates if c.exists()), None)
    if parent_path is None:
        raise FileNotFoundError(f"defaults '{parent_name}' nije nadjen za {path}")
    return _deep_merge(load_config(parent_path), cfg)
