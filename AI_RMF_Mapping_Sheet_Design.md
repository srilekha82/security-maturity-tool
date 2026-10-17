# AI RMF mapping sheet: design decisions (2026-10-16/17)

Agreed in a design review of the AI RMF track. Nothing here is built yet; the build is planned for the next session.
It replaces the applicability judge and the CIS linker as decision makers. Read with `AI_RMF_QuestionBank_Decisions.md`
and `AI_RMF_Pilot_Decisions.md`.

## Why
- `prompts/ai_rmf_applicability_judge.md` decides everything; `record_ai_bank.py` checks only the format (72 ids, known
  category ids, a reason). Nothing checks whether a mapping is right.
- The recorded applicability (2026-10-14) left the critical asset categories almost empty: consumer `data_exposure`
  2 of 72 subcategories, `infra_hosting` 1, producer `build_infra` 1. Governance and reliability got 16 to 20 each. The
  Playbook says little about security, so an agent mapping from Playbook text alone always under-maps the asset areas.
- `question_categories.json` reflects the usage model, but it is hard to read, the consumer assets (knowledge graph /
  RAG, IP) are hidden inside `data_exposure`, and the category-level fields (`capability`, `modifiers`, `scope_tags`)
  are read by no script and never shown to an agent.
- Usage connects to the Playbook and CIS only through agent decisions (applicability, question tags). Nothing links them
  deterministically.

## The usage model (confirmed)
1. **Who:** producer / consumer.
2. **Type of use:** internal; code generation; customer-facing; third party (vendors and products that run AI on the
   org's data: Jira, Slack, ServiceNow, GitHub ...); modified LLM (a model the org tuned for itself, may serve internal or
   external applications; not a direct call to an LLM hosted elsewhere).
3. **Depth of use:** LLM -> RAG -> MCP -> agents (the existing rung).
4. **Critical assets:**
   - Hosting: checked when the org hosts the LLM (producer; consumer only for a PoC or a modified LLM). Critical then.
   - Model as IP: always. Producer: the model (weights, training data, versions). Consumer: prompts, system
     instructions, agent configurations, plus RAG content and the knowledge graph. Modified LLM: both.
   - Knowledge graph / RAG: checked at depth RAG or higher. One area with both views: data (classification, exposure)
     and IP (theft, extraction).
5. **Rule:** the intake asks only about capability. Every control (including data classification) is assessed by the
   questions, never asked up front. Having RAG means classification should exist; whether it does is maturity.

The existing implementation already holds most of this (roles, rung, `third_party_supply`, `self_hosted`,
`model_assets_ip`, `data_exposure`). The model is right; the naming, grouping and enforcement are what change.

## Check areas (draft, to review)
| # | Area | Applies to | Checked when | Replaces |
|---|---|---|---|---|
| 1 | Ownership and rules | Both | Always | `gov_accountability` |
| 2 | Which AI we use, who approved it (shadow AI, PoCs) | Both | Always | `inventory_shadow_ai` |
| 3 | What it is for, who it affects | Both | Always | `use_context_impact`, `intended_use_impact` |
| 4 | Suppliers, vendors and outside models | Both | Always | `third_party_supply`, `upstream_models` |
| 5 | Testing it works safely and fairly | Both | Always | `reliability_validation`, `reliability_robustness`, `fairness_safety_eval` |
| 6 | When things go wrong | Both | Always | `incident_recovery` |
| 7 | Model and prompts as IP | Both | Always (contents by role) | `model_assets_ip`, IP part of `data_exposure` |
| 8 | Knowledge graph and RAG data | Both | Depth RAG or higher | RAG part of `data_exposure` |
| 9 | Hosting infrastructure | Both | The org hosts (producer, PoC, modified LLM) | `infra_hosting`, `build_infra` |
| 10 | What the AI can access and do | Both | Depth MCP or agents | `ai_access_identity`, `ai_access_tools` |
| 11 | Releasing AI to others | Producer | Always for producers | `release_distribution` |

