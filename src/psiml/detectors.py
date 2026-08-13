"""Jedinstveni interfejs za detektore prompt injection-a — "lestvica detektora".

Kristinino upozorenje: proveriti da li je detektor treniran za PROMPT INJECTION
(AgentDojo stil: "posalji mejl osobi X") ili samo za JAILBREAK / harmful output
("kako napraviti bombu"). To su razliciti zadaci i razliciti trening skupovi.

Zato ovde ne biramo jedan detektor nego pravimo LESTVICU, poredanu po
visejezicnoj pokrivenosti. To je i eksperimentalni dizajn: pokazuje koliko
visejezicne pokrivenosti treba pre nego sto homoglifi postanu NEOPHODNI.

    ProtectAI v2      injection-specific, ENGLESKI ONLY  -> sam srpski ga obara
    Deepset           injection-specific, engleski        -> isto
    PromptGuard 2 86M injection+jailbreak, 8 jezika (mDeBERTa) -> treba homoglif
    PromptGuard 2 22M injection+jailbreak, slabiji multiling.  -> medju njima

Poenta lestvice: ako ProtectAI padne na golom srpskom (bez ikakvog napada), to
je trivijalan ali koristan baseline. Pravi cilj je PG2, koji JESTE visejezican
i JESTE evaluiran na AgentDojo-u (model card: APR 81.2% @ 3% utility reduction).

Svi detektori se svode na isti interfejs: `score(text) -> float u [0,1]`, gde
je veci broj = detektor je sigurniji da je malicious. Tako CyrEvade pretraga
radi nad bilo kojim od njih bez izmene.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Detector(Protocol):
    """Minimalni interfejs koji CyrEvade pretraga ocekuje."""

    name: str

    def score(self, text: str) -> float:
        """Vraca [0,1]; veci = vise 'malicious'."""
        ...


@dataclass(frozen=True)
class DetectorSpec:
    """Metapodaci o detektoru — sta je, na cemu je treniran, koji jezici.

    Ovo NIJE dekoracija: kolone `task` i `languages` su direktno ono sto
    Kristina trazi da proverimo, i idu u tabelu u radu.
    """

    key: str
    hf_id: str
    task: str            # "injection" | "injection+jailbreak"
    languages: str       # sta model card tvrdi
    gated: bool          # da li treba trazit pristup na HF-u
    note: str


# Registar — jedini izvor istine o tome sta testiramo.
REGISTRY: dict[str, DetectorSpec] = {
    "protectai_v2": DetectorSpec(
        key="protectai_v2",
        hf_id="protectai/deberta-v3-base-prompt-injection-v2",
        task="injection",
        languages="engleski (model card eksplicitno: ne rukuje ne-engleskim)",
        gated=False,
        note="Injection-specific, NIJE za jailbreak. Ocekujemo pad na golom srpskom.",
    ),
    "deepset": DetectorSpec(
        key="deepset",
        hf_id="deepset/deberta-v3-base-injection",
        task="injection",
        languages="engleski",
        gated=False,
        note="Stariji, jednostavan baseline. INJECTION vs LEGIT.",
    ),
    "promptguard2_86m": DetectorSpec(
        key="promptguard2_86m",
        hf_id="meta-llama/Llama-Prompt-Guard-2-86M",
        task="injection+jailbreak",
        languages="en, fr, de, hi, it, pt, es, th (8) — srpski NIJE",
        gated=True,
        note="GLAVNI CILJ. mDeBERTa multiling. Adv-resistant tokenizacija. "
             "Model card: AgentDojo APR 81.2% @ 3% utility reduction.",
    ),
    "promptguard2_22m": DetectorSpec(
        key="promptguard2_22m",
        hf_id="meta-llama/Llama-Prompt-Guard-2-22M",
        task="injection+jailbreak",
        languages="slabija visejezicnost (nema multiling. deberta-xsmall)",
        gated=True,
        note="Model card priznaje veci multilingual gap od 86M. Zanimljiv kontrast.",
    ),
}


class HFDetector:
    """Omotac oko HuggingFace text-classification modela.

    Normalizuje razlicite label seme (INJECTION/LEGIT, MALICIOUS/BENIGN,
    LABEL_0/LABEL_1) u jedan broj: verovatnoca "malicious" klase.

    Ucitavanje je LENJO (tek pri prvom `score`) da bi se registar mogao
    inspektovati bez skidanja gigabajta.
    """

    def __init__(self, spec: DetectorSpec, device: str = "cpu", batch_size: int = 16) -> None:
        self.spec = spec
        self.name = spec.key
        self.device = device
        self.batch_size = batch_size
        self._pipe = None
        self._cache: dict[str, float] = {}

    def _ensure_loaded(self) -> None:
        if self._pipe is not None:
            return
        from transformers import pipeline  # lokalni import: modul radi i bez torch-a

        self._pipe = pipeline(
            "text-classification",
            model=self.spec.hf_id,
            device=self.device,
            truncation=True,
            max_length=512,
            top_k=None,  # vrati SVE klase, da sami biramo koja je 'malicious'
        )

    @staticmethod
    def _malicious_prob(scores: list[dict]) -> float:
        """Iz liste {label, score} izvuci verovatnocu 'malicious' klase.

        Razliciti modeli koriste razlicite nazive; pokrivamo poznate seme.
        Ako nista ne prepoznamo, uzimamo klasu koja NIJE benigna.
        """
        benign_names = {"benign", "legit", "safe", "label_0"}
        malicious = 0.0
        for entry in scores:
            label = str(entry["label"]).strip().lower()
            if label not in benign_names:
                malicious = max(malicious, float(entry["score"]))
        return malicious

    def score(self, text: str) -> float:
        return self.score_many([text])[0]

    def score_many(self, texts: list[str]) -> list[float]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            self._ensure_loaded()
            for i in range(0, len(missing), self.batch_size):
                chunk = missing[i: i + self.batch_size]
                out = self._pipe(chunk, batch_size=len(chunk))
                for txt, entry in zip(chunk, out):
                    sc = entry if isinstance(entry, list) else [entry]
                    self._cache[txt] = self._malicious_prob(sc)
        return [self._cache[t] for t in texts]


class MockDetector:
    """Lazni detektor za razvoj bez GPU-a. NIKAD u rezultate."""
    TRIGGERS = ("ignore","disregard","previous instruction","override",
                "send","forward","transfer","api key","password",
                "important message","before you can solve")
    def __init__(self, name: str = "mock") -> None:
        self.name = name
        self.spec = type('S', (), {'key':'mock','hf_id':'','task':'','languages':'','gated':False,'note':''})()
    def score(self, text: str) -> float:
        low = text.lower()
        hits = sum(1 for t in self.TRIGGERS if t in low)
        return 0.02 if hits == 0 else min(0.99, 0.45 + 0.18 * hits)
    def score_many(self, texts: list[str]) -> list[float]:
        return [self.score(t) for t in texts]


def get_detector(key: str, device: str = "cpu", batch_size: int = 16):
    """Fabrika po kljucu iz REGISTRY. `mock` ne dira mrezu ni GPU."""
    if key == "mock":
        return MockDetector()
    if key not in REGISTRY:
        raise KeyError(f"Nepoznat detektor '{key}'. Dostupni: {list(REGISTRY)}")
    return HFDetector(REGISTRY[key], device=device)


def summary_table() -> str:
    """Tekstualna tabela registra — ide direktno u rad i u poruku mentoru."""
    rows = [f"{'kljuc':<18} {'zadatak':<20} {'gated':<6} jezici"]
    rows.append("-" * 88)
    for s in REGISTRY.values():
        rows.append(f"{s.key:<18} {s.task:<20} {str(s.gated):<6} {s.languages}")
    return "\n".join(rows)
