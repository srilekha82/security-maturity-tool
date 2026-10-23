# AI RMF assessment model and mapping (agreed 2026-10-16 to 2026-10-21)

The model the AI RMF track is built on: **how AI is used and what the AI is made of (AI areas) -> the attack areas they
impact -> questions per AI RMF function -> maturity per AI RMF subcategory**. Start every design discussion from this
note. It replaces the applicability judge and the CIS linker as decision makers. Build steps are in `TODO.md`.

## Why the change
- The applicability judge (`prompts/ai_rmf_applicability_judge.md`, removed 2026-10-22) decided everything; `record_ai_bank.py` checked only the format. The recorded
  applicability (2026-10-14) left the asset categories almost empty: consumer `data_exposure` 2 of 72 subcategories,
  `infra_hosting` 1, producer `build_infra` 1, while governance and reliability got 16 to 20 each. The Playbook says
  little about security, so an agent mapping from Playbook text alone under-maps the attack surface.
- `question_categories.json` held the usage model, but it was hard to read, hid the consumer assets inside
  `data_exposure`, and its category-level fields were read by no script.
- Usage met the Playbook and CIS only through agent decisions. Nothing linked them deterministically.

## 1. AI areas: the decision, in a spreadsheet
`data/ai/authoring/ai_areas.xlsx` is written by a person and is the decision. `scripts/sheet_io.py import ai_areas`
checks it and writes `data/ai/ai_areas.json`, which scripts and agents read. Columns: ID, AI area, Kind, Applies to,
Impact, What it covers, Example question (spreadsheet only).

