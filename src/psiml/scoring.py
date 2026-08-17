"""Skorovanje sa kesom, batch-om i klizecim prozorom.

Zasto novi modul umesto diranja `detectors.py`: `detectors.py` se menjao vise
puta i ne zelimo merge konflikt 36 sati pred rok. Ovde se samo OMOTAVA ono sto
postoji, uz fallback ako `score_many` ne postoji.

Klizeci prozor je ovde jer je jedan od tri glavna nalaza Faze 2: HF
`text-classification` pipeline se poziva sa `truncation=True, max_length=512`,
sto znaci da detektor FIZICKI NE VIDI tekst posle ~512 tokena. Realni tool
output (mejl, README, JSON odgovor API-ja) je redovno duzi od toga.

Prozor je definisan u KARAKTERIMA, ne tokenima, i to je namerno:
  - napadac broji karaktere (to je ono sto ubacuje u dokument),
  - a koliko karaktera stane u 512 tokena zavisi od pisma (fertility),
    pa je razlika izmedju en i sr_cyrl deo nalaza, ne greska merenja.
Konverzija se meri u `scripts/f2_t3_window.py` i izvestava se uz svaki broj.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(".cache/scores")


class Scorer:
    """Detektor + kes na disku. Isti tekst se nikad ne skoruje dva puta."""

    def __init__(self, key: str, device: str = "cpu", batch_size: int = 16,
                 cache_dir: Path = CACHE_DIR, use_cache: bool = True) -> None:
        from psiml.detectors import get_detector

        self.key = key
        self.batch_size = batch_size
        self.det = get_detector(key, device=device, batch_size=batch_size)
        self.use_cache = use_cache
        self.path = Path(cache_dir) / f"{key}.json"
        self.cache: dict[str, float] = {}
        if use_cache and self.path.exists():
            try:
                self.cache = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                self.cache = {}
        self._dirty = 0

    @staticmethod
    def _k(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def flush(self) -> None:
        if not self.use_cache or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache), encoding="utf-8")
        self._dirty = 0

    def _raw_batch(self, texts: list[str]) -> list[float]:
        """Batch put ako detektor ima `score_many`, inace jedan po jedan."""
        fn = getattr(self.det, "score_many", None)
        if fn is not None:
            return [float(x) for x in fn(texts)]
        return [float(self.det.score(t)) for t in texts]

    def score(self, texts: list[str], label: str = "") -> list[float]:
        """Skoruje listu tekstova. Kes se puni usput i pise na kraju."""
        todo = [t for t in dict.fromkeys(texts) if self._k(t) not in self.cache]
        for i in range(0, len(todo), self.batch_size):
            chunk = todo[i:i + self.batch_size]
            for t, s in zip(chunk, self._raw_batch(chunk)):
                self.cache[self._k(t)] = s
                self._dirty += 1
            if label and (i // self.batch_size) % 10 == 0:
                print(f"    [{self.key}] {label}: {min(i + self.batch_size, len(todo))}/{len(todo)} novih",
                      flush=True)
        self.flush()
        return [self.cache[self._k(t)] for t in texts]


# ---------------------------------------------------------------------------
# Klizeci prozor
# ---------------------------------------------------------------------------
def windows(text: str, size: int, stride: int) -> list[str]:
    """Deli tekst na preklapajuce prozore od `size` karaktera, korak `stride`.

    Preklapanje postoji da injection presecen na granici ne bi bio propusten
    ni u jednom prozoru. Sa stride = size/2 svaki podniz kraci od size/2 lezi
    citav u bar jednom prozoru.
    """
    if size <= 0 or len(text) <= size:
        return [text]
    out, i = [], 0
    while True:
        out.append(text[i:i + size])
        if i + size >= len(text):
            return out
        i += max(1, stride)


def score_chunked_detail(scorer: Scorer, texts: list[str], size: int, stride: int,
                         label: str = "") -> tuple[list[float], list[int], list[list[float]]]:
    """Kao `score_chunked`, ali vraca i skor SVAKOG prozora, redom.

    Treca povratna vrednost `per[i]` je lista skorova prozora dokumenta `i`.
    Bez nje se iz maksimuma ne moze rekonstruisati nijedno drugo pravilo
    agregacije (top2, broj prozora >= prag), pa se "cena klizeceg prozora"
    ne moze razdvojiti na "cena ideje" i "cena pravila max".

    Nijedan dodatni poziv modela: prozori su isti stringovi koje `score_chunked`
    ionako skoruje, i kes u `Scorer` ih vraca sa diska.
    """
    flat: list[str] = []
    counts: list[int] = []
    for t in texts:
        w = windows(t, size, stride)
        counts.append(len(w))
        flat.extend(w)
    scores = scorer.score(flat, label=label)
    out: list[float] = []
    per: list[list[float]] = []
    i = 0
    for c in counts:
        chunk = scores[i:i + c]
        per.append(chunk)
        out.append(max(chunk))
        i += c
    return out, counts, per


def score_chunked(scorer: Scorer, texts: list[str], size: int, stride: int,
                  label: str = "") -> tuple[list[float], list[int]]:
    """Skor dokumenta = MAKSIMUM po prozorima (odbrana: dovoljan je jedan pogodak).

    Vraca (skorovi, broj_prozora_po_dokumentu). Broj prozora je vazan jer je
    to cena odbrane: N prozora = N sansi za lazno uzbunjivanje, pa FPR raste
    sa duzinom dokumenta. Ta cena se meri, ne pretpostavlja.
    """
    out, counts, _ = score_chunked_detail(scorer, texts, size, stride, label=label)
    return out, counts
