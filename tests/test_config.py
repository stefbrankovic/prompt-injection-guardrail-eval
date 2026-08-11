"""Smoke test: konfiguracije se ucitavaju i nasledjivanje radi.

Ovaj test postoji da bi `pytest` imao sta da pokrene od prvog dana.
Ako `pytest -q` ne prolazi, nista se ne commit-uje.
"""
from pathlib import Path

from psiml.utils.io import load_config

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def test_default_loads():
    cfg = load_config(CONFIGS / "default.yaml")
    assert cfg["seed"] == 1337


def test_experiment_overrides_default():
    cfg = load_config(CONFIGS / "experiments" / "smoke.yaml")
    assert cfg["seed"] == 1337          # nasledjeno
    assert cfg["eval"]["n_samples"] == 4  # pregazeno
    assert cfg["model"]["max_new_tokens"] == 16
