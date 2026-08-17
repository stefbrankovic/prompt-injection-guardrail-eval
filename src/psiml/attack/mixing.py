"""Mesanje pisama u OBA smera — jezgro traka T2.

`attack/homoglyphs.py` radi samo latinica -> cirilica, jer je pisan za napad na
engleski tekst. Za T2 nam treba i obrnut smer: uzeti PRAVI srpski cirilicni
tekst i ubaciti latinicne dvojnike.

Bez oba smera dve hipoteze predvidjaju isto i eksperiment nije nalaz:
    H_pismo    detektor kaznjava cirilicu kao takvu
    H_mesanje  detektor kaznjava MESANJE pisama, svejedno koje je bazno

Vizuelna nevidljivost vazi u oba smera: cirilicno 'а' (U+0430) i latinicno 'a'
(U+0061) su isti glif, pa je smer zamene nebitan za coveka a bitan za tokenizer.
"""
from __future__ import annotations

from psiml.attack.homoglyphs import build_map

DIRECTIONS = ("lat2cyr", "cyr2lat")


def build_reverse_map(strict: bool = True) -> dict[str, str]:
    """Cirilica -> latinica. Inverz mape iz `homoglyphs.build_map`."""
    return {v: k for k, v in build_map(strict).items()}


def _map_for(direction: str, strict: bool) -> dict[str, str]:
    if direction not in DIRECTIONS:
        raise ValueError(f"Smer mora biti jedan od {DIRECTIONS}, dobijeno: {direction}")
    return build_map(strict) if direction == "lat2cyr" else build_reverse_map(strict)


def mixable_positions(text: str, direction: str = "lat2cyr",
                      strict: bool = True) -> list[int]:
    """Indeksi karaktera koji se mogu zameniti u zadatom smeru."""
    m = _map_for(direction, strict)
    return [i for i, ch in enumerate(text) if ch in m]


def apply_mix(text: str, positions: set[int], direction: str = "lat2cyr",
              strict: bool = True) -> str:
    """Zamenjuje karaktere na zadatim pozicijama. Nezamenljivi se ignorisu."""
    m = _map_for(direction, strict)
    return "".join(m[ch] if (i in positions and ch in m) else ch
                   for i, ch in enumerate(text))


def evenly_spaced(items: list[int], k: int) -> set[int]:
    """Ravnomerno rasporedjenih k pozicija (ne prvih k).

    Prvih k bi znacilo "pokvaren pocetak recenice, ostatak netaknut", sto je
    drugaciji napad od onog koji mislimo da merimo.
    """
    if k <= 0 or not items:
        return set()
    if k >= len(items):
        return set(items)
    step = len(items) / k
    return {items[int(i * step)] for i in range(k)}


def mix_budget(text: str, budget: int | str, direction: str = "lat2cyr",
               strict: bool = True) -> tuple[str, int, int]:
    """Primeni budzet zamena na tekst.

    Args:
        budget: broj karaktera (int) ILI procenat kao string ("25%").
            Apsolutni budzeti postoje zbog dozno-odgovorne krive na malim
            vrednostima — "koliko karaktera je dovoljno" je naslovni broj.

    Returns:
        (perturbovan_tekst, stvarno_zamenjeno, ukupno_zamenljivo)
    """
    pos = mixable_positions(text, direction, strict)
    if isinstance(budget, str) and budget.strip().endswith("%"):
        k = round(len(pos) * float(budget.strip()[:-1]) / 100)
    else:
        k = int(budget)
    chosen = evenly_spaced(pos, k)
    return apply_mix(text, chosen, direction, strict), len(chosen), len(pos)


def mixing_ratio(text: str) -> float:
    """Udeo manjinskog pisma medju slovima. 0.0 = cisto, 0.5 = pola-pola.

    Koristi se kao osa na grafiku umesto sirovog broja zamena, da bi tekstovi
    razlicite duzine bili uporedivi.
    """
    cyr = lat = 0
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:
            cyr += 1
        elif o < 0x0250:
            lat += 1
    tot = cyr + lat
    return min(cyr, lat) / tot if tot else 0.0


def script_profile(text: str) -> dict:
    """Brojevi za tabelu: koliko slova, koliko cirilicnih, koliko latinicnih."""
    cyr = lat = other = 0
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:
            cyr += 1
        elif o < 0x0250:
            lat += 1
        else:
            other += 1
    return {"cyr": cyr, "lat": lat, "other": other,
            "mix_ratio": round(mixing_ratio(text), 4)}
