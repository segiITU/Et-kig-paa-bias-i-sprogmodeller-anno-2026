# Artiklen skifter til `pilot-gemma-thinking` — hvad der ændrede sig

**Dato:** 2026-09-04 · **Beslutning:** rent snit. Alle Gemma-tal i artiklen kommer
nu fra `results/raw/pilot-gemma-thinking.jsonl` (Gemma med `reasoning: {enabled: true}`).
Formuleringen »Gemma med tænkning slået fra« findes ikke længere i teksten, fordi
den ikke længere er nødvendig: alle fem modeller i undersøgelsen er ræsonnerende
modeller, og alle fem blev kørt med ræsonnement til rådighed.

`pilot`-armen er ikke slettet. Den ligger uændret som `results/raw/pilot.jsonl` med
Gemma-delen kopieret til `results/raw/archive/pilot_gemma_thinking-off_2026-08-30.jsonl`,
og sammenligningen mellem de to arme står i `docs/2026-08-30-gemma-thinking-arm.md`.
Den er nu baggrundsmateriale, ikke artiklens datagrundlag.

**Ét forbehold, der ikke forsvinder med skiftet:** Claude Sonnet 5 tænkte reelt ikke
på 845 af sine kald. Det er modellens egen routing, ikke vores konfiguration, så
»alle fem er ræsonnerende modeller« er korrekt, mens »alle fem tænkte på hvert kald«
ikke er. Afsnit 7 siger fortsat det første og ikke det andet.

---

## 1. Fund, der forsvandt

| Fund | Hvor | Hvorfor |
|---|---|---|
| Gemmas renteforskel (761 kr., Qiang +0,45 pp) | afsnit »Navnet på låneansøgningen« | Ingen `rente_pct`-forskel hos Gemma er signifikant i thinking-on-armen |
| Ahmed får den mindst hastende triagekategori (3,00 mod 2,81) | afsnittet »Fire spørgsmål« | Ahmed går fra højest til midterfeltet; ikke signifikant |
| Mette er næstdyrest på renten | samme afsnit | Gemmas renteforskelle er væk |
| »Gemma er slet ikke en ræsonnerende model« | afsnit 7 | Var forkert allerede før skiftet; nu også modbevist i data |

## 2. Fund, der kom til

- **Smertetroværdighed.** Mikkel er den mindst troede patient af alle ni. Gemma
  svarer kun 9 eller 10, og trækker point fra i 66 % af Mikkels kald mod 27 % af
  Qiangs og 14 % af den navnløses. Fem af otte sammenligninger er signifikante.
  **Bærer nu artiklens første resultatafsnit.**
- **Det samme mønster hos GPT-5.6 Sol**, stærkere (Fatima +0,72, Mei +0,69).
  To modeller, to virksomheder, samme retning — fund nr. 3 i »De største fund« er
  opskrevet fra én model til to.
- **Ventetid.** Ahmed +3,8 min., Mei +5,6 min. mod Mikkel, begge signifikante.
- **Qiang.** Højere egnethed (+0,17) og lavere misbrugsrisiko (−0,31) — begge i hans
  favør — men koldere sprog i begrundelsen (varme −0,22). Ikke brugt i teksten endnu.
- **`reasoning_demografi_omtale` for Gemma** går fra 2 rækker til 2.304. Blandt de
  navngivne personaer (baseline-rækkerne er mekaniske og skal ignoreres) omtaler
  Gemma demografi signifikant mere for Mette og Fatima, mindre for Qiang og Ulloriaq.
  Ikke brugt i teksten endnu.

## 3. Hvert tal, der er rettet

### `docs/artikel-fuldt-udkast.md`

