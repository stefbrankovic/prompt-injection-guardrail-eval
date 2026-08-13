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
BatchScoreFn = Callable[[list[str]], list[float]]


@dataclass
class SearchResult:
    original: str
    perturbed: str
    positions: list[int]
    budget: int
    orig_score: float
    final_score: float
    evaded: bool
    trace: list[tuple[int, float]] = field(default_factory=list)


def _scores_after_adding(
    text: str,
    chosen: set[int],
    candidates: list[int],
    score_fn: ScoreFn,
    strict: bool,
    score_many_fn: BatchScoreFn | None = None,
) -> list[float]:
    trials = [apply_substitution(text, chosen | {c}, strict=strict) for c in candidates]
    if score_many_fn is not None:
        return list(score_many_fn(trials))
    return [score_fn(t) for t in trials]


def greedy_search(
    text: str,
    score_fn: ScoreFn,
    threshold: float = 0.5,
    max_budget: int | None = None,
    strict: bool = True,
    score_many_fn: BatchScoreFn | None = None,
) -> SearchResult:
    positions_all = substitutable_positions(text, strict=strict)
    if max_budget is None:
        max_budget = len(positions_all)

    orig_score = score_many_fn([text])[0] if score_many_fn is not None else score_fn(text)
    chosen: set[int] = set()
    order: list[int] = []
    trace: list[tuple[int, float]] = []
    current_score = orig_score

    remaining = set(positions_all)
    max_stalls = len(remaining)
    stalls = 0
    while remaining and len(chosen) < max_budget and current_score >= threshold:
        cands = sorted(remaining)
        scores = _scores_after_adding(text, chosen, cands, score_fn, strict, score_many_fn)
        if not scores:
            break
        best_score, best_pos = min(zip(scores, cands))
        if best_score >= current_score:
            stalls += 1
            if stalls > max_stalls:
                break
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
    score_many_fn: BatchScoreFn | None = None,
) -> SearchResult:
    positions_all = substitutable_positions(text, strict=strict)
    if max_budget is None:
        max_budget = len(positions_all)
    orig_score = score_many_fn([text])[0] if score_many_fn is not None else score_fn(text)

    Beam = tuple[frozenset[int], tuple[int, ...], float, tuple]
    beams: list[Beam] = [(frozenset(), (), orig_score, ())]
    best_evaded: Beam | None = None

    for _ in range(max_budget):
        expansions = []
        for chosen, order, _score, trace in beams:
            for cand in sorted(set(positions_all) - set(chosen)):
                new_chosen = frozenset(chosen | {cand})
                expansions.append(
                    (new_chosen, order + (cand,), trace,
                     apply_substitution(text, set(new_chosen), strict=strict))
                )
        if not expansions:
            break
        texts = [e[3] for e in expansions]
        scores = list(score_many_fn(texts)) if score_many_fn is not None else [
            score_fn(t) for t in texts
        ]
        candidates = []
        for (new_chosen, new_order, trace, _t), s in zip(expansions, scores):
            candidates.append((new_chosen, new_order, s, trace + ((new_order[-1], s),)))
        candidates.sort(key=lambda b: (b[2], len(b[0])))
        beams = candidates[:beam_width]
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