Open: training data (producer) as its own area 12 or inside 7; fairness split out of 5 or not.

## Impact
Use the AI RMF harm categories (NIST AI 100-1, section 1.1, Figure 1): **People** (individuals, groups, society),
**Organization** (business operations, security breach and monetary loss, reputation), **Ecosystem** (supply chains,
financial system, environment). Data and operations sit under Organization. Impact is set per mapping row, not only
per area (MEASURE 2.10 under area 8 is People; MEASURE 2.7 under area 8 is Organization). MEASURE 2.12 is Ecosystem
(the applicability pass had forced it into `intended_use_impact`). Add NIST AI 100-1 to the sources if the figure is cited.

## The mapping (like CSET: every question lands on a subcategory)
Spreadsheet, review view of a JSON store:
- **Areas** sheet (human): one row per area: id, name, applies to, checked when, what we check, risk / attack
  surface, covered by general security (the gap rule, replaces topics), replaces.
- **Mapping** sheet (agent drafts, human reviews): one row per area x AI RMF subcategory: area id, subcategory,
  outcome, why the area covers it, CIS safeguards that prove it, impact. An area has many rows.

Example rows for area 8 (draft):
| Subcategory | Why | CIS safeguards (lowest IG) |
|---|---|---|
| GOVERN 1.6 | Each store is inventoried with owner and data held | LLM-3.2 (IG1) |
| MAP 4.1 | Rights and sources of the data fed into the store | LLM-3.1 (IG1) |
| MEASURE 2.10 | Data classified; sensitive data detected, access logged | LLM-3.7 (IG2), LLM-3.13 (IG3), LLM-3.14 (IG3) |
| MEASURE 2.7 | Retrieval respects rights; encrypted, separated; extraction | LLM-3.3 (IG1), LLM-3.11 (IG2), LLM-3.12 (IG2) |

Rules for the mapping:
- Score per subcategory (the 72-row profile XLS stays the score); areas are a view on top, so nothing counts twice.
- All 72 subcategories covered by at least one area; each asset area (7 to 10) has a minimum number of rows.
- CIS controls prove the asset and security areas; governance areas (42 subcategories have no CIS link) are proved by
  Playbook practices.
- CIS Implementation Groups give a deterministic maturity ladder (IG1 basic, IG2, IG3); `data/tier_definitions.json`
  (NIST tiers 1-4, unused today) maps to it.
- List `LLM-` safeguards; a script adds the `MCP-` / `AGENT-` equivalents when the client's depth is MCP or agents
  (the CIS guides are organised by depth).
- Areas and the categories file live in a committed folder such as `data/ai/authoring/`, not `data/ai/source/`
  (`.gitignore` excludes `data/ai/source/*.xlsx`; that folder is for third-party material).

## Pipeline (to build)
1. Areas sheet (human).
2. Drafter agent: Playbook JSON + CIS JSON + areas -> mapping rows with reasons.
3. Evaluator agent (fresh context): returns failing rows only; one revision turn.
4. Recording script: validates the whole file (ids, coverage of all 72, safeguards exist, minimum rows per asset area),
   stores the JSON, write-once record.
5. Export script: JSON -> spreadsheet for review.
6. Human review in the spreadsheet.
7. Import script: spreadsheet -> JSON; changed rows `decided_by: human`; change logged. Freshness flags a spreadsheet
   that changed but was not imported.
8. Accept gate (human), like `ai_pilot.py accept`: only an accepted mapping feeds bank generation.
9. Bank generation: generator + evaluator per mapping row (area + subcategory) instead of per subcategory.

Effects: `applicability.json` and `airmf_to_cis.json` are replaced by the mapping (bank applicability comes from the
area's "applies to"); the applicability judge and CIS linker become optional checkers; `question_categories.json`
is generated from the areas sheet; `prepare_ai_bank.py batch`, `build_ai_questions.py` and the generator input change.
The pilot is not accepted, so it is re-run after this.

## Code review findings from the same session (not fixed yet)
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