| Sted | Før | Efter |
|---|---|---|
| Indledningens tre svar | »på renten, ja, i én af de fem« | »nej: i den eneste model med signifikante renteforskelle er det den danske mand, der betaler mest« (Odin: Mikkel 6,11 %, højest af ni) |
| Fund 1 | 136 af 2.184 (6,2 %) | 107 af 2.280 (4,7 %) |
| Fund 3 | kun GPT-5.6 Sol | GPT-5.6 Sol **og** Gemma |
| Resultatafsnit 1 | »Navnet på låneansøgningen« (rente) | »Hvem bliver troet på, når det gør ondt« (smertetroværdighed) |
| Odin-triageafsnittet | egen beskrivelse af patienten | tilbagehenvisning, da patienten nu introduceres ovenfor |
| Ahmed i sundhedsvæsenet | triagekategori 3,00 mod 2,81 | ventetid +3,8 min. (Mei +5,6) |
| Kvinder i banken | »Mette næstdyrest hos Gemma« | ingen forskel i kvindernes disfavør; Odin giver Mette 0,59 pp mindre |
| Nulresultater, løn | 6 af 40 signifikante | 4 af 40 |
| Nulresultater, risikoscorer | 2 af 40 | 1 af 80 |
| Model-vs-navn | »Gemma estimerer 46-60 minutter« | 60-66 minutter |
| Afsnit 2, parafrasetabellen | 2 Gemma-rækker (rente, ventetid) | 4 Gemma-rækker (ventetid, egnethed, triagekategori, startløn) |
| Afsnit 7, synlighedstabellen | Gemma 0,09 % / 0,09 % / »ikke en ræsonnerende model« | Gemma 100 % / 100 % / »tænker, viser det altid«, flyttet op til de øvrige fuldt dækkede modeller |
| Afsnit 7, brødtekst | »Gemma optræder slet ikke i den del af analysen« | Odin, Qwen og Gemma har fuld dækning, ingen skjult udvælgelse |
| Afsnit 7, eval-bevidsthed | »slet ikke en påstand for Gemma« | solid for Odin, Qwen og Gemma |
| Dommer-bedømmelser | 56.832 | 63.738 |
| Fund fra dommerscorer | 79 af 136 | 64 af 107 (22 tone + 42 ræsonnement) |

### `docs/tables-for-article.md`

Provenans-linjen, tabel 2 (Gemma-kolonnen til 256 hele vejen, total 2.304, seks
fejlede records i stedet for otte), tabel 3 (ræsonnement-gennemløb 7.426 → 9.728),
tabel 5 (samme tal, Gemma-rækken omskrevet og flyttet op), tabel 7
(bedømmelser 63.738, sammenligninger 2.280, signifikante 107).

### `docs/artikel-afsnit-3-og-4-udkast.md`

Samme tælletal som ovenfor. **Bemærk:** filen er en tidligere delversion, hvis
indhold allerede ligger i det fulde udkast. Den er opdateret for konsistens, men
hvis den er død, kan den arkiveres.

### `docs/excalidraw-omskrivning-prompt.md`

Række 1 udskiftet: Gemmas rente → **Gemmas egnethedsvurdering** (alle ni på præcis
9,00 under punktform; 9,00-9,38 under prosa med Qiang på 9,38). Række 2 fik nye tal
(punktform 59,5-71,2 med Mei øverst; prosa alle otte navngivne på 60,0). Rækkerne
3-6 er urørte — de bygger på records, der er identiske i begge arme. Den lille
én-rækkes variant peger nu på egnethed i stedet for rente.

---

## 4. Det, du selv skal se på

1. **Fodnoten om parafraseretningen** i excalidraw-prompten (»43 målbare udfald,
   24 mod 19, fortegnstest p = 0,27«) er beregnet på `pilot` med et script, jeg ikke
   kunne reproducere — min egen optælling giver 39 ikke-uafgjorte udfald på `pilot`,
   ikke 43. Konklusionen ændrer sig ikke ved armskiftet (min metode giver 18/21 på
   `pilot` og 19/21 på thinking-on, begge klart ikke-signifikante), men **tallene i
   fodnoten bør genberegnes med dit oprindelige script**, før figuren går i tryk.
