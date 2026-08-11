# MASTERPLAN — CyrEvade

**Napad na filtere AI agenata koji ljudsko oko ne vidi, mehanizam koji ga objašnjava, i odbrana koja ga hvata**

**Tim:** Stefan Branković, Katarina · **Seminar:** PSIML 11 (5–16.08.2026) · **Rok:** 16.08.2026.
**Mentor:** Kristina Nikolić (ETH Zürich, SPY Lab) — *potvrditi da je u mentorskom bazenu*
**Repo:** `github.com/stefbrankovic/psiml_project`

---

## 0. Realnost problema — provereni podaci

Pre nego što uložimo šest dana, evo dokaza da problem postoji i da je merljiv. Ovo je i sadržaj slajda "zašto ovo radimo".

**Detektori prompt injection-a se probijaju karakterskim trikovima — dokumentovano, sa brojkama:**

- Prompt Guard **1** (86M, Meta) je 2024. probijen umetanjem razmaka između slova, sa **99.8% uspeha** — 449 od 450 napada prošlo. Otkrio Robust Intelligence (danas deo Cisca), Meta potvrdila. To je ista klasa slabosti koju mi eksploatišemo, samo drugim sredstvom.
- Sistematska studija iz 2025. (*Bypassing Prompt Injection and Jailbreak Detection in LLM Guardrails*, arXiv:2504.11168) testira **12 karakterskih tehnika** protiv šest komercijalnih i open-source detektora (Azure Prompt Shield, Meta Prompt Guard, ProtectAI, NeMo, ...). Homoglifi su **jedna od tih 12**. Neke tehnike postižu **do 100% evazije**, uz očuvanu nameru napada. Homoglifi i Unicode tagovi su među najefikasnijima.
- Boucher et al. (*Bad Characters*, IEEE S&P 2022) — akademski temelj klase neprimetnih Unicode napada.

**Ali — i ovo je ključno za pošteno pozicioniranje — Prompt Guard 2 je zakrpljen:**

Model card Prompt Guard 2 (86M, april 2025) eksplicitno navodi "**adversarial-attack resistant tokenization**" koja cilja "whitespace manipulations and fragmented tokens". Dakle **napad iz 2024. sa razmacima je zatvoren.** Prompt Guard 2 takođe pokriva 8 jezika: engleski, francuski, nemački, hindi, italijanski, portugalski, španski, tajlandski.

**Srpski nije među njih. Ćirilica nije u tih 8 jezika. I homoglif napad nije isto što i razmak napad koji su zakrpili.**

To je idealna pozicija za projekat: **ni pretežak** (detektor nije neprobojan — cela klasa napada radi), **ni pretrivijalan** (najlakši, već poznati napad je zatvoren, pa moramo da uradimo nešto novo). Naša teza:

> Prompt Guard 2 je otporniji na *tokenizacione* trikove na jezicima koje pokriva. Ali srpska ćirilica napada na drugoj osi — **vizuelni identitet uz jezičku pokrivenost koje nema** — i ta osa nije zatvorena. Štaviše, ne može se zatvoriti normalizacijom bez žrtvovanja srpskog jezika.

**Naša procena, koju D2 potvrđuje ili obara brojkom:**

| Meta koju merimo | Realno očekivanje (hipoteza, ne rezultat) | Kako proveravamo |
|---|---|---|
| Evazija Prompt Guard 2 homoglifima na engleskom injection-u | umerena — 30–70%; PG2 je delom otporan | greedy pretraga, D2 |
| Evazija na srpskom injection-u (ćirilica) | **visoka — 70–95%**; srpski nije pokriven | greedy pretraga, D2 |
| Očuvanje razumevanja na velikom modelu (ASR) | visoko za mali budžet, opada za veliki | AgentDojo, D4 |
| Postojanje "prozora" (evazija DA, ASR očuvan) | postoji za male budžete | presek krivih, D3 |

Ako se na D2 pokaže da je evazija niska čak i na srpskom (< 20%), premisa je slabija nego što mislimo i pivotiramo (vidi sekciju 8). **Zato je D2 tvrdi gate.**

*(Sve gornje brojke iz literature su proverene 09.08.2026. Linkovi u `literature/READING.md`.)*

---

## 0b. Šta je promenio Kristinin feedback (10.08)

Tri izmene u odnosu na prvu verziju plana:

