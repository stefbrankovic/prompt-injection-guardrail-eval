"""Srpska cirilica <-> gajica (latinica), deterministicki.

Zasto ovo postoji: bez `sr_latn` skupa ne mozemo da razdvojimo dve ose napada.

    osa 1 = JEZIK   (tekst je stvarno srpski)
    osa 2 = PISMO   (tekst je engleski, samo su code point-ovi cirilicni)

Ako imamo samo `en` i `sr_cyrl` i score padne, ne znamo da li je pao zato sto
detektor ne zna srpski ili zato sto mu se tokenizacija raspala na cirilici.
`sr_latn` je isti jezik u pismu koje detektor sigurno vidi kao "normalno" —
i tek trojka (en, sr_latn, sr_cyrl) daje faktorski dizajn u kome se ta dva
efekta razdvajaju.

Srpska gajica je 1:1 preslikavanje cirilice (osim tri digrafa), pa je ova
konverzija bez gubitka i bez ijedne heuristike — za razliku od, recimo,
ruskog ili bugarskog gde takva mapa ne postoji.
"""
from __future__ import annotations

# Digrafi idu PRVI: lj/nj/dz moraju da se uhvate pre pojedinacnih slova.
_CYR2LAT: dict[str, str] = {
    "љ": "lj", "њ": "nj", "џ": "dž",
    "Љ": "Lj", "Њ": "Nj", "Џ": "Dž",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e",
    "ж": "ž", "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "ć",
    "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "č", "ш": "š",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E",
    "Ж": "Ž", "З": "Z", "И": "I", "Ј": "J", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "Ћ": "Ć",
    "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Ш": "Š",
}

# Latinica -> cirilica: digrafi prvi, inace bi "lj" postalo "лј".
_DIGRAPHS = (("dž", "џ"), ("Dž", "Џ"), ("DŽ", "Џ"),
             ("lj", "љ"), ("Lj", "Љ"), ("LJ", "Љ"),
             ("nj", "њ"), ("Nj", "Њ"), ("NJ", "Њ"))
_LAT2CYR: dict[str, str] = {v: k for k, v in _CYR2LAT.items() if len(v) == 1}


def cyr_to_lat(text: str) -> str:
    """Cirilica -> gajica. Karakteri van mape (brojevi, mejlovi, IBAN) prolaze.

    Veliko slovo digrafa: 'Њ' -> 'Nj' ako sledi malo slovo, inace 'NJ'.
    ('ЊЕГОВ' -> 'NJEGOV', 'Његов' -> 'Njegov'.)
    """
    out: list[str] = []
    for i, ch in enumerate(text):
        mapped = _CYR2LAT.get(ch)
        if mapped is None:
            out.append(ch)
            continue
        if len(mapped) == 2 and ch in "ЉЊЏ":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            out.append(mapped.upper() if nxt and nxt.isupper() else mapped)
        else:
            out.append(mapped)
    return "".join(out)


def lat_to_cyr(text: str) -> str:
    """Gajica -> cirilica. Inverzna operacija; digrafi se hvataju prvi."""
    for lat, cyr in _DIGRAPHS:
        text = text.replace(lat, cyr)
    return "".join(_LAT2CYR.get(ch, ch) for ch in text)


def script_of(text: str) -> str:
    """Grubo: kojim pismom je tekst pisan — 'cyrl', 'latn' ili 'mixed'."""
    cyr = sum(1 for ch in text if ch in _CYR2LAT)
    lat = sum(1 for ch in text if ch.isalpha() and ch not in _CYR2LAT and ord(ch) < 0x400)
    if cyr and lat:
        return "mixed" if min(cyr, lat) / (cyr + lat) > 0.15 else ("cyrl" if cyr > lat else "latn")
    return "cyrl" if cyr else "latn"
