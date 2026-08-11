"""Latinica <-> cirilica homoglif mapa i osnovne operacije nad njom.

Ovo je tehnicko jezgro Cina I. Ovde nema ni modela ni AgentDojo-a — samo
Unicode. Namerno je izdvojeno u zaseban modul bez teskih zavisnosti da bi
moglo da se testira i pokrene na laptopu prvog dana.

Kljucni pojam: "homoglif" je par karaktera koji se razlicito kodiraju u
Unicode-u a u standardnim fontovima izgledaju identicno. Srpska cirilica
deli veci broj takvih grafema sa latinicom nego ijedan drugi zivi jezik
koji koristi cirilicu, jer je srpska latinica (gajica) dizajnirana kao
1:1 preslikavanje srpske cirilice.

Primer: string "Ignore" i "Іgnоrе" (sa cirilicnim І, о, е) su vizuelno
identicni ali imaju razlicite bajtove i razlicito se tokenizuju.
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Osnovna mapa: latinicni karakter -> vizuelno identican cirilicni karakter.
#
# Ukljuceni su SAMO parovi koji su u tipicnim sans-serif fontovima (DejaVu,
# Arial, Helvetica, sistemski UI fontovi) prakticno nerazlucivi. Parovi koji
# se u nekim fontovima razlikuju (npr. latinicno 'i' vs cirilicno 'і' koje
# ima drugaciju tacku) su izostavljeni iz "strict" skupa i stavljeni u
# "loose" skup, da bi se moglo eksperimentisati sa oba nivoa agresivnosti.
# ---------------------------------------------------------------------------

# Strogi skup: pouzdano identicni u vecini fontova.
_STRICT_LOWER: dict[str, str] = {
    "a": "\u0430",  # а CYRILLIC SMALL A
    "e": "\u0435",  # е CYRILLIC SMALL IE
    "o": "\u043e",  # о CYRILLIC SMALL O
    "p": "\u0440",  # р CYRILLIC SMALL ER
    "c": "\u0441",  # с CYRILLIC SMALL ES
    "y": "\u0443",  # у CYRILLIC SMALL U
    "x": "\u0445",  # х CYRILLIC SMALL HA
}
_STRICT_UPPER: dict[str, str] = {
    "A": "\u0410",  # А
    "B": "\u0412",  # В
    "C": "\u0421",  # С
    "E": "\u0415",  # Е
    "H": "\u041d",  # Н
    "K": "\u041a",  # К
    "M": "\u041c",  # М
    "O": "\u041e",  # О
    "P": "\u0420",  # Р
    "T": "\u0422",  # Т
    "X": "\u0425",  # Х
    "Y": "\u0423",  # У
}

# Prosireni skup: identicni u mnogim ali ne svim fontovima. Dodaje pokrivenost
# ali povecava rizik da pazljiv posmatrac u nekom fontu primeti razliku.
_LOOSE_LOWER: dict[str, str] = {
    "i": "\u0456",  # і CYRILLIC SMALL BYELORUSSIAN-UKRAINIAN I
    "j": "\u0458",  # ј CYRILLIC SMALL JE  (izgleda kao latinicno j)
    "s": "\u0455",  # ѕ CYRILLIC SMALL DZE (izgleda kao latinicno s)
}
_LOOSE_UPPER: dict[str, str] = {
    "I": "\u0406",  # І
    "J": "\u0408",  # Ј
    "S": "\u0405",  # Ѕ
}


def build_map(strict: bool = True) -> dict[str, str]:
    """Vraca latinica->cirilica mapu.

    Args:
        strict: ako je True, samo pouzdano-identicni parovi. Ako je False,
            ukljucuje i prosireni skup (veca pokrivenost, veci rizik detekcije
            golim okom).

    Returns:
        dict koji preslikava jedan latinicni karakter u jedan cirilicni.
    """
    m = {**_STRICT_LOWER, **_STRICT_UPPER}
    if not strict:
        m.update(_LOOSE_LOWER)
        m.update(_LOOSE_UPPER)
    return m


def substitutable_positions(text: str, strict: bool = True) -> list[int]:
    """Indeksi karaktera u `text` koji se MOGU zameniti homoglifom.

    Ovo definise prostor pretrage za napad: napad bira PODSKUP ovih pozicija.

    Returns:
        Lista indeksa (rastuca) na kojima stoji zamenljiv latinicni karakter.
    """
    m = build_map(strict)
    return [i for i, ch in enumerate(text) if ch in m]


def apply_substitution(text: str, positions: set[int], strict: bool = True) -> str:
    """Zamenjuje karaktere na zadatim pozicijama cirilicnim homoglifima.

    Args:
        text: originalni (latinicni) string.
        positions: skup indeksa koje treba zameniti. Indeksi koji nisu
            zamenljivi se tiho ignorisu (radi robusnosti pozivaoca).
        strict: koji homoglif skup koristiti.

    Returns:
        Perturbovani string iste duzine i vizuelno (skoro) identican.
    """
    m = build_map(strict)
    out = []
    for i, ch in enumerate(text):
        if i in positions and ch in m:
            out.append(m[ch])
        else:
            out.append(ch)
    return "".join(out)


def substitution_ratio(text: str, strict: bool = True) -> float:
    """Udeo karaktera u `text` koji su uopste zamenljivi (gornja granica napada).

    Korisno za slajd "koliko je teksta zamenljivo" i za normalizaciju budzeta.
    """
    if not text:
        return 0.0
    return len(substitutable_positions(text, strict)) / len(text)


def is_confusable(text: str) -> bool:
    """Heuristika: da li string mesa latinicu i cirilicu (znak potencijalnog napada).

    NE koristi se kao odbrana (odbrana je ActProbe) — sluzi samo kao sanity
    check u testovima i kao naivni baseline detektor u evaluaciji.
    """
    scripts = set()
    for ch in text:
        if ch.isalpha():
            try:
                name = unicodedata.name(ch)
            except ValueError:
                continue
            if "CYRILLIC" in name:
                scripts.add("cyr")
            elif "LATIN" in name:
                scripts.add("lat")
    return {"cyr", "lat"}.issubset(scripts)


def restore_to_latin(text: str, strict: bool = False) -> str:
    """Inverzna operacija: cirilica -> latinica, za normalizacionu baseline odbranu.

    NAPOMENA: ovo je BASELINE odbrana koju u radu pokazujemo kao NEDOVOLJNU za
    srpski (jer bi unistila legitiman srpski tekst). Ovde je implementirana da
    bismo je mogli izmeriti i uporediti sa ActProbe.

    Koristi loose mapu po defaultu jer napad moze koristiti i loose homoglife.
    """
    # Invertujemo mapu: cirilica -> latinica.
    inv = {v: k for k, v in build_map(strict=False).items()}
    return "".join(inv.get(ch, ch) for ch in text)