**1. Lestvica detektora umesto jednog.** Kristina je upozorila da proverimo je li PG2 uopšte treniran za prompt injection ili samo za jailbreak. Provereno: PG2 **jeste** za injection (scope: "pokušava da pregazi prethodne instrukcije"), i Meta sama izveštava AgentDojo APR 81.2%. Ali PG1-ov poseban "injection" label je u PG2 uklonjen. Zato testiramo **četiri detektora poređana po višejezičnoj pokrivenosti** (ProtectAI EN-only → Deepset → PG2 22M → PG2 86M), pa dobijamo gradijent umesto binarnog rezultata: *koliko višejezične pokrivenosti treba pre nego što homoglifi postanu neophodni.*

**2. Probe se ne izmišlja — koristi se TaskTracker.** Njen pointer na arXiv:2406.00799 je ključan: metod je probe na **razlici aktivacija** (pre/posle obrade eksternog teksta), ne na sirovim aktivacijama. Postoji repo, dataset od 500K primera i istrenirani probe-ovi. Uz to smo našli **PIShield** (arXiv:2510.14005) koji radi praktično isto što smo mi zvali "ActProbe". **Dakle odbrana iz aktivacija nije naša ideja i to otvoreno kažemo.**

**3. Centralna hipoteza Čina III je preformulisana** (njena formulacija, usvojena doslovno):

> Ako probe stvarno detektuje *task drift*, jezik ne bi smeo da bude bitan — ako je model uspešno injectovan, razumeo je srpski i ponašanje mu je odstupilo, pa probe treba da opali. **Ako probe hvata injection na engleskom a ne na srpskom, onda ono što detektuje nije task drift nego nešto vezano za površinu engleskog teksta.**

Time projekat prestaje da bude "predlažemo odbranu" i postaje **test hipoteze na kojoj počiva cela klasa activation-based odbrana**. Oba ishoda su rezultat; negativan je zanimljiviji.

**Redosled rada** (njen savet): prvo gotovi detektori, probe tek posle. Probe je najzahtevniji deo i ide na D4–D5.

---

## 1. Ideja

**Problem.** LLM ne razlikuje instrukciju od podatka — sistemski prompt, korisnikova poruka i sadržaj koji je agent pročitao (mejl, web stranica, tool output) ulaze u isti kontekst kao isti tip objekta. Zato je *indirect prompt injection* (napad sakriven u podacima koje agent pročita) posledica arhitekture, ne bag. Najčešća odbrana je tekstualni klasifikator (Prompt Guard), koji je treniran i evaluiran na šačici jezika. Model koji brani razume mnogo više jezika nego što detektor pokriva.

**Hipoteza (falsifikabilna, jedna rečenica).**
Zamenom latiničnih karaktera vizuelno identičnim srpskim ćiriličnim homoglifima može se injection učiniti nevidljivim za Prompt Guard 2 (evazija znatno viša nego na engleskom), a da veliki model i dalje izvršava napad — jer razume srpski uprkos tome što ga detektor ne pokriva.

**Kako je obaramo.** Ako greedy pretraga ne uspe da spusti evaziju znatno iznad engleskog baseline-a pri budžetu koji čuva ASR — hipoteza pada. Merljivo, na AgentDojo-u, do sredine nedelje.

**Šta je novo u odnosu na postojeće (spremni odgovor mentoru).**
1. Boucher-ovi i "12 tehnika" homoglifi su egzotičan Unicode koji se brani **NFKC normalizacijom + whitelist-om skriptova**. Srpska ćirilica se tako **ne može** odbraniti — to je legitiman jezik miliona ljudi. **Sukob odbrane i višejezičnosti niko nije analizirao.**
2. Meta je *indirect injection u agentskoj petlji* (posledica = izvršena akcija), ne klasifikacija ili prevod.
3. Odbrana iz internih stanja modela (ActProbe) i napad na tu odbranu (Čin IV) su potpuno naši.

---

## 2. Definicija "gotovog" — po činovima

Projekat je strukturiran u pet činova. Svaki ima jasnu isporuku i tvrdi kriterijum prolaska.

