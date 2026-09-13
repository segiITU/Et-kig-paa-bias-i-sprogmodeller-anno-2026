"""Load experiment config and build the full condition grid."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@dataclass(frozen=True)
class Persona:
    id: str
    navn: str | None
    koen: str
    baggrund: str
    ref: str
    ref_short: str
    subj: str
    poss: str


@dataclass
class Scenario:
    id: str
    domaene: str
    rolle: str
    neutral_ref: str
    templates: list[str]
    output_schema: dict


@dataclass
class ModelSpec:
    id: str
    extra_body: dict = field(default_factory=dict)
    # Optional per-model cap overriding sampling.max_tokens. Keeps batch
    # preauth low for models that don't need the global (Qwen-sized) budget.
    max_tokens: int | None = None
    # "openrouter" (default), "odincore", or "alexandra" — selects which API
    # client/base_url runner._call_one uses (see runner.PROVIDERS). Non-
    # OpenRouter providers are never eligible for OpenRouter's Batch API
    # (run_batch routes them straight to streaming) and are absent from
    # OpenRouter's pricing catalog (estimate_cost.py carries an override).
    provider: str = "openrouter"
    # Optional automatic fallback if `provider` fails (e.g. a free-credit pool
    # runs dry): runner retries the call against `fallback_provider`, using
    # `fallback_id` as the wire model name there (provider ids can differ —
    # alexandra's "qwen3.5-397b" vs OpenRouter's "qwen/qwen3.5-397b-a17b").
    # Every record carries `served_by` naming the provider that actually
    # answered, so a fallback mix is tagged, never silent.
    fallback_provider: str | None = None
    fallback_id: str | None = None


@dataclass
class Condition:
    model: ModelSpec
    scenario: Scenario
    persona: Persona
    framing: str
    paraphrase: int
    rep: int
    system_prompt: str
    user_prompt: str

    @property
    def key(self) -> str:
        return (f"{self.model.id}|{self.scenario.id}|{self.persona.id}"
                f"|{self.framing}|p{self.paraphrase}|{self.rep}")


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_experiment(path: Path | None = None) -> dict:
    return _load_yaml(path or CONFIG_DIR / "experiment.yaml")


def load_framings() -> dict[str, str]:
    return _load_yaml(CONFIG_DIR / "framings.yaml")


def load_personas() -> tuple[list[Persona], int]:
    raw = _load_yaml(CONFIG_DIR / "personas.yaml")
    personas = [Persona(**p) for p in raw["personas"]]
    return personas, raw["alder"]


def load_scenarios() -> list[Scenario]:
    scenarios = []
    for path in sorted((CONFIG_DIR / "scenarios").glob("*.yaml")):
        raw = _load_yaml(path)
        scenarios.append(Scenario(**raw))
    return scenarios


def render_user_prompt(
    scenario: Scenario, persona: Persona, alder: int, paraphrase: int = 0
) -> str:
    if persona.navn is None:
        ref = scenario.neutral_ref
        ref_short = scenario.neutral_ref
        persona_line = f"{scenario.neutral_ref}, {alder} år"
    else:
        ref = persona.ref
        ref_short = persona.ref_short
        persona_line = f"{persona.navn}, {alder} år"
    return scenario.templates[paraphrase].format(
        persona_line=persona_line,
        ref=ref,
        ref_short=ref_short,
        subj=persona.subj,
        poss=persona.poss,
    )


def build_grid(cfg: dict) -> list[Condition]:
    """Full factorial: models x scenarios x personas x framings x paraphrases x reps."""
    framing_templates = load_framings()
    personas, alder = load_personas()
    scenarios = load_scenarios()
    models = [ModelSpec(id=m["id"], extra_body=m.get("extra_body") or {},
                        max_tokens=m.get("max_tokens"),
                        provider=m.get("provider", "openrouter"),
                        fallback_provider=m.get("fallback_provider"),
                        fallback_id=m.get("fallback_id")) for m in cfg["models"]]
    reps = cfg["sampling"]["repetitions"]

    conditions = []
    for model, scenario, persona, framing in itertools.product(
        models, scenarios, personas, cfg["framings"]
    ):
        system_prompt = framing_templates[framing].format(rolle=scenario.rolle).strip()
        for paraphrase in range(len(scenario.templates)):
            user_prompt = render_user_prompt(scenario, persona, alder, paraphrase)
            for rep in range(reps):
                conditions.append(
                    Condition(model, scenario, persona, framing, paraphrase, rep,
                              system_prompt, user_prompt)
                )
    return conditions
