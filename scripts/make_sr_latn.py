#!/usr/bin/env python3
"""Pravi `sr_latn` skup iz prevedenog `sr_cyrl` skupa — treca tacka dizajna.

Merenje sa samo `en` i `sr_cyrl` je konfaundirano: ako score padne, ne znas da
li je krivo pismo ili jezik. Ovaj fajl je kontrola: ISTI srpski tekst, pismo
koje detektor vidi kao obicnu latinicu.

    en        engleski jezik, latinica     <- referenca
    sr_latn   srpski jezik, latinica       <- izoluje efekat JEZIKA (osa 1)
    sr_cyrl   srpski jezik, cirilica       <- jezik + pismo
    *_homoNN  bilo koji od gornjih sa homoglifima  <- osa 2

Prevodi se rucno samo cirilicna verzija; latinicna je deterministicka.

Pokretanje:
    python scripts/make_sr_latn.py
    python scripts/make_sr_latn.py --in data/injections/agentdojo_sr_cyrl.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.data import load_jsonl, write_jsonl  # noqa: E402
from psiml.translit import cyr_to_lat  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="sr_cyrl -> sr_latn")
    ap.add_argument("--in", dest="src", type=Path,
                    default=Path("data/injections/agentdojo_sr_cyrl.jsonl"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.src.exists():
        print(f"Nema {args.src} — prvo prevedi skup i pokreni "
              f"`dump_agentdojo_injections.py --wrap-translations`.", file=sys.stderr)
        return 1

    rows = load_jsonl(args.src)
    out_rows = [
        {
            "id": s.id.replace("#", "@latn#") if "#" in s.id else s.id + "@latn",
            "suite": s.suite, "lang": "sr", "script": "latn",
            "label": s.label, "wrap": s.wrap, "text": cyr_to_lat(s.text),
        }
        for s in rows
    ]
    dest = args.out or args.src.with_name("agentdojo_sr_latn.jsonl")
    write_jsonl(dest, out_rows)
    print(f"{len(out_rows)} redova -> {dest}")
    print("Provera na prvom redu:")
    print("  cyr:", rows[0].text[:70])
    print("  lat:", out_rows[0]["text"][:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