| AI area | Kind | Applies to | Impact |
|---|---|---|---|
| Internal process | usage | both | process, data |
| Code generation (AI-specific part only; secure development is assessed by the CSF) | usage | both | assets, data |
| Customer-facing application | usage | both | process, data |
| Vendor AI (vendors and products running AI on the org's data: Jira, Slack, ServiceNow, GitHub, RPA) | usage | both | data |
| Model building (the job of owning a model, built from scratch or on an existing one: purpose and design, evaluation before use, the base model, release to others) | usage | producer | assets |
| Invisible AI usage (unapproved inside, or others' agents, MCP clients and scrapers reaching in) | usage | both | data, access |
| Input | component | both | data |
| Output (wrong answers that are then trusted: steered by an attacker, or simply inaccurate, inconsistent or drifting) | component | both | process |
| Test, tuning and evaluation data (incl. the harness reliability is measured with, feedback reused for tuning) | component | producer | data, assets |
| Model (as IP) | component | producer | assets |
| Source data (RAG / knowledge graph; includes data classification) | component | both | data, access |
| MCP / tools (hosted inside or used from outside; an outside server is also a supplier) | component | both | access |
| Agent | component | both | access, process |
| Hosting (a model the org hosts, as a producer or for a PoC) | component | both | assets |

- **Kind:** usage is a way AI is used (or used around the org); component is a part of the AI ecosystem.
- **Impact** is the attack area a failure hits: **data** (exposed, leaked, poisoned), **access** (permissions and
  credentials used or abused), **process** (a business process or decision goes wrong), **assets** (model, code or
  infrastructure stolen, damaged or taken down).
- GOVERN is the foundation and is not mapped to AI areas (section 3).
- Whether general security (CSF, ISO 27001) already covers a question is decided per mapping row, not per area: when a
  row's CIS safeguard maps (official CIS -> CSF mapping) to a CSF subcategory the client was assessed on, the question
  asks only the AI-specific part.

## 2. Intake: the client's AI areas
The intake asks only what the org has (capability); every control is assessed by the questions.
- AI in use: none / some / unsure.
- "Do you build AI, use AI, or both?" (consumer / producer / both). Build or both brings the producer areas (model building,
  model, test / tuning / evaluation data) and two follow-ups: "Is your model built on an existing model?" (turns on the
  base-model questions: MANAGE 3.2 pre-trained models monitored, MAP 4.1, GOVERN 6.1) and "Do you give the model to
  others?" (turns on the release questions: clients, partners, an API, devices, open weights).
- "How do you use AI?" (pick all): internal process, code generation, customer-facing application, vendor AI.
- "What does your AI include?" (pick all): RAG / knowledge graph, MCP / tools, agents, a model you host.
- Engagement flags (CSF assessment done, ISO 42001); ISO 27001 from the certifications.

`intake.py` writes the client's areas to `ai_usage.json` (`ai_areas`): the ones ticked, plus the automatic ones in
`data/ai/scope_rules.json` `ai_area_rules`:
- always (even with no AI in use): invisible AI usage
- any AI in use: input, output
- role producer or both: model building, model, test / tuning / evaluation data; agents add MCP / tools.

`ai_usage.json` holds `role`, `producer` (`built_on_existing_model`, `given_to_others`; null for a consumer) and
`ai_areas`. Until question selection works on AI areas (TODO step 4) the intake also writes the old fields (rung, usage
contexts, modifiers, hosts_model), worked out from the areas (`legacy_profile` in `scope_rules.json`).

## 3. Controls: GOVERN is the foundation; MAP, MEASURE and MANAGE are asked per AI area
Agreed 2026-10-22, after the `mcp_tools` pilot mapped operational controls under GOVERN labels (GOVERN 2.1 citing an
access-granting safeguard, GOVERN 6.2 citing a containment procedure). The Playbook's own statement of each function
(parsed into `data/ai/ai_rmf_core.json` `functions[].description`) is the guide:

| Function | Playbook statement | What it is here |
|---|---|---|
| GOVERN | Policies, processes, procedures and practices across the organization related to the mapping, measuring and managing of AI risks are in place, transparent, and implemented effectively. | **Foundation**: how the organisation works with AI (policies, roles, inventory, culture, third parties). It defines how MAP, MEASURE and MANAGE are done. Not mapped to an area. |
| MAP | Context is established and understood. | **Context**: the AI areas applied to the organisation's systems, processes, assets and data; reach, components, purpose, risks and impacts. |
| MEASURE | Appropriate methods and metrics are identified and applied. | **Operations, checking**: the area's risks tested, evaluated and monitored (security, reliability, safety, fairness, privacy). |
| MANAGE | AI risks based on assessments and other analytical output from the Map and Measure functions are prioritized, responded to, and managed. | **Operations, responding**: risks prioritised and treated (access control, encryption, separation), switched off, incidents responded to, rectified and recorded. |

- **Foundation (GOVERN, all 19 subcategories):** asked once for the organisation, not through an AI area. Everything
  is org-wide; the difference is that a GOVERN question does not depend on which AI areas the client has. Its
  questions are written per subcategory in the bank build and picked at engagement time by the intake role: none,
  consumer, producer (both = consumer and producer; a producer flag where needed, e.g. GOVERN 6.1 when built on an
  existing model). `foundation` in `data/ai/mapping_rules.json`.
- **Foundation subcategories outside GOVERN (decided 2026-10-23, list still empty):** some MAP, MEASURE and MANAGE
  subcategories are about how the organisation runs AI risk management, not about one AI area, so every area would get
  the same answer. Likely: MANAGE 1.2 and 1.3 (risks prioritised, responses planned), MEASURE 3.2 and 4.1 (tracking
  hard-to-measure risks, measurement feedback); possibly MEASURE 1.1 to 1.3, 2.13, 4.2 and 4.3 (choosing and reviewing
  metrics). They are decided after all 14 areas are drafted, from the Coverage sheet: a subcategory no area reaches, or
  that every area reaches with the same why, and that is about method. They are added to
  `foundation.subcategories` one by one, keep their AI RMF id (they are not relabelled as GOVERN), are left out of the
  drafter's input and the review sheet, and the recording script rejects them as area rows. Until then an area reaches
  them like any other subcategory.
- **A question = one AI area x one mapped function**, landing on one AI RMF subcategory. The function is not in the AI
  area sheet: a script crosses every area with MAP, MEASURE and MANAGE and the drafter fills each pair (or marks it "no
  question" with a reason). The recording script rejects a GOVERN row. The AI RMF has no "protect" function: access
  control and encryption are risk treatments (MANAGE) and are checked in MEASURE 2.7. Audit trails sit in MEASURE 2.8
  and MANAGE 4.1.

Sample, AI area "Source data (RAG / knowledge graph)":
| Function | Subcategory | CIS safeguards (lowest IG) | Impact |
|---|---|---|---|
| MAP | MAP 4.1 data sources and rights | LLM-3.1 (IG1) | data |
| MEASURE | MEASURE 2.10 privacy | LLM-3.7 (IG2), LLM-3.14 (IG3) | data |
| MEASURE | MEASURE 2.7 security | LLM-3.3 (IG1), LLM-3.12 (IG2) | access |
| MANAGE | MANAGE 2.4 disengage | LLM-3.3 (IG1) | access |

### Required checks
Some checks must exist for every AI area they apply to, so they cannot depend on the drafter remembering them. They are
written in a small rules file and the recording script rejects a mapping that misses one (for example "agent: no
audit-trail row").
| Check | For | Must have a row on | Citing |
|---|---|---|---|
| Audit trail | every AI area | MEASURE 2.8 or MANAGE 4.1 | a CIS control 8 (audit log) safeguard |
| Incident response | every AI area | MANAGE 2.3 or MANAGE 4.3 | CIS control 17 where linked |
| Reliability (accuracy, consistency, drift; not attack) | Output, and Model for producers | MEASURE 2.5, and MEASURE 2.4 or MANAGE 4.1, and MEASURE 2.1 (test sets and harness documented) | Playbook practices; CIS where linked |

Reliability under attack (prompt injection, poisoned answers) is part of Output and Source data and is checked in
MEASURE 2.7 like other security. The harness as data to protect is the Test, tuning and evaluation data area.
Inventory is not a per-area check: it is GOVERN 1.6, foundation, asked once (the inventory question can name the
client's areas). CIS controls 1 and 2 stay candidates in every area for MAP rows on the area's components.

## 4. Severity: priority of findings (does not change which questions are asked)
- Each mapping row carries one or more of its area's impacts (data, access, process, assets).
- Data findings rank by data classification, assessed through the questions.
- Process findings rank by process criticality, from one standard question in every questionnaire (MAP 1.1, MAP 5.1):
  for each process AI is used in, the worst realistic outcome if the AI gets it wrong. Financial loss: under USD 100k /
  USD 100k to 500k / over USD 500k. Reputational damage: none / local / public or regulatory. Safety: no / possible harm
  to people. Not being able to answer is itself a maturity gap.
- Domain floor: for healthcare and manufacturing / OT loss of life is possible, so safety findings (MEASURE 2.6, People
  harm) rank highest by default.
- In AI RMF harm terms (NIST AI 100-1, section 1.1, Figure 1): financial and reputational loss is **Organization**,
  loss of life and harm to individuals is **People**, supply chain and environment is **Ecosystem**. Add NIST AI 100-1
  to the sources when the figure is cited.

### Per AI system, without repeating questions
Assessing per AI system (AI RMF GOVERN 1.6 inventory, MAP 1.1 context per system) does not mean asking every area
question once per system. The areas already describe what systems are made of, so:
- **Inventory in the foundation (GOVERN 1.6):** one question lists the client's AI systems, each with its AI areas and
  its criticality (the standard question above: financial, reputational, safety). This is the only per-system question.
- **Area questions are asked once per area x subcategory** and written proportionate to criticality: "for your
  highest-criticality AI systems, ...", with the example taken from the system that ranks highest in the inventory.
- **Maturity ladder (GOVERN 1.3, risk management proportionate to risk):** low = no difference between systems;
  middle = practices differ by criticality on paper; high = practices differ by criticality and are evidenced for the
  high-criticality systems.
- **Severity:** a gap on an area used by a high-criticality system ranks higher than the same gap elsewhere.

## 5. The mapping and maturity
Rows per AI area: AI RMF function -> subcategory, CIS safeguards that prove it, impact, why. There is no row count:
an area gets a row for every subcategory that really checks it (each at most once), and the evaluator fails padding.
- Score per AI RMF subcategory (the 72-row profile XLS), like CSET questions mapping to CSF subcategories. AI areas
  and impacts are report views on top; nothing counts twice.
- All 72 subcategories must be reached: the 19 GOVERN ones as foundation, the other 53 by area rows.
- CIS Implementation Groups give the levels (IG1 basic, IG2, IG3); `data/tier_definitions.json` maps to them.
  Subcategories with no CIS link (42 of 72) are scored from Playbook practices.
- List `LLM-` safeguards; a script adds the `MCP-` / `AGENT-` equivalents for MCP / tools and agents.

## 6. Pipeline
1. AI areas spreadsheet (person) -> `sheet_io.py import ai_areas` -> `ai_areas.json`.
2. A script crosses the areas with MAP, MEASURE and MANAGE and prepares a compact input per area (area, the Playbook
   definition of each function, the subcategories of each mapped function with suggested actions, the candidate CIS
   safeguards).
3. Drafter agent fills each pair: subcategory, safeguards (from the candidates), impact, why. One area at a time.
4. Evaluator agent (fresh context): returns failing rows only; one revision turn.
5. Recording script: validates the whole file (ids, safeguards exist, impacts belong to the area, every area has rows,
   all 72 subcategories reached), stores the mapping JSON, write-once record.
6. The mapping goes to a spreadsheet for review (`sheet_io.py export mapping` -> `data/ai/authoring/mapping.xlsx`):
   one line per AI area x MAP, MEASURE or MANAGE subcategory, mapped or not, with the Playbook outcome and safeguard
   titles, so missing subcategories are visible, plus a Coverage sheet (subcategory x area). The person edits; `import
   mapping` checks every area like agent output and stores changed lines as `decided_by: human`.
7. Accept gate (person), like `ai_pilot.py accept`.
8. Questions per mapping row (generator, evaluator) -> producer and consumer banks; GOVERN questions per subcategory,
   each tagged with the roles it applies to (none, consumer, producer).

`applicability.json` and `airmf_to_cis.json` are replaced by the mapping; the bank a row belongs to comes from the
area's "applies to". Rebuild only when the Playbook or CIS guides change, or after the person accepts mapping changes;
regeneration is per mapping row.

## Code review findings from the same review (not fixed yet)
1. `parse_soa.py`: numeric control ids collapse (5.10 -> 5.1, 8.10 -> 8.1) and `compute_scope.py` then overwrites one
   row with the other. Reproduced. Fail on duplicate ids after parsing.
2. `extract_cset_candidates.py` `net_active_pairs`: `inserts - deletes` ignores order; a mapping deleted then re-inserted
   is lost. Reproduced. Replay in file order.
3. `compute_scope.py validate_judgements`: an excluded control with no `exclusion_class` passes and stays pending forever.
4. `check_freshness.py`: bank completeness compares counts, not sets of ids.
5. CSF bank freshness ignores `cset_judgements.json` and `csf2_core.json`.
6. `extract_cset_candidates.freshness`: an unknown stored commit raises an uncaught error.
7. `record_judgements.validate_patch`: locks only `function` and `outcome`; for AI drafts also lock `bank`,
   `scope_reason`, `usage_note`.
8. `intake.py --date` is not validated before it becomes part of the run folder path.
9. `parse_soa.py` column detection matches substrings ("control" can match "Control title").
