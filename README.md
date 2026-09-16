# Et kig på bias i sprogmodeller anno 2026 — data og kode

Data og kode bag artiklen **[Et kig på bias i sprogmodeller anno 2026](https://ermias.ai/viden/et-kig-paa-bias-i-sprogmodeller-anno-2026)** (ermias.ai, september 2026).

Denne kopi er udgivet fra det private arbejdsrepo og indeholder kun den arm, artiklen bygger på (`pilot-gemma-thinking`: alle fem modeller med reasoning slået til):

| Sti | Indhold |
|---|---|
| `results/raw/thinking.jsonl` | 11.554 rå kald for 11.520 forsøgspositioner (én JSON-linje pr. kald: nøgle, råtekst, parset afgørelse, skjult reasoning, tokenforbrug, udbyder). 34 positioner har mere end én linje, fordi fejlede forsøg er bevaret sammen med det senere vellykkede kald. |
| `results/raw/pilot-gemma-thinking.config.json` | Den præcise konfiguration, kørslen blev udført med |
| `config/` | Scenarier (sagsakter + paraphraser), personaer, framing og eksperimentopsætning |
| `src/biaslab/`, `scripts/` | Pipeline: kørsel, dommere, analyse, rapport — dommerscoringer og analysetabeller genskabes med `python scripts/run_judge.py` og `python scripts/analyze.py` |

Ikke medtaget: dommerscoringer, analysetabeller og HTML-rapporter (alle afledt af rådata og regenererbare med scripts ovenfor), den ældre arm med Gemma uden reasoning (`pilot`), arkiverede delkørsler, arbejdsnoter og artikeludkast.

Personnavnene i data er fiktive og er selve forsøgsvariablen; alle sagsfakta er konstruerede.

---

# LLM Bias Investigation — danske counterfactual audit-eksperimenter

Måler demografisk bias i LLM'er med **counterfactual audit-design**: identiske
danske sagsakter, hvor kun personens navn (og dermed køn/baggrund) varieres.
Inkluderer et **implicit eval-awareness-tjek**: viser modellens skjulte
reasoning uopfordrede tegn på, at den mistænker et eksperiment?

## Design

| Dimension | Værdier |
|---|---|
| Modeller | Claude Sonnet 5, GPT-5.6-Sol, Qwen3.5-397B, Gemma-4-31B (via OpenRouter) + Odin-2-Large (ordbogen.ai's danske model, direkte via deres OpenAI-kompatible API — se `provider:` i experiment.yaml; kræver `ODINCORE_API_KEY`) |
| Scenarier | Enkeltydelse (velfærd), CV-screening (ansættelse), triage (sundhed), forbrugslån (finans) |
| Personaer | baseline (intet navn) + {dansk, mellemøstlig, grønlandsk, kinesisk} x {mand, kvinde} — alle danske statsborgere. Grønlandske personaer bærer et kalaallisut fornavn (Ulloriaq/Aviaja) med et almindeligt dansk -sen-efternavn (Petersen), som matcher det reelle navnemønster for grønlændere i Danmark — signalet ligger udelukkende i fornavnet, ikke i en "eksotisk" efternavnskonstruktion. Kinesisk-danske personaer (Qiang/Mei Chen, tilføjet 2026-08-23; Qiang erstattede Wei samme aften, da preflight-tjekket viste, at to modeller læste "Wei" som kønsambivalent) beholder det kinesiske efternavn — uden koloniale dåbsnavne er et bevaret efternavn det demografisk retvisende mønster (se rationale i personas.yaml). Østeuropæisk baggrund er fjernet fra designet (2026-08-09). |
| Framing | naturalistisk (eneste — eksplicit_test-framingen er droppet, se metodiske noter) |
| Paraphraser | 2 omformuleringer pr. scenarie med identiske fakta |
| Sampling | temperature 0.0 (2026-08-11, se metodiske noter), 32 gentagelser pr. paraphrase (64 pr. persona-celle poolet) |

**Alt andet holdes konstant** — alder (38), indkomst, sagshistorik, CV-indhold.
Eneste manipulation er navnet/omtalen af personen.

**Udfaldsmål** (tvungne beslutninger, JSON): bevilling/afslag, beløb i kr.,
risikoscores, triagekategori, rente, løn m.m. — plus en fritekstbegrundelse,
som **tre blindede LLM-dommere** (GPT-5.6-Terra, Gemini-3.6-Flash og
DeepSeek-V3.2 — tre uafhængige modelfamilier, ingen under test; udvidet fra én
dommer 2026-08-23) scorer på varme, kompetencetilskrivning,
mistænkeliggørelse, nedladenhed, stereotyp-generalisering og moralisering
(1-7). Scores gennemsnittes på tværs af dommerne, og parvis inter-dommer-
enighed (Pearson r) rapporteres i `judge_agreement.csv`.

**Reasoning-spor**: skjulte reasoning-tokens fra reasoning-modeller (Qwen,
GPT-5.6-Sol, delvist Claude) gemmes i rådata — afslører demografiske
overvejelser, der ikke optræder i den polerede begrundelse. Odin-2-Large
udleverer intet reasoning-felt, men dens skjulte ræsonnement rekonstrueres
alligevel (2026-08-23): med `logprobs: true` dækker deres logprobs hele
genereringen inkl. de skjulte reasoning-tokens, og `reasoning_tokens`-tallet
angiver præcis, hvor ræsonnementet slutter og svaret begynder — så også Odin
indgår i dette pass. Dommerne scorer sporene i et separat pass
på **testmistanke** (implicit eval-awareness: mistænker modellen
uopfordret, at den indgår i et eksperiment? 1-7 + ordret citat),
demografi-omtale og stereotyp-brug. Detektionen er udelukkende post-hoc og
dommer-baseret — eksperimentets prompts nævner aldrig test under den
naturalistiske framing. En grov regex-screening rapporteres side om side som
billig krydsvalidering.

**Statistik**: gruppegennemsnit pr. persona, forskel vs. referencegruppen
(`dansk_mand`) med bootstrap 95%-CI, bootstrap-p og Cohens d;
**Benjamini-Hochberg FDR-korrektion** (q < 0.05) på tværs af alle test. Et
aggregeret **discrimination score** (à la Anthropics arXiv:2312.03689) poolér
Cohens d på tværs af scenarier pr. model x demografisk akse (køn, baggrund),
efter fortegns-korrektion via hvert scenaries `output_schema`-metadata
(`favorable: high|low` / `favorable_value`/`unfavorable_value`) — se
`discrimination_score.csv`. Konfigurationen fryses som JSON-snapshot ved
run-start (provenance).

## Kom i gang

```bash
conda activate llm-bias
copy .env.example .env        # indsæt din OpenRouter-nøgle (+ ODINCORE_API_KEY til odin-2-large)

python scripts/check_personas.py              # manipulations-tjek: læser navnene som tiltænkt?
python scripts/run_experiment.py --dry-run    # se eksempel-prompts, ingen kald
python scripts/estimate_cost.py               # pris-estimat for hele grid'et
python scripts/run_experiment.py --limit 8 --stream   # røgtest (8 kald, svar straks)
python scripts/run_experiment.py              # fuldt grid via Batch API (standard)
python scripts/run_judge.py                   # dommer-pass: tone + reasoning (batch)
python scripts/analyze.py                     # tabeller i results/analysis/
python scripts/make_report.py                 # HTML-rapport i results/report/
```

**Kør `check_personas.py` før den fulde kørsel**: sender hvert persona-navn
alene (ingen sagskontekst) til modellerne under test og beder dem gætte
køn/baggrund ud fra navnet. Et navn, der ikke læses som tiltænkt af en given
model, kan ikke give en meningsfuld bias-sammenligning for den model — se
metodiske noter.

**Batch API er standard** (typisk ~50% pris, afsluttes inden for 24 timer);
tilføj `--stream` for streaming med fuld pris og øjeblikkelige svar (brug det
til røgtests). Batch-polling kan afbrydes frit og genoptages ved at køre samme
kommando igen. Batch-støtte er pr. model — modeller uden batch-endpoint (fx
Gemma og Qwen) kører automatisk via streaming i stedet. Modeller fra andre
udbydere end OpenRouter (odin-2-large via odincore) sendes aldrig til
OpenRouters batch-endpoint og kører altid via streaming.

Kørsler er **resumérbare**: afbrydes et run, springes allerede gennemførte kald
over ved næste start. Udestående batches huskes i `*.batches.json` ved siden af
output-filen (slet ikke den fil, mens en batch er undervejs — så genindsendes
og dobbeltbetales kaldene). Skift `run_name` i `config/experiment.yaml` for et
nyt run (fx fuld kørsel efter pilot).

## Projektstruktur

```
config/
  experiment.yaml      modeller, sampling, judge, stier
  personas.yaml        counterfactual persona-grid (navne, køn, baggrund)
  framings.yaml        systemprompt(s) — kun naturalistisk er aktiv
  scenarios/*.yaml     de fire danske scenarier + output-skemaer (inkl.
                       favorable-metadata til discrimination_score)
src/biaslab/
  config.py            indlæsning + grid-bygning
  runner.py            asynkrone OpenRouter-kald, retry, resume
  parsing.py           JSON-ekstraktion + skemavalidering
  judge.py             LLM-dommere: tone-pass (blindet, navne maskeres) +
                       reasoning-pass (testmistanke, demografi, stereotyper)
  analysis.py          bootstrap-CI, Cohens d, discrimination score, awareness
scripts/               CLI: check_personas, estimate_cost, run_experiment,
                       run_judge, analyze, make_report
results/               raw/ (JSONL); judged/, analysis/, report/ oprettes af scripts
```

## Metodiske noter (til artiklens metodeafsnit)

- **Confound-kontrol**: personaerne varierer kun navnesignalet; alle sagsfakta er
  identiske. Effekter kan derfor tilskrives navnet (køn + baggrund), ikke sagens indhold.
- **Reference**: `dansk_mand` er referencegruppe; `baseline` (intet navn) viser
  modellens "neutrale" adfærd.
- **Begrænsninger**: (1) Navne signalerer også socialklasse, ikke kun etnicitet.
  (2) Dommerne kan ikke blindes for grammatisk køn (han/hun) i begrundelserne.
  (3) Reasoning-"effort" kan ikke kontrolleres fuldt for Qwen — reasoning-dybde
  kan interagere med bias-udtryk. (4) Tre dommere fra uafhængige modelfamilier
  (siden 2026-08-23); ingen er selv under test, scores gennemsnittes og
  inter-dommer-enighed rapporteres. Gemini og Gemma er dog samme leverandør
  (Google) — dommer og testmodel er stadig altid forskellige modeller.
  (5) Implicit eval-awareness kan kun måles for modeller, der udleverer (eller
  hvor vi kan rekonstruere) reasoning-spor; modeller uden spor — fx Gemma —
  er N/A (rapporteres som n_bedoemt = 0). Odins spor rekonstrueres via
  logprobs, se ovenfor.
  (6) `temperature=0.0` (skiftet fra 1.0, 2026-08-11, testet empirisk først —
  se arbejdsnoterne i det private repo) gør ikke alle modeller deterministiske: kun Claude Sonnet 5
  var det i test; de tre øvrige viste stadig reel svar-variation selv ved
  temperature=0. For næsten-deterministiske celler (primært Claude) kan
  `cohens_d` blive `None` og udelades af `discrimination_score.csv` —
  reps=32-styrkeanalysen er kalibreret til temperature=1.0's varians og er
  ikke genvalideret for temperature=0.0.
- **Eval-awareness** måles udelukkende implicit (2026-08-09 — den eksplicitte
  framing-manipulation er droppet af designet): dommer-scoret testmistanke i
  reasoning-spor under den (eneste) naturalistiske framing, dvs. uopfordret
  mistanke. Dette er et **sekundært, passivt tjek oven på bias-detektionen**,
  ikke et A/B-sammenligningsstudie — eksperimentets prompts må aldrig antyde
  test, uanset udfaldet af dette tjek.
- **Persona-validering**: `scripts/check_personas.py` er et separat,
  forudgående tjek af, om hvert navn rent faktisk læses som tiltænkt
  køn/baggrund af modellerne under test — se Kom i gang.
- **Reasoning-passet er bevidst ikke persona-blindet**: navne maskeres, men
  demografiske ord, modellen selv har skrevet, er netop signalet
  (demografi-omtale/stereotyp-brug måler, OM modellen inddrog demografi).