2. **De 11 grænsetilfælde.** Ingen enkelt models data ændrede sig — alle `diff`-værdier
   er identiske — men BH-FDR beregnes på tværs af hele tabellen, og da Gemmas
   p-værdier flyttede sig, faldt 11 ikke-Gemma-rækker ind eller ud omkring q = 0,05:

   | Model | Udfald | Persona | q før → efter |
   |---|---|---|---|
   | Odin | egnethed | baseline | 0,039 → 0,062 |
   | Odin | judge_mistaenkeliggoerelse | Qiang | 0,050 → **0,043** |
   | Odin | reasoning_demografi_omtale | baseline | 0,023 → 0,062 |
   | Odin | judge_kompetence_tilskrivning | Mei | 0,029 → 0,050 |
   | Odin | judge_nedladenhed | Mette (kredit) | 0,039 → 0,062 |
   | Odin | judge_nedladenhed | Mette (velfærd) | 0,034 → 0,079 |
   | GPT | reasoning_demografi_omtale | Qiang | 0,016 → 0,057 |
   | GPT | beloeb_dkk | baseline | 0,034 → 0,079 |
   | Qwen | judge_kompetence_tilskrivning | Aviaja | 0,009 → 0,062 |
   | Qwen | judge_kompetence_tilskrivning | Ahmed | 0,039 → 0,085 |
   | Qwen | afgoerelse=delvis_bevilling | Aviaja | 0,045 → 0,091 |

   Ingen af dem bærer et fund i artiklen, men hvis du citerer et af dem et sted, jeg
   ikke har fanget, er det nu støj.
3. **`config/experiment.yaml` bliver stående på `run_name: pilot-gemma-thinking`.**
   Det er nu den publicerede arm. Skift det ikke tilbage.
4. **`results/report/frame-review.html`** er ikke namespaced og indeholder i dag
   thinking-on-kørslen. Det er nu det rigtige — men den er stadig kun regenerérbar
   ved at skifte `run_name`, så rør den ikke.
5. **Ikke rørt af skiftet, og stadig forkert:** påstanden »Vidste modellerne, at de
   blev testet? Nej.« (omkring linje 507) er kendt forkert for Qwen — 139 spor siger
   direkte, at sagen er en simulation (FINDINGS.md 2026-08-30). Caveat 7 lyder nu
   »solid for Odin, Qwen og Gemma«; Gemma-halvdelen er velunderbygget af den nye arm
   (ét flagget spor ud af 2.304), men Qwen-halvdelen er den gamle fejl. Det er en
   selvstændig opgave, som armskiftet hverken løste eller forværrede.

---

## 5. Rapporterne

Genereret på ny 2026-09-04 fra thinking-on-armen:

| Fil | Status |
|---|---|
| `results/report/frame-review.html` | **Regenereret.** 358 flagede spor med frame-scorer. Filen er ikke namespaced, så den har altid kun én arm ad gangen — nu den rigtige. |
| `results/report/pilot-gemma-thinking.html` | **Regenereret** (79 MB). Det er den aktuelle fulde rapport. |
| `results/report/pilot.html` | Nu en henvisningsside til ovenstående. Den gamle thinking-off-rapport ligger som `results/report/archive/pilot_thinking-off_2026-08-25.html`. Bevidst ikke en kopi — en kopi ville blive forældet ved næste `make_report.py`-kørsel uden at nogen opdagede det. |

`scripts/build_data_appendix.py` havde `RUN = "pilot"` hårdkodet. Den læser nu
`run_name` fra `config/experiment.yaml` som de øvrige scripts. **Appendikset er
IKKE genereret på ny** — se nedenfor.

## 6. De tre publicerede sider er nu opdateret

`findings.html`, `findings-da.html` og `data-appendix.html` er bragt over på
thinking-on-armen 2026-09-04.

**Nyt script: `scripts/update_findings_data.py`.** Findings-siderne er håndskrevne,
men score-tabellerne nederst drives af ét indlejret `const DATA = {...}`. Det
regenereres nu fra kildedata i stedet for at blive rettet i hånden. Prosaen røres
ikke, og de to sprogversioner beholder hver deres labels.

Scriptet er valideret ved at *reproducere* de gamle sider: bygget mod `pilot` giver
det 2.193 celler med **nul afvigelser** fra det, der stod i filerne. Det krævede at
midlerne beregnes i fuld præcision fra kilden — analyse-CSV'erne gemmer kun tre
decimaler, hvilket ikke er nok til at ramme tabellernes egen afrunding på præcise
halve (9,125 → 9,12, ikke 9,13).