### Čin I — Dijagnoza (D1–D2) · *osigurani rezultat*
- [ ] Homoglif mapa i CyrEvade greedy/beam pretraga rade (**već implementirano i testirano — vidi `src/psiml/attack/`**).
- [ ] Prompt Guard 2 učitan, meri score na skupu injection-a (čisti EN, EN-homoglif, SR-latinica, SR-ćirilica, SR-homoglif).
- [ ] **Isporuka: kriva evazije vs budžet perturbacije**, po jeziku/pismu. Prvi grafik.
- **Gate D2:** ako kriva ne pokazuje jasan jaz između ćirilice i engleskog → problem u pristupu, preispitati pre nego što se ide dalje.

### Čin II — Mehanizam (D3)
- [ ] Za svaki perturbovani string: tokenizer fertility u PG2 tokenizeru.
- [ ] Korelacija: fertility ↔ pad detektorovog score-a; fertility ↔ očuvanje ASR-a.
- [ ] **Isporuka: scatter fertility vs pad score-a** sa fitovanom linijom. Objašnjenje: napad radi jer fragmentacija tokena razbija leksičke feature-e malog detektora, a veliki model i dalje čita.

### Čin III — Artefakt: odbrana `ActProbe` (D4–D5) · *ambicija*
- [ ] AgentDojo integracija; end-to-end napad u agentskoj petlji (bar 2 task suite).
- [ ] Linearni probe nad rezidualnim streamom agentskog modela, treniran **isključivo na engleskim** primerima.
- [ ] Isporučen kao klasa koja nasleđuje AgentDojo `Defense` interfejs.
- [ ] Baseline odbrana: NFKC normalizacija + transliteracija (i dokaz zašto uništava srpski).
- [ ] **Isporuka: heatmap odbrane × varijante napada** (ASR). Filteri crveni na ćirilici, ActProbe hladan. Plus: latencijski overhead ActProbe ≈ 0 (isti forward pass).

### Čin IV — Napad na sopstvenu odbranu (D6) · *ovo nas razlikuje*
- [ ] Preusmeriti CyrEvade da optimizuje protiv ActProbe score-a. Da li prozor i dalje postoji i po kojoj ceni u budžetu?
- [ ] Cross-lingual generalizacija: probe treniran na EN, testiran na makedonskom/bugarskom (druga ćirilica) ili grčkom (treće pismo).
- [ ] Cross-model: probe sa Qwen → Llama.
- [ ] **Isporuka: pošten nalaz** — "odbrana drži do budžeta X / pada na jeziku Y". Oba ishoda su publikabilna.

### Čin V — Objava (paralelno od D3, opciono)
- [ ] Abstract + uvod napisani D3. Figure u finalnom kvalitetu odmah.
- [ ] Odgovorno objavljivanje: javiti Meta timu pre objave (report vulnerabilities kanal postoji na PG repo-u).
- [ ] Uslov: mentor pristaje na koautorstvo i pregled.

### Fallback (ako Čin III ne radi do srede uveče)
Prekid Čina III, prelazak na Čin IV nad postojećim. Projekat ostaje kompletan: **dijagnoza + mehanizam + pošteno rečeno dokle smo stigli sa odbranom.** To je legitiman ishod i planiran je.

---

## 3. Literatura

Čitati **samo #1, #2 i #3 pre početka**. Ostalo usput. Tvrdi budžet: 4h ukupno.

