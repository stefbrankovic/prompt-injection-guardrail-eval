diff --git a/scripts/f2_defense.py b/scripts/f2_defense.py
--- a/scripts/f2_defense.py
+++ b/scripts/f2_defense.py
@@ -10,6 +10,10 @@
     ap.add_argument("--win", type=int, default=1200)
     ap.add_argument("--stride", type=int, default=600)
+    ap.add_argument("--embed", type=int, default=None, metavar="OFFSET",
+                    help="ubaci svaki napad u nosac iste duzine, na dati offset. "
+                         "Bez ovoga bezopasna strana ima 26 prozora a napadi 1, "
+                         "pa je poredjenje namesteno protiv prozora.")
     ap.add_argument("--fpr", type=float, default=0.05,
                     help="rezolucija je 1/n_carriers; pri 40 nosaca 0.05 = 2 dokumenta")
     ap.add_argument("--out", type=Path, default=Path("results"))
     a = ap.parse_args()

     ben = load_jsonl(a.benign_full)
     ben_texts = [s.text for s in ben]
     ipi = load_jsonl(a.ipi)
     carriers = [make_carrier(ben_texts, a.carrier_chars, 7 * k + 1)
                 for k in range(a.n_carriers)]
-    clusters = [s.id.split("#")[0] if "#" in s.id else s.id for s in ipi]
+    # isti kljuc klastera kao u f2_t4_external.py — 95 stringova, ali 28 ponasanja
+    clusters = [s.id.split("#")[0] if "#" in s.id else
+                getattr(s, "suite", "") + "__" + s.id.rsplit("__", 1)[0] for s in ipi]
+    if a.embed is None:
+        atk_texts = [s.text for s in ipi]
+    else:
+        atk_texts = []
+        for k, s in enumerate(ipi):
+            c = make_carrier(ben_texts, a.carrier_chars, 1000 + 7 * k)
+            off = min(a.embed, len(c))
+            atk_texts.append(c[:off] + "\n\n" + s.text + "\n\n" + c[off:])
     print(f"bezopasnih nosaca {len(carriers)} po {a.carrier_chars} znakova, "
           f"IPI napada {len(ipi)} stringova / {len(set(clusters))} ponasanja")
+    med_n = sorted(len(t) for t in carriers)[len(carriers) // 2]
+    med_p = sorted(len(t) for t in atk_texts)[len(atk_texts) // 2]
+    print(f"medijana duzine: bezopasni {med_n}, napadi {med_p} znakova"
+          + ("" if a.embed is None else f"  (napadi ubaceni na offset {a.embed})"))
+    if a.embed is None and med_p * 3 < med_n:
+        print("  UPOZORENJE: strane nisu iste duzine. Prag postavlja 26 prozora")
+        print("  bezopasnog dokumenta, a napad ima jedan — poredjenje naive vs")
+        print("  window i pravilo count>=2 NISU valjani. Pokreni sa --embed 4000.")
     print(f"budzet laznih uzbuna: {a.fpr:.0%}  (= {int(len(carriers) * a.fpr)} od "
           f"{len(carriers)} nosaca)")
@@ -60,7 +64,7 @@
         pools["naive"] = {
             "neg": [[v] for v in sc.score(carriers, label="odbrana/naive/ben")],
-            "pos": [[v] for v in sc.score([s.text for s in ipi], label="odbrana/naive/ipi")],
+            "pos": [[v] for v in sc.score(atk_texts, label="odbrana/naive/ipi")],
         }
         # prozori, sa i bez ispravljene pokrivenosti glave
         for mode, hc in (("plain", False), ("hc", True)):
             out = {}
-            for side, texts in (("neg", carriers), ("pos", [s.text for s in ipi])):
+            for side, texts in (("neg", carriers), ("pos", atk_texts)):
@@ -110,6 +114,7 @@
             rows.append({"detector": d, "rule": name, "thr": round(thr, 6),
                          "fpr_benign_16k": round(fpr, 4), "tpr_ipi": round(tpr, 4),
                          "n_benign": len(neg), "n_attacks": len(pos),
                          "n_clusters": len(set(clusters)),
+                         "embed_offset": -1 if a.embed is None else a.embed,
                          "mean_windows": round(nw, 1)})