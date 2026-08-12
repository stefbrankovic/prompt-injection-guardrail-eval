"""Ucitavanje skupa injection-a i generisanje varijanti napada.

Do D1 smo radili na tri recenice zakucane u `detector_sanity.py`. To je bilo
dovoljno za smoke test i za ADR-0003, ali nije skup na kome se meri ista sto
ide u rad. Ovde je pravi izvor: injection zadaci iz AgentDojo-a (35 komada,
4 suite-a), izvuceni skriptom `scripts/dump_agentdojo_injections.py`.

Format je JSONL, jedan red po tekstu:

    {"id": "banking__injection_task_0#imp", "suite": "banking",
     "lang": "en", "script": "latn", "label": "attack",
     "wrap": "important", "text": "..."}

`label` je "attack" ili "benign" — kontrolna grupa je u ISTOM formatu, jer bez
FPR-a TPR ne znaci nista (vidi docs/TEORIJA.md, Deo 5).

Varijante (osa 2 napada) se generisu iz ucitanog teksta, ne cuvaju se u fajlu:
    orig      — tekst kakav jeste
    homo25    — 25% zamenljivih pozicija zamenjeno homoglifom, ravnomerno
    homo50    — 50%
    homo100   — sve sto se moze zameniti (gornja granica napada)
Prava CyrEvade pretraga trazi MINIMALAN podskup i radi se posebno; ove
fiksne varijante su referentne tacke na krivoj.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from psiml.attack.homoglyphs import apply_substitution, substitutable_positions

VARIANTS = ("orig", "homo25", "homo50", "homo100")


@dataclass(frozen=True)
class Sample:
    """Jedan tekst iz skupa, sa metapodacima koji idu u svaki izlazni red."""

    id: str
    text: str
    label: str          # "attack" | "benign"
    lang: str = "en"    # "en" | "sr"
    script: str = "latn"  # "latn" | "cyrl"
    suite: str = ""
    wrap: str = "raw"   # "raw" | "important"  (AgentDojo important_instructions omotac)

    @property
    def is_attack(self) -> bool:
        return self.label == "attack"


def load_jsonl(path: str | Path) -> list[Sample]:
    """Ucitava JSONL u listu `Sample`. Nepoznata polja se tiho ignorisu."""
    rows: list[Sample] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        rows.append(
            Sample(
                id=d["id"],
                text=d["text"],
                label=d.get("label", "attack"),
                lang=d.get("lang", "en"),
                script=d.get("script", "latn"),
                suite=d.get("suite", ""),
                wrap=d.get("wrap", "raw"),
            )
        )
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> Path:
    """Upisuje listu dict-ova kao JSONL (UTF-8, bez ASCII escape-ovanja)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def _evenly_spaced(items: list[int], k: int) -> set[int]:
    """Bira `k` pozicija ravnomerno rasporedjenih po listi.

    Ravnomerno, a ne prvih k, da 25% varijanta ne bi bila "pokvaren pocetak
    recenice a ostatak netaknut" — to bi bilo drugaciji napad nego sto mislimo
    da merimo.
    """
    if k <= 0 or not items:
        return set()
    if k >= len(items):
        return set(items)
    step = len(items) / k
    return {items[int(i * step)] for i in range(k)}


def make_variant(text: str, variant: str, strict: bool = True) -> str:
    """Pravi jednu varijantu teksta. `orig` vraca original nepromenjen."""
    if variant == "orig":
        return text
    if not variant.startswith("homo"):
        raise ValueError(f"Nepoznata varijanta: {variant}")
    pct = int(variant[4:])
    positions = substitutable_positions(text, strict=strict)
    k = round(len(positions) * pct / 100)
    return apply_substitution(text, _evenly_spaced(positions, k), strict=strict)


def variant_stats(text: str, strict: bool = True) -> dict:
    """Koliko je teksta uopste napadljivo — ide u tabelu 'prostor napada'."""
    positions = substitutable_positions(text, strict=strict)
    return {
        "len": len(text),
        "substitutable": len(positions),
        "ratio": len(positions) / len(text) if text else 0.0,
    }