| # | Rad | Uloga | Ko | Status |
|---|---|---|---|---|
| 1 | Debenedetti et al., **AgentDojo** (NeurIPS 2024, arXiv:2406.13352) | infrastruktura + metrike | Stefan | ☐ |
| 2 | Abdelnabi et al., **Get my drift? Task Drift with Activation Deltas** (SaTML'25, arXiv:2406.00799) | **Kristinin pointer. Metod za Čin III.** Repo: `github.com/microsoft/TaskTracker` | Katarina | ☐ |
| 3 | Zou et al., **PIShield** (arXiv:2510.14005) | residual-stream + linear probe. **Najbliži konkurent — moramo znati.** | Katarina | ☐ |
| 4 | Hackett et al., **Bypassing Guardrails** (arXiv:2504.11168) | 12 karakterskih tehnika, homoglifi među njima | Stefan | ☐ |
| 5 | Boucher et al., **Bad Characters** (IEEE S&P 2022) | temelj; "zašto NFKC ne rešava srpski" | Stefan | ☐ |
| 6 | **Prompt Guard 2 model card** (HF) | šta je zakrpljeno, 8 jezika, AgentDojo APR 81.2% | oboje | ✅ |
| 7 | Liu et al., **InjecGuard** (arXiv:2410.22770) | over-defense; izbor detektora | Katarina | ☐ |
| 8 | **Adaptive Eval of OOB Defenses** (arXiv:2606.26479) | opravdanje za Čin IV | Stefan | ☐ |
| 9 | microsoft/**llmail-inject-challenge** (repo) | realni napadi koji su probijali TaskTracker odbranu | Stefan | ☐ |

**Repoi:** `github.com/ethz-spylab/agentdojo` · `github.com/microsoft/TaskTracker` · `github.com/nickboucher/imperceptible`

## 4. Resursi

### Detektori — lestvica (jedini izvor istine: `src/psiml/detectors.py`)
| Ključ | HF id | Zadatak | Jezici | Gated |
|---|---|---|---|---|
| `protectai_v2` | `protectai/deberta-v3-base-prompt-injection-v2` | samo injection | **samo engleski** | ne |
| `deepset` | `deepset/deberta-v3-base-injection` | samo injection | engleski | ne |
| `promptguard2_22m` | `meta-llama/Llama-Prompt-Guard-2-22M` | injection+jailbreak | slabija višejezičnost | **da** |
| `promptguard2_86m` | `meta-llama/Llama-Prompt-Guard-2-86M` | injection+jailbreak | 8 jezika, srpski NIJE | **da** |

### Ostalo
| Tip | Šta | Odakle | Status |
|---|---|---|---|
| Agent model | `Qwen/Qwen2.5-7B-Instruct` (dobar srpski) | HF | ☐ D1 |
| Agent model (alt) | `meta-llama/Llama-3.1-8B-Instruct` | HF, gated | ☐ |
| Framework | `agentdojo` | `pip` / `github.com/ethz-spylab/agentdojo` | ☐ D1 |
| **Probe metod + dataset** | **TaskTracker** (500K primera, istrenirani probe-ovi, aktivacije za 6 modela) | `github.com/microsoft/TaskTracker` | ☐ **tražiti pristup aktivacijama preko forme** |
| Adversarijalni primeri | `microsoft/llmail-inject-challenge-analysis` | GitHub | ☐ D6 |
| Homoglif jezgro | `psiml.attack.homoglyphs`, `psiml.attack.search` | **naš repo** | ✅ napisano+testirano |
| Serving | vLLM (OpenAI-compat endpoint za AgentDojo) | `pip` | ☐ D4 |
| Compute | Čin I–II: laptop/Colab. Čin III–IV: 1×24–40GB, ~12h | Nacionalna AI platforma | ☐ pitati |

**Kritično, uraditi večeras:** `python scripts/check_access.py`. Gated modeli (PG2 86M i 22M) traže "Request access" na HF-u; odobrenje traje par sati. Ako se to ostavi za ujutru, blokira ceo D1.

## 5. Plan po fazama

Redosled po Kristininom savetu: **prvo gotovi detektori, probe tek posle.**

| Faza | Dan | Datum | Isporuka | Ko | Gate |
|---|---|---|---|---|---|
| F0 setup | D0 | 09–10.08 | repo, `check_access.py` zeleno, **HF gated pristup zatražen** | oboje | pristup odobren pre D1 |
| Čin I | D1 | 11.08 | AgentDojo radi; **baseline: 4 detektora na engleskom** (TPR + FPR) | S: AgentDojo, K: detektori | **detektori moraju biti dobri na EN, inače nema šta da se probija** |
| Čin I | D2 | 12.08 | srpski (lat/ćir) + CyrEvade; **kriva evazije po detektoru** | oboje | jaz ćirilica vs EN mora postojati |
| Čin II | D3 | 13.08 | fertility korelacija; abstract+uvod | K: analiza, S: pisanje | — |
| Čin III | D4 | 14.08 | TaskTracker metod: activation deltas, probe treniran na EN | S: aktivacije, K: probe | benign utility ≥ 30% ili API pivot |
| Čin III | D5 | 15.08 | **probe testiran na srpskom — centralna hipoteza** | oboje | probe radi na EN, inače → Čin IV |
| Čin IV | D6 | 16.08 | adaptivni napad, cross-lingual, figure, **demo uvežban** | oboje | — |

**Milestone-ovi koji ne smeju da kliznu:**
- **D1 uveče:** znamo da li su detektori dobri na engleskom (Kristinina pretpostavka potvrđena ili oborena).
- **D2 uveče:** prvi grafik postoji.
- **D5 uveče:** odgovor na centralnu hipotezu — drži li probe na srpskom.
- **D6 podne:** demo uvežban bar dvaput.

## 6. Podela posla

Rez po osi **napad / odbrana**, minimalno preklapanje u fajlovima.

| Stefan (infrastruktura + odbrana) | Katarina (napad + analiza) |
|---|---|
| AgentDojo integracija, agent petlja | homoglif varijante, pretraga, budžetske krive |
| vLLM serving, PG2 učitavanje | fertility analiza (Čin II) |
| izvlačenje aktivacija, ActProbe (`defense/`) | probe evaluacija, cross-lingual (Čin IV) |
| latencija, reproduktivnost, manifest | figure i grafici (`viz/`) |
| pisanje metod/rezultati sekcija | pisanje uvod/related sekcija |

**Interfejs (dogovoren D1, ne menja se):** JSONL sa poljima
`{injection_id, jezik, pismo, varijanta, tekst, budget, pg2_score, evaded}`.
Napadačka strana proizvodi ovaj fajl; odbrambena ga konzumira. Tako se dva čoveka retko sudaraju u istom fajlu.

**Sinhronizacija:** 13h i 20h, po 10 minuta. `main` uvek prolazi `pytest -q`. Grane žive maksimum jedan dan. (Detalji u `docs/GIT_WORKFLOW.md`.)

---

## 7. Rizici

| Rizik | Verovatnoća | Uticaj | Plan B |
|---|---|---|---|
| PG2 previše otporan i na ćirilicu (evazija < 20%) | srednja | visok | Pivot: fokus na *mehanizam* zašto je otporan + loose homoglifi + kombinacija sa drugim tehnikama iz 2504.11168. I dalje nalaz. |
| Open-weight model ne rešava AgentDojo taskove (benign utility < 30%) | srednja | srednji | API model za petlju, open za internals. Budžet $20–40. Odluka D4. |
| Nema ekskluzivnog/dovoljnog GPU-a | srednja | srednji | Statički deo (Čin I–II) radi na Colab-u. AgentDojo petlja na manjem podskupu. |
| AgentDojo API se lomi između verzija | niska | srednji | **Pinovati verziju D1**, ne ažurirati. |
| ActProbe ne radi ni na engleskom | srednja | visok | Fallback: prelazak na Čin IV nad postojećim; projekat ostaje kompletan (dijagnoza+mehanizam). |
| Kvalitet ćiriličnih injection-a (mašinski prevod) | niska | nizak | Native smo govornici — ručna provera svih ~30 template-a, ~1h. |
| Prevremeno curenje napada (etika) | niska | srednji | Odgovorno objavljivanje: Meta report kanal, javiti pre javne objave. |

---

## 8. Kill kriterijumi (kada menjamo pristup, bez žaljenja)

1. **D2 uveče:** ako nema krive evazije koja pokazuje jaz ćirilica-vs-engleski → premisa slabija, pivot na "mehanizam otpornosti PG2 + kombinovani napadi".
2. **D4 uveče:** ako napad ne radi end-to-end u AgentDojo-u → skratiti na statičku evaluaciju detektora (bez agent petlje), što je i dalje kompletan Čin I–II rezultat.
3. **D5 uveče:** ako ActProbe ne radi ni na engleskom → Čin III se proglašava negativnim nalazom, sva energija na Čin IV.

Pravilo: kill odluka se donosi **uveče, brojkom, ne osećajem**, i ne žali se za uloženim vremenom.

---

## 9. Definicija uspeha (šta pokazujemo na demo danu)

**Minimalni uspeh (osiguran do D2):** "Napravili smo napad koji homoglifima probija Prompt Guard 2 na srpskom sa X% uspeha, dok na engleskom prolazi samo Y%. Evo krive i evo zašto (fertility)."

**Ciljani uspeh (D5):** gornje + "napravili smo odbranu koja čita aktivacije modela umesto teksta, hvata napad koji filter propušta, uz nula dodatne latencije."

**Puni uspeh (D6):** gornje + "pokušali smo da razbijemo i sopstvenu odbranu; drži do budžeta X i na jezicima Y, pada na Z — evo poštene granice."

Sva tri su prezentabilna. Svaki sledeći je nadogradnja na prethodni, ne zamena.
