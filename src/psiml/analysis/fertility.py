"""Cin II — mehanizam: zasto homoglif napad radi.

Teza koju ovaj modul meri:

    Homoglif ne menja znacenje i ne menja izgled. Menja SAMO to kako tokenizer
    isece tekst. Ako je pad score-a detektora objasnjen porastom fragmentacije,
    onda napad ne radi "nekom magijom" nego zato sto mali klasifikator prepozna
    NIZ TOKENA, a ne znacenje. To je merljiva tvrdnja i ovde se meri.

Fertility (plodnost) = broj tokena / broj reci. Engleski tekst u DeBERTa
tokenizeru ima ~1.3; ista recenica sa cirilicnim homoglifima se raspada na
komadice i fertility skoci na 3-5, jer parovi tipa "In" + "gnore" vise ne
postoje u recniku pa tokenizer pada na pojedinacne bajtove/karaktere.

Merimo dve stvari:
  1. staticki: fertility svake varijante (orig/homo25/50/100) i njena
     korelacija sa score-om detektora -> scatter sa fitovanom linijom;
  2. po napadu: delta fertility (posle CyrEvade pretrage minus pre) naspram
     delta score-a -> da li vece raspadanje znaci veci pad.

Korelacije su Pearson (linearna) i Spearman (monotona, otporna na outliere).
Racunaju se ovde rucno da modul ne zavisi od scipy-ja.

Pokretanje:
    python -m psiml.analysis.fertility --run results/raw/cyrevade
    python -m psiml.analysis.fertility --run results/raw/cyrevade -d promptguard2_86m
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from psiml.detectors import REGISTRY


# ---------------------------------------------------------------------------
# Statistika (bez scipy-ja: 20 linija, nula zavisnosti)
# ---------------------------------------------------------------------------
def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def pearson(xs: list[float], ys: list[float]) -> float:
    """Linearna korelacija. -1..1; 0 = nema linearne veze."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


def _ranks(xs: list[float]) -> list[float]:
    """Rangovi sa prosekom za izjednacene vrednosti (kako Spearman trazi)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    """Monotona korelacija = Pearson nad rangovima. Otporna na outliere."""
    return pearson(_ranks(xs), _ranks(ys))


# ---------------------------------------------------------------------------
# Fertility
# ---------------------------------------------------------------------------
def load_tokenizer(detector_key: str):
    """Tokenizer TOG detektora — ne bilo koji.

    Fertility je svojstvo para (tekst, tokenizer). Meriti ga tudjim tokenizerom
    znaci meriti nesto sto sa nasim detektorom nema veze.
    """
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(REGISTRY[detector_key].hf_id)


def fertility(text: str, tokenizer) -> float:
    """Broj tokena po reci. Reci = razmakom razdvojeni komadi.

    Specijalni tokeni ([CLS], [SEP]) se izbacuju jer su konstanta koja bi
    kratke tekstove vestacki podigla.
    """
    words = [w for w in text.split() if w]
    if not words:
        return float("nan")
    n_tok = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    return n_tok / len(words)


def analyze_run(run: Path, detector_key: str, tokenizer) -> dict:
    """Racuna fertility za `scores.jsonl` i `attacks.jsonl` jednog run-a."""
    rows = [
        json.loads(line)
        for line in (run / "scores.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    rows = [r for r in rows if r["detector"] == detector_key]
    if not rows:
        raise SystemExit(f"U {run} nema redova za detektor '{detector_key}'.")

    for r in rows:
        r["fertility"] = fertility(r["text"], tokenizer)

    out: dict = {"detector": detector_key, "n": len(rows), "po_varijanti": {}}

    # 1) staticki deo: fertility i score po varijanti, samo nad napadima
    attacks = [r for r in rows if r["label"] == "attack"]
    for variant in sorted({r["variant"] for r in attacks}):
        sub = [r for r in attacks if r["variant"] == variant]
        out["po_varijanti"][variant] = {
            "mean_fertility": _mean([r["fertility"] for r in sub]),
            "mean_score": _mean([r["score"] for r in sub]),
            "n": len(sub),
        }

    f = [r["fertility"] for r in attacks]
    s = [r["score"] for r in attacks]
    out["korelacija_svi_napadi"] = {
        "pearson": pearson(f, s), "spearman": spearman(f, s), "n": len(f),
    }

    # 2) uparen deo: ista recenica pre i posle -> delta fertility vs delta score
    by_id: dict[str, dict] = {}
    for r in attacks:
        by_id.setdefault(r["id"], {})[r["variant"]] = r
    pairs = []
    for _id, vs in by_id.items():
        if "orig" not in vs:
            continue
        for variant, r in vs.items():
            if variant == "orig":
                continue
            pairs.append({
                "id": _id, "variant": variant,
                "d_fertility": r["fertility"] - vs["orig"]["fertility"],
                "d_score": r["score"] - vs["orig"]["score"],
            })
    if pairs:
        df = [p["d_fertility"] for p in pairs]
        ds = [p["d_score"] for p in pairs]
        out["korelacija_delta"] = {
            "pearson": pearson(df, ds), "spearman": spearman(df, ds), "n": len(df),
        }
    out["_pairs"] = pairs

    # 3) rezultat CyrEvade pretrage, ako postoji
    apath = run / "attacks.jsonl"
    if apath.exists():
        arows = [json.loads(l) for l in apath.read_text(encoding="utf-8").splitlines() if l]
        arows = [a for a in arows if a.get("detector") == detector_key
                 and a.get("detektovan_original", True) and a.get("tekst_original")]
        for a in arows:
            a["fertility_pre"] = fertility(a["tekst_original"], tokenizer)
            a["fertility_posle"] = fertility(a["tekst"], tokenizer)
        if arows:
            df = [a["fertility_posle"] - a["fertility_pre"] for a in arows]
            ds = [a["pg2_score"] - a["orig_score"] for a in arows]
            out["korelacija_cyrevade"] = {
                "pearson": pearson(df, ds), "spearman": spearman(df, ds), "n": len(df),
                "mean_d_fertility": _mean(df),
                "mean_budget": _mean([float(a["budget"]) for a in arows]),
            }
        out["_cyrevade"] = arows
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Cin II: fertility <-> pad score-a")
    ap.add_argument("--run", type=Path, required=True, help="npr. results/raw/cyrevade")
    ap.add_argument("-d", "--detector", default=None, help="podrazumevano: prvi u run-u")
    args = ap.parse_args()

    if args.detector is None:
        summary = json.loads((args.run / "summary.json").read_text(encoding="utf-8"))
        args.detector = next(iter(summary["detectors"]))

    tok = load_tokenizer(args.detector)
    res = analyze_run(args.run, args.detector, tok)

    print(f"Detektor: {res['detector']}   tekstova: {res['n']}")
    print(f"{'varijanta':<12}{'fertility':>11}{'score':>9}{'n':>5}")
    print("-" * 40)
    for v, m in res["po_varijanti"].items():
        print(f"{v:<12}{m['mean_fertility']:>11.2f}{m['mean_score']:>9.3f}{m['n']:>5}")
    for key in ("korelacija_svi_napadi", "korelacija_delta", "korelacija_cyrevade"):
        if key in res:
            c = res[key]
            print(f"{key:<26} pearson {c['pearson']:+.3f}  "
                  f"spearman {c['spearman']:+.3f}  (n={c['n']})")

    dest = args.run / "fertility.json"
    dest.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nZapisano: {dest}")
    print("Figura: python -m psiml.viz.make_figures --run", args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
