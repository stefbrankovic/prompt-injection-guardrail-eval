#!/usr/bin/env python3
"""f2_analyze.py — ispravljena analiza Faze 2. NIJEDAN novi poziv modela.

Cita samo `results/raw/*.jsonl` koje su vec napisale trake T1-T4 i proizvodi
tabele koje odgovaraju na metodoloske primedbe iz revizije:

  t1   Puna 2x2 dekompozicija umesto `delta_koverta` vs `delta_sadrzaj`.
       Kritika je bila tacna: A - C nije "efekat sadrzaja" jer se A i C
       razlikuju i po duzini, leksici i temi. Ovde se racunaju cetiri
       velicine od kojih su DVE uparene (isti tekst, menja se samo omotac),
       plus interakcija, koja je jedina velicina bez konfaunda sadrzaja.

  t2   Uparena poredjenja po jezickoj i po osi mesanja, sa unapred
       deklarisanim familijama za Bonferroni. Ispravlja i tihi bag: `en_orig`
       i `sr_cyrl_orig` NEMAJU zajednicke id-eve, pa ih upareni test
       preskace bez poruke. Referenca za jezicku osu je `en_parallel`
       (FLORES, isti sadrzaj), a prag ostaje kalibrisan na `en_orig`.

  t4   TPR i AUC sa klasterskim intervalom po `behavior_id`, i n se izvestava
       kao "95 stringova / 28 klastera", ne kao n=95.

  t3   Poredjenje pravila agregacije (max / top2 / broj prozora >= prag).
       Trazi `results/raw/t3_windows.jsonl` (mikro-zakrpa u f2_t3_window.py).

Sve intervale racuna klasterski bootstrap. Broj replikacija se bira po
pravilu n_boot >= 100 / alpha_eff, jer percentil pri alpha_eff = 0.0015 nad
2000 uzoraka odredjuju dva izvlacenja i to nije interval nego sum.

    python scripts/f2_analyze.py t1
    python scripts/f2_analyze.py t2
    python scripts/f2_analyze.py t4
    python scripts/f2_analyze.py t3
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

RAW = Path("results/raw")
TAB = Path("results/tables")


# ---------------------------------------------------------------------------
# Osnovno
# ---------------------------------------------------------------------------
def read(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Nema fajla {path} — prvo pokreni odgovarajucu traku.")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def roc_auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney U sa prosecnim rangovima (saturirane distribucije imaju
    mnogo izjednacenih vrednosti; bez prosecnih rangova AUC je pristrasan)."""
    if not pos or not neg:
        return float("nan")
    m = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg], key=lambda t: t[0])
    ranks = [0.0] * len(m)
    i = 0
    while i < len(m):
        j = i
        while j + 1 < len(m) and m[j + 1][0] == m[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r_pos = sum(r for r, (_, lab) in zip(ranks, m) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (r_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def threshold_at_fpr(neg: list[float], target: float) -> float:
    """Najnizi prag pri kome je FPR <= target na datom benignom skupu."""
    if not neg:
        return float("inf")
    s = sorted(neg, reverse=True)
    k = int(len(s) * target)
    if k <= 0:
        return s[0] + 1e-9
    if k >= len(s):
        return 0.0
    return s[k] + 1e-9


def n_boot_for(alpha_eff: float, floor: int = 2000) -> int:
    """n_boot tako da svaki rep intervala odredjuje bar ~50 izvlacenja."""
    return max(floor, int(100 / alpha_eff))


def _groups(ids, cluster_of):
    g = defaultdict(list)
    for i in ids:
        g[cluster_of(i)].append(i)
    return dict(g)


def boot_stat(ids, cluster_of, stat, n_boot, alpha_eff, seed=0):
    """Klasterski bootstrap jedne statistike nad listom id-eva.

    `stat(list_of_ids) -> float`. Uzorkuju se KLASTERI sa vracanjem.
    """
    g = _groups(ids, cluster_of)
    keys = list(g)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        idx = []
        for _ in range(len(keys)):
            idx.extend(g[keys[rng.randrange(len(keys))]])
        v = stat(idx)
        if v == v:
            draws.append(v)
    draws.sort()
    lo = draws[int(len(draws) * alpha_eff / 2)]
    hi = draws[min(len(draws) - 1, int(len(draws) * (1 - alpha_eff / 2)))]
    return stat(ids), lo, hi, len(keys)


def boot_two(ids_a, cof_a, stat_a, ids_b, cof_b, stat_b, n_boot, alpha_eff, seed=0):
    """Interval za `stat_b - stat_a` kad su dve grupe NEZAVISNE (razliciti tekstovi).

    Svaki bootstrap uzorak nezavisno resample-uje obe grupe. Interval je siri
    nego kod uparenih velicina i to je posteno — ne pretvaramo neupareno
    poredjenje u upareno.
    """
    ga, gb = _groups(ids_a, cof_a), _groups(ids_b, cof_b)
    ka, kb = list(ga), list(gb)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        ia = []
        for _ in range(len(ka)):
            ia.extend(ga[ka[rng.randrange(len(ka))]])
        ib = []
        for _ in range(len(kb)):
            ib.extend(gb[kb[rng.randrange(len(kb))]])
        va, vb = stat_a(ia), stat_b(ib)
        if va == va and vb == vb:
            draws.append(vb - va)
    draws.sort()
    lo = draws[int(len(draws) * alpha_eff / 2)]
    hi = draws[min(len(draws) - 1, int(len(draws) * (1 - alpha_eff / 2)))]
    return stat_b(ids_b) - stat_a(ids_a), lo, hi, len(ka), len(kb)


def sig(lo, hi) -> str:
    return "DA" if (lo > 0 or hi < 0) else "-"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {path}")


def task_of(sid: str) -> str:
    """`banking__injection_task_0#imp` -> `banking__injection_task_0`."""
    return sid.split("#", 1)[0]


def behavior_of(sid: str) -> str:
    """`ipi__garage-door-email__012` -> `ipi__garage-door-email`."""
    if "#" in sid:
        return sid.split("#", 1)[0]
    head, _, tail = sid.rpartition("__")
    return head if head and tail.isdigit() else sid


# ---------------------------------------------------------------------------
# T1 — puna 2x2 dekompozicija
# ---------------------------------------------------------------------------
def cmd_t1(a) -> int:
    rows = read(a.raw)
    thr_by_det = {}
    csvp = TAB / "t1_envelope.csv"
    if csvp.exists():
        for r in csv.DictReader(csvp.open(encoding="utf-8")):
            try:
                thr_by_det[r["detector"]] = float(r["thr"])
            except (KeyError, ValueError):
                pass

    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by[r["detector"]][r["condition"]][r["id"]] = r["score"]

    out, cells = [], []
    m = 4                                   # familija: 4 velicine po detektoru
    alpha_eff = a.alpha / m
    nb = n_boot_for(alpha_eff)
    print(f"familija = 4 velicine po detektoru, alpha_eff = {alpha_eff:.4f}, n_boot = {nb}\n")

    for det, c in by.items():
        need = ["A_mal_raw", "B_mal_imp", "C_ben_raw", "D_ben_imp"]
        if any(k not in c for k in need):
            print(f"  {det}: nedostaju uslovi, preskacem")
            continue
        A, B, C, D = (c[k] for k in need)
        thr = thr_by_det.get(det)

        for name, d in zip(need + (["E_empty_imp"] if "E_empty_imp" in c else []),
                           [A, B, C, D] + ([c["E_empty_imp"]] if "E_empty_imp" in c else [])):
            row = {"detector": det, "cell": name, "n": len(d),
                   "mean": round(mean(d.values()), 4),
                   "median": round(sorted(d.values())[len(d) // 2], 4)}
            if thr is not None:
                row["flag_rate"] = round(sum(v >= thr for v in d.values()) / len(d), 4)
            cells.append(row)

        # --- uparene velicine: isti tekst, menja se samo omotac ---------
        goals = [i for i in C if i in D]
        tasks = sorted({task_of(i) for i in A} & {task_of(i) for i in B})
        a_by, b_by = {task_of(i): v for i, v in A.items()}, {task_of(i): v for i, v in B.items()}

        w_ben = boot_stat(goals, lambda i: i,
                          lambda ii: mean(D[i] - C[i] for i in ii), nb, alpha_eff)
        w_mal = boot_stat(tasks, lambda i: i,
                          lambda ii: mean(b_by[i] - a_by[i] for i in ii), nb, alpha_eff, seed=1)

        # --- neuparene velicine: razliciti tekstovi (konfaund sadrzaja) --
        d_raw = boot_two(list(C), lambda i: i, lambda ii: mean(C[i] for i in ii),
                         list(A), task_of, lambda ii: mean(A[i] for i in ii),
                         nb, alpha_eff, seed=2)
        d_imp = boot_two(list(D), lambda i: i, lambda ii: mean(D[i] for i in ii),
                         list(B), task_of, lambda ii: mean(B[i] for i in ii),
                         nb, alpha_eff, seed=3)

        # --- interakcija: da li omotac deluje isto na oba sadrzaja -------
        inter = boot_two(goals, lambda i: i, lambda ii: mean(D[i] - C[i] for i in ii),
                         tasks, lambda i: i, lambda ii: mean(b_by[i] - a_by[i] for i in ii),
                         nb, alpha_eff, seed=4)

        for label, res, kind in (
            ("W_ben  omotac na bezopasnom (D-C)", w_ben, "upareno"),
            ("W_mal  omotac na malicioznom (B-A)", w_mal, "upareno"),
            ("D_raw  sadrzaj bez omotaca (A-C)", d_raw, "NEUPARENO"),
            ("D_imp  sadrzaj u omotacu (B-D)", d_imp, "NEUPARENO"),
            ("I      interakcija (W_mal-W_ben)", inter, "neupareno"),
        ):
            point, lo, hi = res[0], res[1], res[2]
            out.append({"detector": det, "quantity": label.split()[0],
                        "opis": label.split(None, 1)[1], "tip": kind,
                        "value": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4),
                        "alpha_eff": alpha_eff, "significant": sig(lo, hi)})
            print(f"  {det:18s} {label:36s} {point:+.3f} [{lo:+.3f}, {hi:+.3f}]  {sig(lo, hi)}")
        if "E_empty_imp" in c:
            e = list(c["E_empty_imp"].values())
            print(f"  {det:18s} {'E      prazan omotac (n=' + str(len(e)) + ')':36s} "
                  f"{mean(e):+.3f}  [bez intervala]")
        print()

    write_csv(TAB / "t1_cells.csv", cells)
    write_csv(TAB / "t1_decomposition.csv", out)
    print("CITANJE:")
    print("  W_ben i W_mal su UPARENE — isti tekst, jedina promena je omotac. Njima se veruje.")
    print("  D_raw i D_imp su NEUPARENE — mal i ben tekstovi se razlikuju i po duzini i po temi;")
    print("  to nije cist 'efekat sadrzaja' nego razlika izmedju dva skupa tekstova, i tako se pise.")
    print("  I (interakcija) je jedina velicina bez konfaunda sadrzaja: ako je interval oko nule,")
    print("  omotac pomera bezopasan i maliciozan tekst JEDNAKO — to je najjaci oblik nalaza.")
    return 0


# ---------------------------------------------------------------------------
# T2 — jezicka osa i osa mesanja, sa deklarisanim familijama
# ---------------------------------------------------------------------------
def cmd_t2(a) -> int:
    rows = read(a.raw)
    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by[r["detector"]][r["condition"]][r["id"]] = r["score"]

    out = []
    for det, c in by.items():
        if "en_orig" not in c:
            print(f"  {det}: nema en_orig, preskacem")
            continue
        print(f"\n=== {det} ===")
        for fpr_t in a.fpr:
            thr = threshold_at_fpr(list(c["en_orig"].values()), fpr_t)
            n_en = len(c["en_orig"])
            print(f"  prag kalibrisan na en_orig pri FPR={fpr_t:.0%}: {thr:.6f}  "
                  f"(odredjuje ga {max(1, int(n_en * fpr_t))} od {n_en} tekstova)")

            def fpr_of(cond, ids=None):
                d = c[cond]
                ids = ids if ids is not None else list(d)
                return mean(1.0 if d[i] >= thr else 0.0 for i in ids)

            # -------- familija L: jezik i pismo -------------------------
            fam_l = []
            if "en_parallel" in c:
                fam_l += [("en_parallel", "sr_latn_orig"), ("en_parallel", "sr_cyrl_orig")]
            fam_l += [("sr_latn_orig", "sr_cyrl_orig")]
            fam_l = [(x, y) for x, y in fam_l if x in c and y in c]
            m_l = max(1, len(fam_l))
            ae_l = a.alpha / m_l
            nb_l = n_boot_for(ae_l)
            print(f"  [familija L: jezik/pismo] m={m_l}, alpha_eff={ae_l:.4f}, n_boot={nb_l}")
            for ref, cond in fam_l:
                ids = [i for i in c[ref] if i in c[cond]]
                if not ids:
                    print(f"    {ref} -> {cond}: NEMA zajednickih id-eva, poredjenje nije upareno")
                    continue
                point, lo, hi, nk = boot_stat(
                    ids, lambda i: i,
                    lambda ii: fpr_of(cond, ii) - fpr_of(ref, ii), nb_l, ae_l)
                out.append({"detector": det, "family": "L_jezik_pismo", "fpr_target": fpr_t,
                            "ref": ref, "condition": cond, "thr": round(thr, 6),
                            "paired": 1, "n": len(ids), "clusters": nk,
                            "fpr_ref": round(fpr_of(ref, ids), 4),
                            "fpr_cond": round(fpr_of(cond, ids), 4),
                            "delta": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4),
                            "m": m_l, "significant": sig(lo, hi)})
                print(f"    {ref:14s} -> {cond:14s} FPR {fpr_of(ref, ids):.3f} -> "
                      f"{fpr_of(cond, ids):.3f}  d={point:+.3f} [{lo:+.3f}, {hi:+.3f}]  {sig(lo, hi)}")

            # -------- familija M: mesanje pisama ------------------------
            bases = [("en_orig", "en_mix_"), ("sr_latn_orig", "sr_latn_mix_"),
                     ("sr_cyrl_orig", "sr_cyrl_mix_")]
            heads = [b for b in a.headline]
            fam_m = [(base, f"{pref}{h}") for base, pref in bases for h in heads
                     if base in c and f"{pref}{h}" in c]
            m_m = max(1, len(fam_m))
            ae_m = a.alpha / m_m
            nb_m = n_boot_for(ae_m)
            print(f"  [familija M: mesanje] m={m_m}, alpha_eff={ae_m:.4f}, n_boot={nb_m}")
            for ref, cond in fam_m:
                ids = [i for i in c[ref] if i in c[cond]]
                if not ids:
                    continue
                point, lo, hi, nk = boot_stat(
                    ids, lambda i: i,
                    lambda ii: fpr_of(cond, ii) - fpr_of(ref, ii), nb_m, ae_m)
                out.append({"detector": det, "family": "M_mesanje", "fpr_target": fpr_t,
                            "ref": ref, "condition": cond, "thr": round(thr, 6),
                            "paired": 1, "n": len(ids), "clusters": nk,
                            "fpr_ref": round(fpr_of(ref, ids), 4),
                            "fpr_cond": round(fpr_of(cond, ids), 4),
                            "delta": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4),
                            "m": m_m, "significant": sig(lo, hi)})
                print(f"    {ref:14s} -> {cond:18s} FPR {fpr_of(ref, ids):.3f} -> "
                      f"{fpr_of(cond, ids):.3f}  d={point:+.3f} [{lo:+.3f}, {hi:+.3f}]  {sig(lo, hi)}")

            # -------- deskriptivno: cela kriva, bez zvezdica ------------
            for cond in sorted(c):
                if "_mix_" not in cond:
                    continue
                out.append({"detector": det, "family": "kriva_deskriptivno", "fpr_target": fpr_t,
                            "ref": "", "condition": cond, "thr": round(thr, 6),
                            "paired": 0, "n": len(c[cond]), "clusters": len(c[cond]),
                            "fpr_ref": "", "fpr_cond": round(fpr_of(cond), 4),
                            "delta": "", "lo": "", "hi": "", "m": "", "significant": ""})

    write_csv(TAB / "t2_corrected.csv", out)
    print("\nCITANJE:")
    print("  Jedini par bez ijednog konfaunda je sr_latn_orig -> sr_cyrl_orig: ista recenica,")
    print("  isti jezik, deterministicka transliteracija, menja se SAMO pismo.")
    print("  Poredjenje sa en_orig je konfaundirano sadrzajem (druge teme); ako FLORES nije")
    print("  prosao, to se pise eksplicitno i tvrdnja se spusta na 'prenos praga izmedju jezika'.")
    return 0


# ---------------------------------------------------------------------------
# T4 — TPR i AUC sa klasterima po ponasanju
# ---------------------------------------------------------------------------
def cmd_t4(a) -> int:
    rows = read(a.raw)
    out = []
    for det in sorted({r["detector"] for r in rows}):
        sub = [r for r in rows if r["detector"] == det]
        neg = [r["score"] for r in sub if r["set"] == "benign"]
        if not neg:
            print(f"  {det}: nema benignih, preskacem")
            continue
        print(f"\n=== {det} ===   n_benign={len(neg)}")
        for fpr_t in a.fpr:
            thr = threshold_at_fpr(neg, fpr_t)
            print(f"  prag pri FPR={fpr_t:.0%}: {thr:.6f}")
            sets = sorted({(r["set"], r.get("mode", "naive")) for r in sub if r["set"] != "benign"})
            m = max(1, len(sets))
            ae = a.alpha / m
            nb = n_boot_for(ae)
            for sname, mode in sets:
                d = {r["id"]: r["score"] for r in sub
                     if r["set"] == sname and r.get("mode", "naive") == mode}
                ids = list(d)
                cof = behavior_of if sname == "ipi_arena" else task_of
                tpr, lo, hi, nk = boot_stat(
                    ids, cof, lambda ii: mean(1.0 if d[i] >= thr else 0.0 for i in ii), nb, ae)
                auc = roc_auc(list(d.values()), neg)
                out.append({"detector": det, "set": sname, "mode": mode, "fpr_target": fpr_t,
                            "n_strings": len(ids), "n_clusters": nk, "thr": round(thr, 6),
                            "tpr": round(tpr, 4), "tpr_lo": round(lo, 4), "tpr_hi": round(hi, 4),
                            "auc": round(auc, 4)})
                print(f"    {sname:14s} {mode:8s} n={len(ids):>3}/{nk:<3} klastera  "
                      f"TPR={tpr:.2f} [{lo:.2f}, {hi:.2f}]  AUC={auc:.3f}")

            # uparena razlika naive -> chunked na istom skupu
            for sname in sorted({s for s, _ in sets}):
                nv = {r["id"]: r["score"] for r in sub
                      if r["set"] == sname and r.get("mode", "naive") == "naive"}
                ck = {r["id"]: r["score"] for r in sub
                      if r["set"] == sname and r.get("mode") == "chunked"}
                ids = [i for i in nv if i in ck]
                if not ids:
                    continue
                cof = behavior_of if sname == "ipi_arena" else task_of
                point, lo, hi, nk = boot_stat(
                    ids, cof,
                    lambda ii: mean(1.0 if ck[i] >= thr else 0.0 for i in ii)
                    - mean(1.0 if nv[i] >= thr else 0.0 for i in ii), nb, ae, seed=7)
                out.append({"detector": det, "set": sname, "mode": "delta_chunked_minus_naive",
                            "fpr_target": fpr_t, "n_strings": len(ids), "n_clusters": nk,
                            "thr": round(thr, 6), "tpr": round(point, 4),
                            "tpr_lo": round(lo, 4), "tpr_hi": round(hi, 4), "auc": ""})
                print(f"    {sname:14s} prozor - naive: dTPR={point:+.3f} "
                      f"[{lo:+.3f}, {hi:+.3f}]  {sig(lo, hi)}")

    write_csv(TAB / "t4_corrected.csv", out)
    print("\nCITANJE: u svakoj recenici o IPI Areni ide 'n stringova / n ponasanja'.")
    print("  Tvrdnja je 'generalizacija opada na IPI Arena distribuciji', ne 'detektor pada")
    print("  na pravim napadima' — skup je selektovan po tome sto su napadi radili na Qwen-u.")
    return 0


# ---------------------------------------------------------------------------
# T3 — pravila agregacije (trazi t3_windows.jsonl)
# ---------------------------------------------------------------------------
def thr_from_summary() -> dict[str, float]:
    """Pragovi po detektoru iz `results/tables/t3_summary.csv`, ako postoji."""
    p = TAB / "t3_summary.csv"
    if not p.exists():
        return {}
    with p.open(encoding="utf-8", newline="") as f:
        out = {}
        for r in csv.DictReader(f):
            try:
                out[r["detector"]] = float(r["thr"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def cmd_t3(a) -> int:
    p = RAW / "t3_windows.jsonl"
    if not p.exists():
        print(f"Nema {p}. f2_t3_window.py sada upisuje score svakog prozora, ne samo")
        print("maksimum. Pokreni ponovo traku T3 sa ISTIM argumentima — svi prozori su")
        print("vec u kesu (.cache/scores), pa ne ide nijedan novi poziv modela:")
        print("  python scripts/f2_t3_window.py --detectors deepset promptguard2_86m --n-carriers 8")
        return 1
    rows = read(p)
    out = []
    from_summary = thr_from_summary()
    for det in sorted({r["detector"] for r in rows}):
        sub = [r for r in rows if r["detector"] == det]
        # Prag je PO DETEKTORU. Jedan globalni --thr za sve detektore je besmislen:
        # 0.006 je prag promptguard-a, deepset ima 0.9989. Redosled izvora:
        # kolona `thr` u samom t3_windows.jsonl (upisao ju je f2_t3_window),
        # pa t3_summary.csv, pa tek onda rucni --thr kao override.
        thr = a.thr
        src = "--thr"
        if thr is None:
            have = {r["thr"] for r in sub if r.get("thr") is not None}
            if len(have) == 1:
                thr, src = have.pop(), "t3_windows.jsonl"
            elif det in from_summary:
                thr, src = from_summary[det], "t3_summary.csv"
        if thr is None:
            print(f"  {det}: nema praga ni u jsonl-u ni u t3_summary.csv — zadaj --thr")
            continue
        print(f"\n=== {det} ===  prag={thr:.6f}  ({src})")
        for kind in sorted({r.get("kind", "?") for r in sub}):
            grp = defaultdict(list)
            for r in sub:
                if r.get("kind") == kind:
                    grp[r["doc_id"]].append(r["score"])
            rules = {
                "max": lambda w: max(w),
                "top2_mean": lambda w: mean(sorted(w, reverse=True)[:2]),
                "count>=2": lambda w: 1.0 if sum(x >= thr for x in w) >= 2 else 0.0,
                "count>=3": lambda w: 1.0 if sum(x >= thr for x in w) >= 3 else 0.0,
            }
            for rn, fn in rules.items():
                vals = [fn(w) for w in grp.values()]
                rate = (mean(vals) if rn.startswith("count")
                        else mean(1.0 if v >= thr else 0.0 for v in vals))
                out.append({"detector": det, "kind": kind, "rule": rn, "n_docs": len(grp),
                            "mean_windows": round(mean(len(w) for w in grp.values()), 1),
                            "rate": round(rate, 4)})
                print(f"  {kind:14s} {rn:10s} n={len(grp):>3}  "
                      f"prosek prozora={out[-1]['mean_windows']:>5}  udeo={rate:.3f}")
    write_csv(TAB / "t3_aggregation.csv", out)
    print("\nCITANJE: 'max po prozorima' je najnaivnije pravilo i najskuplje po FPR-u.")
    print("  Ako 'count>=2' zadrzi TPR a obori FPR, onda je rast FPR-a posledica pravila")
    print("  agregacije a ne klizeceg prozora kao ideje — i tako se pise u radu.")
    return 0


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Ispravljena analiza Faze 2, bez novih poziva modela")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("t1")
    p1.add_argument("--raw", type=Path, default=RAW / "t1_envelope_scores.jsonl")
    p1.add_argument("--alpha", type=float, default=0.05)
    p1.set_defaults(fn=cmd_t1)

    p2 = sub.add_parser("t2")
    p2.add_argument("--raw", type=Path, default=RAW / "t2_script_scores.jsonl")
    p2.add_argument("--alpha", type=float, default=0.05)
    p2.add_argument("--fpr", type=float, nargs="+", default=[0.01, 0.05])
    p2.add_argument("--headline", nargs="+", default=["3ch", "100%"],
                    help="budzeti koji ulaze u familiju M; ostalo ide deskriptivno")
    p2.set_defaults(fn=cmd_t2)

    p4 = sub.add_parser("t4")
    p4.add_argument("--raw", type=Path, default=RAW / "t4_external_scores.jsonl")
    p4.add_argument("--alpha", type=float, default=0.05)
    p4.add_argument("--fpr", type=float, nargs="+", default=[0.01, 0.05])
    p4.set_defaults(fn=cmd_t4)

    p3 = sub.add_parser("t3")
    p3.add_argument("--thr", type=float, default=None,
                    help="override; podrazumevano se prag cita PO DETEKTORU iz "
                         "t3_windows.jsonl, pa iz t3_summary.csv")
    p3.add_argument("--alpha", type=float, default=0.05)
    p3.set_defaults(fn=cmd_t3)

    a = ap.parse_args()
    TAB.mkdir(parents=True, exist_ok=True)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
