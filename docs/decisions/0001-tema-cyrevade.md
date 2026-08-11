# ADR-0001: izbor teme — CyrEvade

**Datum:** 09.08.2026 · **Status:** prihvaćeno

## Kontekst
Birali smo između 4 teme (agent security × jezik, VLM halucinacije, speculative
decoding × pismo, CoT steering). Kriterijum koji je presudio: struktura od 4
čina (dijagnoza → mehanizam → artefakt → napad na artefakt) i to da impresivni
deo mora biti gotov rano.

## Odluka
T1 — CyrEvade. Cross-lingual homoglif napad na prompt-injection filtere +
odbrana iz aktivacija modela.

## Zašto (ne ostale)
- **Čin I gotov D2**, ne traži GPU ni AgentDojo — najbolja struktura rizika.
- Prava tenzija: normalizacija ruši srpski → odbrana u sukobu sa višejezičnošću.
- Mentor (Kristina Nikolić, SPY Lab) je autor AgentDojo infrastrukture.
- Problem dokumentovan brojkama (PG1 99.8%, "12 tehnika" do 100%).

## Alternative odbačene
- **T2 VLM** — najniži rizik ali popunjeniji prostor, slabiji "wow".
- **T3 SrbDraft** — najopipljiviji artefakt ali compute rizik (wall-clock).
- **T4 steering** — najveći rizik da hipoteza padne.

## Posledice
Zavisimo od pristupa Prompt Guard 2 (gated) i AgentDojo-a. GPU tek za Čin III.