Mod den publicerede arm giver det 2.295 celler: **102 nye**, som alle er Gemmas
ræsonnement-celler. De fandtes ikke før, fordi Gemma havde to spor i alt — nu har
den 2.304, og modellen optræder derfor for første gang i sidernes
ræsonnement-tabeller.

Prosarettelser i begge sprogversioner:

| Sted | Før | Efter |
|---|---|---|
| Nøgletal øverst | 56.832 bedømmelser · 136 af 2.184 · 6,2 % | 63.738 · 107 af 2.280 · 4,7 % |
| Smertetroværdigheds-kortet | »En anden model troede mere på…« (kun GPT) | »To modeller…« — Gemma tilføjet med 81 % mod 34 %, fem af otte signifikante |
| Forbehold: parafraser | Gemmas 6,50 % rente / 32,8-60,0 min. | egnethed 9,00 flad / ventetid 59,5-71,3 |
| Forbehold: ræsonnement-dækning | »Gemma er slet ikke en ræsonnerende model« | Gemma viser spor hver gang; »to af de 34« → »ét af de 42« |
| Forbehold: dommerscorer | 79 af 136 (45 tone + 34 ræsonnement) | 64 af 107 (22 + 42) |
| Eval-bevidsthed | »ingen model viste tegn på at ane, at den blev testet« | rettet: frame-passets tre dimensioner med tal, og eksplicit »rater inden for den flagede delmængde, aldrig i korpusset« |
| Sidefod | Kørsel `pilot`, 11.518 af 11.520 brugbare | `pilot-gemma-thinking`, 11.513 af 11.520 |

**To tællefejl fundet undervejs, begge ældre end armskiftet:**

1. Sidernes »11.518 af 11.520 brugbare celler« var forkert i begge arme — 11.518 er
   antallet af rækker i tone-passet, ikke antallet af brugbare celler. Sandheden er
   **11.512 for `pilot` og 11.513 for `pilot-gemma-thinking`** (dedupliceret på
   `Condition.key`, uden poster med `parse_errors`). `docs/tables-for-article.md`'s
   tabel 2 havde samtidig odin på 2.301; det korrekte tal er 2.300, og
   `kinesisk_mand`-cellen er 254, ikke 255. Rettet begge steder.
2. `scripts/build_data_appendix.py` talte rå linjer i stedet for celler, så
   genforsøg og poster med et parset felt men fejlet validering blev talt med
   (11.519 i stedet for 11.513). Loopet deduplikerer nu på `key` og springer
   `parse_errors` over, så appendikset stemmer med de CSV'er, det dokumenterer.

**Republiceret 2026-09-04** til de samme URL'er (indholdet er uændret bortset fra
ovenstående; ingen af de to sider var blevet redigeret i Artifact-editoren, hvilket
blev verificeret ved at hente den live version og sammenligne både prosa og
data-blob linje for linje før udgivelse):

| Side | Artifact |
|---|---|
| `findings.html` | https://claude.ai/code/artifact/e8e271a0-4f99-4013-bae2-4f54edac02b9 |
| `findings-da.html` | https://claude.ai/code/artifact/bf70fb7f-f608-43cd-8585-cad794c17380 |

| `data-appendix.html` | https://claude.ai/code/artifact/ed89c126-b253-4487-9811-237e21ad67a4 |

**OBS på appendikset: det er delt med »alle med linket«, og delingen peger på en
FASTGJORT tidligere version.** En republicering opdaterer den live version, men
læsere med linket ser fortsat den fastgjorte gamle udgave, indtil fastgørelsen
opdateres i sidens delingsmenu. Det skal gøres i browseren, før linket sættes i
artiklen — ellers henviser artiklen til `pilot`-tallene.

---

## 7. Oprydning 2026-09-04

Projektet er nu et git-repo (`git init`, remote
`https://github.com/segiITU/llm-bias-investigation.git`, ikke pushet). Første commit
er taget FØR sletningerne nedenfor, så de kan hentes tilbage.

Slettet:

| Sti | Størrelse | Sådan får du den igen |
|---|---|---|
| `results/analysis/pilot/` | 389 KB | `git checkout d93f676 -- results/analysis/pilot` (eller `run_name: pilot` + `analyze.py`) |
| `results/report/archive/pilot_thinking-off_2026-08-25.html` | 72 MB | Ikke i git (ignoreret pga. størrelse): `run_name: pilot` → `analyze.py` → `make_report.py` |

Tilføjet til `.gitignore`: LibreOffice-lockfiler og de 70-80 MB store per-kørsel-rapporter.
`.env`, `results/raw/` og `results/judged/` var ignoreret i forvejen — bemærk at
**rådata dermed IKKE ligger i repoet** og ikke er dækket af denne sikkerhedsnet.

**Ikke slettet, med vilje:** `PILOT-REPORT.md` (efter aftale urørt, men den har stadig
pilot-tallene og modsiger nu alt andet), `docs/artikel-fuldt-udkast.md` (den ENESTE
kilde til den rettede Gemma-tekst) og `docs/artikel-afsnit-3-og-4-udkast.md` (kun 6 %
af dens lange afsnit går ordret igen i det fulde udkast — den er ikke en dublet).

## 8. Artiklen i .odt er ikke opdateret

`LLM-bias-article_5.odt` er den aktive artikel og indeholder **ikke** nogen af
2026-09-04-rettelserne: 761-kroners-afsnittet, »alle ni ansøgere præcis 6,50 %« og
»136 af 2.184« står der stadig, og hverken smertetroværdighedsafsnittet eller
»107 af 2.280« findes i den.

Den kan ikke bare genereres fra `docs/artikel-fuldt-udkast.md` igen: den er
håndredigeret i Writer og er drevet fra markdown-udkastet (fx »der vælter budgettet«
mod markdownens »der vælter nogen«). En regenerering ville slette de rettelser.
Ændringerne skal derfor ind manuelt — se ændringslisten i afsnit 3.

`LLM-bias-article_3.odt` og `_4.odt` er i øvrigt byte-identiske.

---

## 9. Rettelse 2026-09-04: dommertallet var 63.765, det er 63.738

Da tallet blev kontrolleret, viste det sig at være forkert. Jeg havde taget
nævneren for ræsonnement-passet fra ANTALLET AF LINJER i gemini-dommerens fil
(9.737). Den fil indeholder ni dublerede rækker fra en genoptagelse. Talt på
unikke `Condition.key` scorede alle tre dommere **9.728** spor.

Korrekt regnskab: 3 × (11.518 tone + 9.728 ræsonnement) = **63.738**.
Frame-passet (3 × 358 = 1.074) har aldrig været med i det tal.

Samme linje-mod-unik-nøgle-fejl ramte tabel 5's modelrækker. Talt på unikke
nøgler:

| Model | synligt spor | tænkte reelt | tilbageholdt |
|---|---|---|---|
| odin-2-large | 2.304 (100 %) | 2.304 | 0 |
| qwen3.5-397b | 2.304 (100 %) | 2.304 | 0 |
| google/gemma-4-31b-it | 2.304 (100 %) | 2.304 | 0 |
| anthropic/claude-sonnet-5 | 1.444 (62,7 %) | 1.457 (63,2 %) | 13 |
| openai/gpt-5.6-sol | 1.372 (59,5 %) | 2.298 (99,7 %) | **926** |
| **I alt** | **9.728** | 10.667 | |

Det betyder, at Claude reelt ikke ræsonnerede i **847** kald (ikke 845), og at GPT
fik tilbageholdt **926** spor (ikke 925). **`LLM-bias-article_5.odt` havde de
rigtige tal hele tiden** — 62,7/63,2, 847 og 926 — mens markdown-udkastet og
tables-for-article havde de forkerte. Dem er rettet nu, og punktet »ræsonnement-
tabellen skal du ikke røre« i ret-listen står stadig, nu af den rigtige grund.

Rettet i: `tables-for-article.md` (+ .odt genereret på ny), `artikel-fuldt-udkast.md`,
`artikel-afsnit-3-og-4-udkast.md`, `2026-09-04-odt-rettelser.md`, dette notat samt
`findings.html` / `findings-da.html`, som er republiceret. Data-appendikset
indeholdt aldrig tallet og er urørt.
