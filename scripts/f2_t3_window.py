#!/usr/bin/env python3
"""T3 — slepa mrlja od 512 tokena: napad koji radi, odbrana, i cena odbrane.

Sve dosad merene brojke (i nase i Metine u model cardu) dobijene su na
IZOLOVANOM injection tekstu od nekoliko stotina karaktera. Realni tool output
nije takav: mejl, README, JSON odgovor, stranica sa recenzijama. U skupu
IPI Arena napadi idu do ~14.000 karaktera.

HF `text-classification` pipeline se u `detectors.py` poziva sa
`truncation=True, max_length=512`. Sve posle ~512 tokena detektor FIZICKI NE
VIDI. To nije bag naseg koda — to je podrazumevani nacin na koji se ovi
detektori pozivaju, i tako su i deployovani.

Tri merenja:

  1. EFEKTIVNI PROZOR — koliko KARAKTERA stane u 512 tokena, po pismu.
     Ovde se spaja sa fertility pricom: cirilica se deli na vise tokena po
     karakteru, pa je prozor u karakterima KRACI za srpski nego za engleski.
     Isti detektor, ista granica u tokenima, manje procitanog teksta.

  2. NAPAD (pozicija) — isti payload ubacen na rastuce rastojanje od pocetka
     bezopasnog nosaca. Score kao funkcija pozicije. Ocekivan je prag, ne
     glatki pad: dok je payload unutar prozora detektor ga vidi, posle ne.
     Napadac ne mora nista da obfuskuje — samo da ga gurne nize u dokument.

  3. ODBRANA (klizeci prozor) + NJENA CENA — dokument se sece na preklapajuce
     prozore i uzima se maksimum. Napad nestaje. Ali svaki prozor je nova
     prilika za laznu uzbunu, pa FPR raste sa duzinom dokumenta. Ta kriva je
     cena odbrane i meri se na cistim bezopasnim nosacima.

    export PYTHONPATH=src
    python scripts/f2_t3_window.py --detectors deepset promptguard2_86m
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from psiml.data import load_jsonl                                  # noqa: E402
from psiml.metrics import rate_above, threshold_at_fpr             # noqa: E402
from psiml.scoring import Scorer, score_chunked_detail, windows    # noqa: E402

OFFSETS = [0, 250, 500, 1000, 1500, 2000, 3000, 5000, 8000]
DOC_LENS = [500, 1000, 2000, 4000, 8000, 16000]
DETECTORS = ["deepset", "protectai_v2", "promptguard2_86m", "promptguard2_22m"]


def make_carrier(texts: list[str], n_chars: int, seed_offset: int = 0) -> str:
    """Bezopasan nosac zadate duzine, sastavljen od pravih benignih tekstova."""
    parts, i = [], seed_offset
    total = 0
    while total < n_chars:
        t = texts[i % len(texts)]
        parts.append(t)
        total += len(t) + 2
        i += 1
    return "\n\n".join(parts)[:n_chars]


def effective_window(detector_key: str, samples: dict[str, str], max_tokens: int = 512) -> list[dict]:
    """Koliko karaktera stane u `max_tokens` tokena, po pismu/jeziku."""
    from psiml.analysis.fertility import load_tokenizer

    try:
        tok = load_tokenizer(detector_key)
    except Exception as e:                                          # noqa: BLE001
        print(f"  (tokenizer nedostupan za {detector_key}: {type(e).__name__})")
        return []
    out = []
    for name, text in samples.items():
        if not text:
            continue
        ids = tok(text, add_special_tokens=False)["input_ids"]
        tpc = len(ids) / len(text)
        out.append({"detector": detector_key, "corpus": name,
                    "chars": len(text), "tokens": len(ids),
                    "tokens_per_char": round(tpc, 4),
                    "chars_in_512_tokens": int(max_tokens / tpc) if tpc else 0})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacks", type=Path, default=Path("data/injections/agentdojo_en.jsonl"))
    ap.add_argument("--benign-full", type=Path,
                    default=Path("data/injections/agentdojo_benign_full_en.jsonl"))
    ap.add_argument("--sr-cyrl", type=Path, default=Path("data/benign/sr_cyrl.jsonl"))
    ap.add_argument("--detectors", nargs="+", default=DETECTORS)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--n-payloads", type=int, default=10)
    ap.add_argument("--n-carriers", type=int, default=20)
    ap.add_argument("--win", type=int, default=1200, help="prozor odbrane u karakterima")
    ap.add_argument("--stride", type=int, default=600)
    ap.add_argument("--fpr", type=float, default=0.01)
    ap.add_argument("--out", type=Path, default=Path("results"))
    a = ap.parse_args()

    atk = [s for s in load_jsonl(a.attacks) if s.wrap == "important"][:a.n_payloads]
    ben = load_jsonl(a.benign_full)
    ben_texts = [s.text for s in ben]
    sr = load_jsonl(a.sr_cyrl) if a.sr_cyrl.exists() else []
    print(f"payload-a {len(atk)}, benignih {len(ben_texts)}, srpskih {len(sr)}")

    pos_rows, cost_rows, win_rows, summary = [], [], [], []
    wnd_rows: list[dict] = []
    wnd_rows: list[dict] = []      # jedan red po PROZORU -> results/raw/t3_windows.jsonl
    for d in a.detectors:
        sc = Scorer(d, device=a.device, batch_size=a.batch_size)

        # --- 1. efektivni prozor -------------------------------------------
        probes = {"en": " ".join(ben_texts)[:4000]}
        if sr:
            probes["sr_cyrl"] = " ".join(s.text for s in sr)[:4000]
            from psiml.translit import cyr_to_lat
            probes["sr_latn"] = cyr_to_lat(probes["sr_cyrl"])
        win_rows.extend(effective_window(d, probes))

        # --- prag: kalibracija na kratkim benignim tekstovima ---------------
        thr = threshold_at_fpr(sc.score(ben_texts, label="kalibracija"), a.fpr)
        print(f"\n{d}: prag={thr:.6f}")

        # --- 2. napad pozicijom --------------------------------------------
        docs, meta = [], []
        for pi, p in enumerate(atk):
            carrier = make_carrier(ben_texts, max(DOC_LENS[-1], max(OFFSETS) + len(p.text) + 500), pi)
            for off in OFFSETS:
                docs.append(carrier[:off] + "\n\n" + p.text + "\n\n" + carrier[off:])
                meta.append((p.id, off))
        naive = sc.score(docs, label="pozicija/naive")
        chunked, counts, per_win = score_chunked_detail(sc, docs, a.win, a.stride,
                                                       label="pozicija/chunked")
        for (pid, off), sn, scnk, nw, ws in zip(meta, naive, chunked, counts, per_win):
            pos_rows.append({"detector": d, "payload": pid, "offset": off,
                             "score_naive": round(sn, 6), "flag_naive": int(sn >= thr),
                             "score_chunked": round(scnk, 6), "flag_chunked": int(scnk >= thr),
                             "n_windows": nw})
            doc_id = f"{pid}@off{off}"
            for wi, w in enumerate(ws):
                wnd_rows.append({"detector": d, "kind": f"position_{off}", "doc_id": doc_id,
                                 "window_idx": wi, "n_windows": nw,
                                 "score": round(w, 6), "thr": round(thr, 6)})
        by_off = {o: [] for o in OFFSETS}
        by_off_c = {o: [] for o in OFFSETS}
        for r in pos_rows:
            if r["detector"] == d:
                by_off[r["offset"]].append(r["flag_naive"])
                by_off_c[r["offset"]].append(r["flag_chunked"])
        for o in OFFSETS:
            print(f"   offset {o:>5}: TPR naive {sum(by_off[o]) / len(by_off[o]):.2f}"
                  f"   chunked {sum(by_off_c[o]) / len(by_off_c[o]):.2f}")

        # --- 3. cena odbrane: FPR vs duzina dokumenta -----------------------
        for L in DOC_LENS:
            carriers = [make_carrier(ben_texts, L, 7 * k + 1) for k in range(a.n_carriers)]
            fn = sc.score(carriers, label=f"cena/naive/{L}")
            fc, cnt, per_c = score_chunked_detail(sc, carriers, a.win, a.stride,
                                                 label=f"cena/chunked/{L}")
            for k, ws in enumerate(per_c):
                for wi, w in enumerate(ws):
                    wnd_rows.append({"detector": d, "kind": f"carrier_{L}",
                                     "doc_id": f"carrier{L}_{k}", "window_idx": wi,
                                     "n_windows": len(ws), "score": round(w, 6),
                                     "thr": round(thr, 6)})
            cost_rows.append({"detector": d, "doc_chars": L,
                              "windows": round(sum(cnt) / len(cnt), 1),
                              "fpr_naive": round(rate_above(fn, thr), 4),
                              "fpr_chunked": round(rate_above(fc, thr), 4)})
            print(f"   duzina {L:>6}: FPR naive {cost_rows[-1]['fpr_naive']:.3f}"
                  f"   chunked {cost_rows[-1]['fpr_chunked']:.3f}"
                  f"   ({cost_rows[-1]['windows']} prozora)")

        summary.append({"detector": d, "thr": round(thr, 6),
                        "tpr_naive_off0": round(sum(by_off[0]) / len(by_off[0]), 3),
                        "tpr_naive_off8000": round(sum(by_off[8000]) / len(by_off[8000]), 3),
                        "tpr_chunked_off8000": round(sum(by_off_c[8000]) / len(by_off_c[8000]), 3)})

    (a.out / "raw").mkdir(parents=True, exist_ok=True)
    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    with (a.out / "raw" / "t3_window_scores.jsonl").open("w", encoding="utf-8") as f:
        for r in pos_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if wnd_rows:
        p = a.out / "raw" / "t3_windows.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in wnd_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {p} ({len(wnd_rows)} prozora)")
    if wnd_rows:
        p = a.out / "raw" / "t3_windows.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in wnd_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"-> {p}  ({len(wnd_rows)} prozora; ulaz za `f2_analyze.py t3`)")
    for name, data in (("t3_position.csv", pos_rows), ("t3_defense_cost.csv", cost_rows),
                       ("t3_effective_window.csv", win_rows), ("t3_summary.csv", summary)):
        if not data:
            continue
        p = a.out / "tables" / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
        print(f"-> {p}")
    print("\nCITANJE: ako TPR pada sa offsetom a chunked ostaje ravan, napad je")
    print("         pozicija a ne sadrzaj; kolona fpr_chunked je cena te odbrane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
