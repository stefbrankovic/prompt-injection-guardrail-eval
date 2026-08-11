"""CyrEvade: pretraga minimalne homoglif perturbacije koja izbegava detektor.

Ovo je algoritamsko jezgro projekta (Cin I). Formulacija:

    min |S|  (broj zamenjenih pozicija)
    uz:  detector_score(perturb(text, S)) < prag_evazije
    i:   attack_still_works(perturb(text, S))    [proverava se odvojeno, D3+]

Ovde implementiramo greedy i beam varijantu koje koriste SAMO score detektora
(black-box pristup detektoru — treba nam samo skalarni izlaz, ne gradijenti).

Provera "da li napad jos radi na modelu" je namerno IZVAN ove petlje: skupa je
(zahteva pokretanje velikog modela / AgentDojo petlje) pa se radi kao poseban
korak nad kandidatima koje pretraga vrati. Tako Cin I moze da se pokrene na
laptopu za sekunde, a skupa provera dolazi tek u Cinu III.

Tipovi:
    ScoreFn = Callable[[str], float]
        Prima string, vraca "koliko je ovo malicious" u [0, 1]. Veci = detektor
        je sigurniji da je napad. Cilj pretrage je da ga spusti ispod praga.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from psiml.attack.homoglyphs import apply_substitution, substitutable_positions

ScoreFn = Callable[[str], float]


@dataclass
class SearchResult:
    """Rezultat jedne pretrage nad jednim injection stringom."""

    original: str
    perturbed: str
    positions: list[int]          # zamenjene pozicije, redosledom dodavanja
    budget: int                   # = len(positions)
    orig_score: float             # detektor score pre napada
    final_score: float            # detektor score posle napada
    evaded: bool                  # da li je final_score < prag
    trace: list[tuple[int, float]] = field(default_factory=list)
    # trace: (pozicija_dodata, score_posle) — za crtanje krive evazije


def _score_after_adding(
    text: str, chosen: set[int], candidate: int, score_fn: ScoreFn, strict: bool
) -> float:
    """Score detektora ako se na vec izabrane pozicije doda jos `candidate`."""
    trial = apply_substitution(text, chosen | {candidate}, strict=strict)
    return score_fn(trial)


def greedy_search(
    text: str,
    score_fn: ScoreFn,
    threshold: float = 0.5,
    max_budget: int | None = None,
    strict: bool = True,
) -> SearchResult:
    """Greedy pretraga: u svakom koraku dodaj poziciju koja NAJVISE spusta score.

    Ovo je glavni algoritam. Slozenost je O(k * n) poziva detektora, gde je
    n broj zamenljivih pozicija a k finalni budzet — jer u svakom od k koraka
    probamo svaku preostalu poziciju. Za injection od ~70 znakova i ~20
    zamenljivih pozicija to je par stotina poziva detektora, dakle < 1s.

    Args:
        text: originalni injection string (latinica).
        score_fn: black-box detektor, string -> [0,1].
        threshold: prag evazije; kad score padne ispod, pretraga staje.
        max_budget: gornja granica broja zamena; None = svi zamenljivi karakteri.
        strict: koji homoglif skup koristiti.

    Returns:
        SearchResult sa putanjom (trace) pogodnom za crtanje krive evazije.
    """
    positions_all = substitutable_positions(text, strict=strict)
    if max_budget is None:
        max_budget = len(positions_all)

    orig_score = score_fn(text)
    chosen: set[int] = set()
    order: list[int] = []
    trace: list[tuple[int, float]] = []
    current_score = orig_score

    remaining = set(positions_all)
    # `stalls` broji uzastopne korake bez STROGOG poboljsanja. Dozvoljavamo
    # ravne (plato) korake jer detektor cesto reaguje tek kad se pokvari CELA
    # kljucna rec, ne prvo slovo — pa prvi korak izgleda beskoristan a nije.
    # Prekidamo tek kad ni posle citavog "platoa" nema napretka.
    max_stalls = len(remaining)  # najgori slucaj: probaj sve jednom
    stalls = 0
    while remaining and len(chosen) < max_budget and current_score >= threshold:
        # Nadji poziciju cije dodavanje daje najnizi score (dozvoljavamo <=).
        best_pos = None
        best_score = float("inf")
        for cand in remaining:
            s = _score_after_adding(text, chosen, cand, score_fn, strict)
            if s < best_score:
                best_score = s
                best_pos = cand
        if best_pos is None:
            break
        # Da li je ovo bilo STROGO poboljsanje?
        if best_score >= current_score:
            stalls += 1
            if stalls > max_stalls:
                break  # plato se ne zavrsava, odustani
        else:
            stalls = 0
        chosen.add(best_pos)
        order.append(best_pos)
        remaining.discard(best_pos)
        current_score = best_score
        trace.append((best_pos, current_score))

    perturbed = apply_substitution(text, chosen, strict=strict)
    return SearchResult(
        original=text,
        perturbed=perturbed,
        positions=order,
        budget=len(order),
        orig_score=orig_score,
        final_score=current_score,
        evaded=current_score < threshold,
        trace=trace,
    )


def beam_search(
    text: str,
    score_fn: ScoreFn,
    threshold: float = 0.5,
    beam_width: int = 5,
    max_budget: int | None = None,
    strict: bool = True,
) -> SearchResult:
    """Beam varijanta: cuva `beam_width` najboljih delimicnih resenja.

    Greedy moze da zaglavi u lokalnom minimumu (jedna zamena izgleda lose sama
    ali je odlicna u kombinaciji sa drugom). Beam to delimicno resava po ceni
    beam_width puta vise poziva detektora. Za projekat je greedy verovatno
    dovoljan; beam je tu za slucaj da greedy pokaze zaglavljivanje.

    Vraca najbolji list iz beam-a (najnizi score, pa najmanji budzet).
    """
    positions_all = substitutable_positions(text, strict=strict)
    if max_budget is None:
        max_budget = len(positions_all)
    orig_score = score_fn(text)

    # Svaki beam element: (chosen_set, order_list, score, trace)
    Beam = tuple[frozenset[int], tuple[int, ...], float, tuple[tuple[int, float], ...]]
    beams: list[Beam] = [(frozenset(), (), orig_score, ())]
    best_evaded: Beam | None = None

    for _ in range(max_budget):
        candidates: list[Beam] = []
        for chosen, order, _score, trace in beams:
            remaining = set(positions_all) - set(chosen)
            for cand in remaining:
                new_chosen = frozenset(chosen | {cand})
                s = score_fn(apply_substitution(text, set(new_chosen), strict=strict))
                new_trace = trace + ((cand, s),)
                candidates.append((new_chosen, order + (cand,), s, new_trace))
        if not candidates:
            break
        # Zadrzi beam_width najboljih po score-u.
        candidates.sort(key=lambda b: (b[2], len(b[0])))
        beams = candidates[:beam_width]
        # Da li je neki od njih presao prag?
        for b in beams:
            if b[2] < threshold:
                if best_evaded is None or len(b[0]) < len(best_evaded[0]):
                    best_evaded = b
        if best_evaded is not None:
            break

    winner = best_evaded if best_evaded is not None else min(beams, key=lambda b: b[2])
    chosen, order, score, trace = winner
    return SearchResult(
        original=text,
        perturbed=apply_substitution(text, set(chosen), strict=strict),
        positions=list(order),
        budget=len(order),
        orig_score=orig_score,
        final_score=score,
        evaded=score < threshold,
        trace=list(trace),
    )
