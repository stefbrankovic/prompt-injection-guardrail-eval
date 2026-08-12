"""D1/D2 eksperiment: lestvica detektora x jezicke i homoglif varijante.

Jedan prolaz proizvodi sve brojeve Cina I:

  1. `scores.jsonl`  — svaki (detektor, varijanta, tekst) sa score-om.
     Odavde idu TPR, FPR i razdvojenost po varijanti.
  2. `attacks.jsonl` — rezultat CyrEvade pretrage po napadu, u formatu koji je
     dogovoren kao interfejs napad<->odbrana (docs/GIT_WORKFLOW.md).
     Kljucevi su namerno na srpskom jer je tako dogovoreno D1 i ne menja se.
  3. `summary.json`  — agregirane metrike, ulaz za `psiml.viz.make_figures`.

Zasto sve u jednoj skripti: da bi svaki broj u prezentaciji imao tacno jednu
komandu koja ga reprodukuje (docs/decisions/REPRO.md).

Pokretanje ide preko configa:
    python -m psiml.cli.run --config configs/experiments/baseline_en.yaml
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from psiml.attack.homoglyphs import substitutable_positions
from psiml.attack.search import beam_search, greedy_search
from psiml.data import Sample, load_jsonl, make_variant, write_jsonl

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrike
# ---------------------------------------------------------------------------
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def metrics_from_rows(rows: list[dict], threshold: float) -> dict:
    """TPR, FPR i razdvojenost za jedan (detektor, varijanta) par.

    Razdvojenost = prosek napada minus prosek benignih. Ako je blizu nule,
    detektor ne razlikuje napad od normalnog teksta, ma koliko score bio visok.
    """
    atk = [r["score"] for r in rows if r["label"] == "attack"]
    ben = [r["score"] for r in rows if r["label"] == "benign"]
    return {
        "n_attack": len(atk),
        "n_benign": len(ben),
        "tpr": sum(s >= threshold for s in atk) / len(atk) if atk else float("nan"),
        "fpr": sum(s >= threshold for s in ben) / len(ben) if ben else float("nan"),
        "mean_attack_score": _mean(atk),
        "mean_benign_score": _mean(ben),
        "separation": _mean(atk) - _mean(ben) if atk and ben else float("nan"),
    }


# ---------------------------------------------------------------------------
# Deo 1: staticko skorovanje varijanti
# ---------------------------------------------------------------------------
def score_variants(
    detector,
    samples: list[Sample],
    variants: list[str],
    threshold: float,
    strict: bool = True,
) -> tuple[list[dict], dict]:
    """Za svaku varijantu skoruje ceo skup u jednom batch-u."""
    rows: list[dict] = []
    summary: dict[str, dict] = {}
    for variant in variants:
        texts = [make_variant(s.text, variant, strict=strict) for s in samples]
        t0 = time.time()
        scores = detector.score_many(texts)
        dt = time.time() - t0
        vrows = [
            {
                "detector": detector.name,
                "variant": variant,
                "id": s.id,
                "suite": s.suite,
                "lang": s.lang,
                "script": s.script,
                "wrap": s.wrap,
                "label": s.label,
                "score": round(float(sc), 6),
                "flagged": bool(sc >= threshold),
                "text": t,
            }
            for s, t, sc in zip(samples, texts, scores)
        ]
        rows.extend(vrows)
        summary[variant] = metrics_from_rows(vrows, threshold)
        summary[variant]["seconds"] = round(dt, 2)
        log.info(
            "%s / %-8s TPR %.2f FPR %.2f razdvojenost %.3f (%.1fs)",
            detector.name, variant, summary[variant]["tpr"],
            summary[variant]["fpr"], summary[variant]["separation"], dt,
        )
    return rows, summary


# ---------------------------------------------------------------------------
# Deo 2: CyrEvade pretraga — minimalan budzet po napadu
# ---------------------------------------------------------------------------
def search_attacks(
    detector,
    samples: list[Sample],
    threshold: float,
    max_budget: int | None = None,
    strict: bool = True,
    algo: str = "greedy",
    beam_width: int = 5,
) -> list[dict]:
    """Pusta pretragu na svaki napad; vraca redove u dogovorenom interfejsu."""
    fn = greedy_search if algo == "greedy" else beam_search
    kwargs = {"beam_width": beam_width} if algo == "beam" else {}
    out: list[dict] = []
    attacks = [s for s in samples if s.is_attack]
    for i, s in enumerate(attacks, 1):
        t0 = time.time()
        res = fn(
            s.text,
            detector.score,
            threshold=threshold,
            max_budget=max_budget,
            strict=strict,
            score_many_fn=detector.score_many,
            **kwargs,
        )
        out.append(
            {
                "injection_id": s.id,
                "jezik": s.lang,
                "pismo": s.script,
                "varijanta": f"cyrevade_{algo}",
                "tekst": res.perturbed,
                "budget": res.budget,
                "pg2_score": round(float(res.final_score), 6),
                "evaded": bool(res.evaded),
                # Ako detektor NIJE ni video original, taj napad ne sme da ulazi
                # u stopu evazije — inace merimo rupu u detektoru kao nas uspeh.
                "detektovan_original": bool(res.orig_score >= threshold),
                # dodatna polja (odbrambena strana ih sme ignorisati)
                "detector": detector.name,
                "orig_score": round(float(res.orig_score), 6),
                "n_substitutable": len(substitutable_positions(res.original, strict=strict)),
                "trace": [[p, round(float(sc), 6)] for p, sc in res.trace],
                "seconds": round(time.time() - t0, 2),
            }
        )
        log.info(
            "[%d/%d] %s  %.3f -> %.3f  budzet %d  %s",
            i, len(attacks), s.id, res.orig_score, res.final_score,
            res.budget, "EVADED" if res.evaded else "-",
        )
    return out


def search_summary(rows: list[dict], max_budget: int) -> dict:
    """Kriva evazije nad napadima koje je detektor UOPSTE video.

    Napadi koje detektor ni u originalu ne prijavljuje broje se odvojeno
    (`n_nedetektovan`). Oni su nalaz o detektoru — ADR-0003, granica
    injection-vs-jailbreak — ali nisu zasluga homoglif napada.
    """
    if not rows:
        return {}
    det = [r for r in rows if r.get("detektovan_original", True)]
    if not det:
        return {"n": len(rows), "n_detektovan": 0, "n_nedetektovan": len(rows), "curve": []}
    curve = [
        {"budget": b, "evasion_rate": sum(1 for r in det if r["evaded"] and r["budget"] <= b) / len(det)}
        for b in range(0, max_budget + 1)
    ]
    budgets = sorted(r["budget"] for r in det if r["evaded"])
    return {
        "n": len(rows),
        "n_detektovan": len(det),
        "n_nedetektovan": len(rows) - len(det),
        "evasion_rate": sum(1 for r in det if r["evaded"]) / len(det),
        "median_budget": budgets[len(budgets) // 2] if budgets else None,
        "mean_orig_score": _mean([r["orig_score"] for r in det]),
        "mean_final_score": _mean([r["pg2_score"] for r in det]),
        "curve": curve,
    }


# ---------------------------------------------------------------------------
# Orkestracija
# ---------------------------------------------------------------------------
def run_sweep(cfg: dict, out_dir: str | Path) -> dict:
    """Cita `cfg['sweep']`, pise tri fajla u `out_dir`, vraca summary dict."""
    from psiml.detectors import get_detector

    sc = cfg.get("sweep", {})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    threshold = float(sc.get("threshold", 0.5))
    strict = bool(cfg.get("attack", {}).get("strict_homoglyphs", True))
    variants = list(sc.get("variants", ["orig"]))
    limit = sc.get("limit")

    samples: list[Sample] = []
    for path in sc.get("data", []):
        samples.extend(load_jsonl(path))
    if not samples:
        raise SystemExit(
            "Prazan skup. Prvo pokreni: python scripts/dump_agentdojo_injections.py"
        )
    if limit:
        atk = [s for s in samples if s.is_attack][:limit]
        ben = [s for s in samples if not s.is_attack][:limit]
        samples = atk + ben
    log.info(
        "Skup: %d napada, %d benignih",
        sum(s.is_attack for s in samples), sum(not s.is_attack for s in samples),
    )

    all_rows: list[dict] = []
    all_attacks: list[dict] = []
    summary: dict = {
        "threshold": threshold,
        "variants": variants,
        "strict_homoglyphs": strict,
        "n_attack": sum(s.is_attack for s in samples),
        "n_benign": sum(not s.is_attack for s in samples),
        "detectors": {},
    }

    for key in sc.get("detectors", ["mock"]):
        det = get_detector(
            key,
            device=cfg.get("device", "cpu"),
            batch_size=int(cfg.get("eval", {}).get("batch_size", 16)),
        )
        rows, per_variant = score_variants(det, samples, variants, threshold, strict)
        all_rows.extend(rows)
        entry = {"variants": per_variant}

        if sc.get("search"):
            arows = search_attacks(
                det, samples, threshold,
                max_budget=sc.get("max_budget"),
                strict=strict,
                algo=str(cfg.get("attack", {}).get("search", "greedy")),
                beam_width=int(cfg.get("attack", {}).get("beam_width", 5)),
            )
            all_attacks.extend(arows)
            entry["search"] = search_summary(arows, int(sc.get("max_budget") or 20))
        summary["detectors"][key] = entry

    write_jsonl(out / "scores.jsonl", all_rows)
    if all_attacks:
        write_jsonl(out / "attacks.jsonl", all_attacks)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Zapisano -> %s", out)
    return summary
