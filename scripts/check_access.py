#!/usr/bin/env python3
"""Provera pristupa SVIM resursima — pokrenuti VECERAS, pre nego sto krene rad.

Kristina: "za neke detektore mora da se zatrazi pristup, svi dobiju approval
ali moze da potraje par sati pa zatrazite sto pre."

Ova skripta za svaki resurs kaze: OK / TREBA ZATRAZITI PRISTUP / NEMA MREZE.
Cilj je da ujutru ne otkrijete da nesto ceka odobrenje.

Pokretanje:
    python scripts/check_access.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")

from psiml.detectors import REGISTRY, summary_table  # noqa: E402

AGENT_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",  # gated
]


def check_one(repo_id: str) -> tuple[str, str]:
    """Vraca (status, poruka) za jedan HF repo."""
    try:
        from huggingface_hub import model_info
    except ImportError:
        return "SKIP", "huggingface_hub nije instaliran"

    try:
        model_info(repo_id)
        return "OK", "pristup radi"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        low = msg.lower()
        if "gated" in low or "awaiting" in low or "403" in low:
            return "GATED", f"treba zatraziti pristup: https://huggingface.co/{repo_id}"
        if "401" in low or "unauthorized" in low or "token" in low:
            return "AUTH", "nisi ulogovan — pokreni `hf auth login`"
        if "connect" in low or "resolve" in low or "network" in low:
            return "NET", "nema mreze"
        return "ERR", msg[:110]


def main() -> int:
    print("=" * 90)
    print("PROVERA PRISTUPA — pokrenuti veceras, ne ujutru")
    print("=" * 90)
    print()
    print("LESTVICA DETEKTORA (odgovor na Kristinino pitanje 'koji detektor'):")
    print(summary_table())
    print()

    problems: list[str] = []

    print("--- Detektori ---")
    for spec in REGISTRY.values():
        status, msg = check_one(spec.hf_id)
        flag = "gated" if spec.gated else "open "
        print(f"  [{status:<5}] {flag} {spec.hf_id}")
        if status != "OK":
            print(f"          -> {msg}")
            problems.append(spec.hf_id)

    print()
    print("--- Agent modeli ---")
    for repo in AGENT_MODELS:
        status, msg = check_one(repo)
        print(f"  [{status:<5}] {repo}")
        if status != "OK":
            print(f"          -> {msg}")
            problems.append(repo)

    print()
    print("--- Paketi ---")
    for pkg in ["transformers", "torch", "agentdojo", "sklearn", "datasets"]:
        try:
            __import__(pkg)
            print(f"  [OK   ] {pkg}")
        except ImportError:
            print(f"  [MISS ] {pkg}  -> pip install")
            problems.append(pkg)

    print()
    print("=" * 90)
    if problems:
        print(f"PROBLEMA: {len(problems)}. Resiti VECERAS:")
        for p in problems:
            print(f"  - {p}")
        print()
        print("Za gated modele: otvori link, klikni 'Request access', ceka se par sati.")
        return 1
    print("SVE OK — moze da se radi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
