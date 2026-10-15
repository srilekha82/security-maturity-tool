# AI RMF Question Bank — Decisions & Build Brief

Status: decisions settled Oct 2026; build not started. Read with `README.md`, `AI_RMF_Handoff_Notes.md` and `AI_Assessment_Pipeline_Design.md`.

## What we are building

A question bank generator for NIST AI RMF 1.0 assessments, analogous to how `caizin-csf-tool` uses CSET for CSF 2.0. The output is two frozen JSON files — one for producer orgs, one for consumer orgs — built from the AI RMF Playbook and the three CIS companion guides, and refreshed quarterly. The answers end up in the AI RMF profile XLS (Stage 2).

---

## Architecture decisions (confirmed)

### 0. Premise
The maturity lookout is the same for any org: govern, understand risk, protect, detect, respond, recover (AI RMF: GOVERN / MAP / MEASURE / MANAGE). What differs is how AI creates exposure, and so what gets prioritised.
- **Primary scoping input = how AI is used** (the three dimensions in section 2). This replaces the CSF domain question.
- **Sector is a secondary decorator only**: report context and regulatory notes. It does not select questions.

### 1. Two banks, not one
- `question_bank_ai_rmf_producer.json`
- `question_bank_ai_rmf_consumer.json`

**Producer** = org that builds AI models where the model is the product or a core asset (often small, purpose-built LLMs; IP protection and independence matter) or where the model is distributed to others (API, open weights, embedded in products). Separate question set. Full AI RMF depth, especially GOVERN 4.x, MAP 1.x, MEASURE 1.x, MEASURE 2.x (bias, fairness, safety, test & eval), plus weights, IP and training-data protection.

**Consumer** = org that uses AI. NOT a lower tier of producer — a genuinely different question set.

An org can be both and then gets both banks (e.g. a producer that also uses LLMs internally).

**Fine-tuning boundary:** fine-tuning an existing model for own use (an org-level PoC, an internal domain model) = consumer, with a `self_hosted`/fine-tuned tag that pulls in data/model protection and infra questions. A company whose product is a tuned domain model (the John Snow Labs pattern) = producer, because others receive the model.

### 2. Scoping dimensions (engagement time)
1. **Role** — producer / consumer / both. Picks the bank.
2. **Technology / reach ladder** — each rung includes the ones below; the org answers for the highest rung it reaches:
   - `base` — LLM use, no access beyond the prompt
   - `rag` — LLM reads org data through retrieval (RAG, knowledge graph)
   - `mcp` — LLM has tools; can read/write and take actions
   - `agentic` — operates with minimal human oversight; autonomous multi-step

   Classic ML and vision models are out of scope (the CIS guides cover LLM, MCP and agents only; the LLM guide also excludes non-text modalities).
3. **Usage context** (multi-select, not mutually exclusive):
   - `internal` — day-to-day business processes; output stays inside the org
   - `code_generation` — AI builds or maintains business applications. Separate because the output is a persistent executable artifact (software-integrity risk: insecure code, hallucinated dependencies, licensing, secrets, review gates) and coding assistants usually have repo/terminal reach. Revisit only if it ends up with fewer than ~5 candidates once `ai_rmf_core.json` exists.
   - `customer_facing` — AI inside an app, or output reaching customers/end users; includes calling a SaaS LLM API from the org's own app
   - `third_party_embedded` — AI bundled in a tool the org uses (ServiceNow, Jira, RPA with a built-in LLM); less control, supply chain focus

   For producers this dimension means who receives the model: internal only, or distributed.

Dimensions drive which candidates are selected and how they are prioritised. They do NOT split the bank further — they are tags on candidates. MCP and agents are the same for producers and consumers.

### 2a. Modifiers
- **`builds_on_base_model`** (producer bank tag, vs trained from scratch): the producer inherits upstream risk — upstream model due diligence, licence, inherited bias/safety gaps, base-model change or withdrawal (third-party / supply-chain subcategories, e.g. GOVERN 6.x).
- **`stage: poc | production`**: PoCs use real data with a larger exposure surface and fewer checks. Not a role and not a separate question set; it raises priority and depth of the data_model and ai_access topics and the inventory questions (what is running, who approved, what data, end date). Intake asks "any PoCs or experiments running?"; the answer also feeds `unsanctioned_use`.
- **`third_party_embedded` specifics:** inventory of vendor AI features, ability to opt out/control, data flow to the vendor's model provider, vendor training on org data. The reach rung is set per embedded tool, not once per org.
- **`unsanctioned_use`** (shadow AI): asked for every org, including `none`. It is the in-enterprise stand-in for the general public using public chatbots.
- **`self_hosted`**: wording of infra and supply-chain questions differs from SaaS because responsibility shifts.

### 3. Topic areas (always asked; depth set by the dimensions)
- **Data and model protection** — RAG/knowledge-graph content, weights, fine-tuned models and prompts are assets.
- **Infrastructure** — protecting where sensitive things are hosted; wording differs for SaaS vs self-hosted.
- **Reliability** — tuning, harness, guardrails; wrong or hostile inputs/outputs, from normal model behaviour or from attack.
- **Access by AI** — agents, MCP and RAG as a new identity with permissions. This is an access path, not a technology or an asset. Four attributes shape the depth of its questions (they do not choose the bank or the tags): what data it can reach (public / internal / sensitive-regulated), what it can do (read / write / execute actions), whose permissions it uses (its own scoped identity vs the user's full rights), and whether a human approves actions. Example: an agent that writes with the user's full rights gets the deepest questions.

### 4. AI-in-use intake gate
Intake asks "AI in use: none / some / unsure". The AI RMF XLS is always produced in the 72-subcategory schema.
- `some` — scope by the three dimensions.
- `unsure` — treated as `some`: consumer bank, `base` rung, no usage tags assumed; Map/inventory questions and the shadow-AI check are `full_discovery`; the answers reveal the real profile for a second scoping pass.
- `none` — mostly `skip` / not applicable; the `unsanctioned_use` check stays live; the report notes "no AI use declared".

**Sequence of an engagement (settled):** (1) the CSF assessment runs first; (2) the AI RMF assessment is scoped from the AI usage profile (the gate above, the three dimensions and the modifiers); (3) the CSF output is then updated with the AI-world notes according to that same usage pattern. The AI usage intake therefore drives both the AI RMF scope and which CSF notes are shown. **The AI-world notes have two layers (settled):** (a) an **exposure** note per mapped CSF subcategory, shown to every org (external agents/MCP clients and AI-enabled attackers can reach any org, including orgs that use AI); (b) a **use** note, added only when AI is in use (`some`, or `unsure` once answers confirm use) and only for the subcategories where use changes the reading (~25 to 30 expected). Use notes are short and point to the AI RMF Access by AI and related topics instead of repeating them; depth follows the highest technology rung reached (`base`/`rag` = data leakage and retrieval permissions; `mcp`/`agentic` = AI tools as identities with scoped credentials and human approval). Example, PR.AA-05: exposure = agents can call APIs or sign in on behalf of users at machine speed, so permissions sized for humans may be too broad; use (agents/MCP) = give each AI tool its own scoped credentials, never inherit a user's full rights, require approval for write or irreversible actions.

**Orgs with no AI but exposed** to external agents/MCP clients or AI-enabled attackers are handled on the CSF side as short "AI-world impact" notes (`data/csf/ai_impact_notes.json`, keyed per CSF subcategory), not in the AI RMF bank. An org that runs an MCP server or an agent-callable API is NOT in this case; it is in AI RMF scope.

### 5. Question types
Same names as the CSF tool: `full_discovery` / `gap` / `confirmatory` / `skip`. Assigned at engagement time, not baked into the bank. The bank stores candidates only; a `build_questions.py` equivalent assigns the type per engagement from `data/ai/scope_rules.json`.

**The type is set at topic level, not per safeguard.** The CSF tool already assesses general security and handles the ISO 27001 SoA, so the AI RMF questionnaire only asks the AI angle of those areas.
- Engagement flags: "CSF assessment done", "ISO 27001 held", "ISO 42001 held".
- CSF or ISO 27001 flag set: data_model / infra / ai_access topics become `gap` ("general controls cover this; what differs for AI?").
- No flag, or no match: `full_discovery` (safe default).
- ISO 42001 held: governance subcategories could become `gap` / `confirmatory` — **Phase 2**, see the build section.
- The CIS → CSF and CIS → ISO 27001 tables are NOT needed for question type.

### 6. Bank candidate schema
Each candidate question in a bank carries:
```json
{
  "subcategory_id": "GOVERN 6.2",
  "question_text": "...",
  "playbook_ref": "GOVERN 6.2 — suggested action 3",
  "cis_refs": ["LLM-15.5", "MCP-15.5"],
  "scope_tags": ["customer_facing", "third_party_embedded"],
  "capability": "base",
  "topic": "infra"
}
```
- `scope_tags`: usage-context values; empty array = applies to all usage contexts. Producer-bank candidates don't need scope_tags.
- `capability`: `base` | `rag` | `mcp` | `agentic` (the lowest rung at which the question applies).
- `topic`: `data_model` | `infra` | `reliability` | `ai_access`.
- Modifier tags (`builds_on_base_model`, `self_hosted`, `poc`, `unsanctioned_use`) are added where a candidate depends on them.

### 7. Question content principle
- Questions are at the **subcategory outcome level** — they ask what the org *does*, not whether it has a document.
- **Playbook suggested actions** = primary source for question content (what good looks like).
- **CIS companion guides** = evidence prompts, context and tagging (rung, usage context, topic), NOT question text. (They also still feed the roadmap tab of the HTML as the prescription layer; see the pipeline design.)
- The evaluator must reject checkbox-style questions ("do you have a policy for X?") and require practice-revealing questions ("describe how your org does X, who owns it, what evidence exists").
- Producer content on bias, fairness and explainability can only come from the Playbook (MEASURE 2.x): the CIS guides exclude those topics.

### 8. Freshness gate
SHA of the four source PDFs, checked quarterly:
- `CIS_Controls_v8.1_AI_and_LLM_Companion_Guide_April_2026.pdf`
- `CIS_Controls_v8.1_Model_Context_Protocol_Companion_Guide_April_2026.pdf`
- `CIS_Controls_v8.1_AI_Agents_Companion_Guide_April_2026.pdf`
- AI RMF Playbook PDF

If no PDF has changed, the bank is valid and regeneration is skipped. Same pattern as the CSET git-commit check in `check_freshness.py`.

### 9. Mappings, sources and what they are (settled Oct 2026)

**Sources used to build the banks:** only the AI RMF Playbook and the three CIS companion guides. Supporting only: the profile XLS (72-subcategory structure; its "Applicability Layer" column seeds the applicability pass). NOT used for the bank: the base CIS Controls guide (the companion guides already carry the base safeguard text beside the AI-specific text, so it adds nothing), the CIS → ISO 27001 table (not needed), the CIS → CSF table (used only for the impact notes, Step 5, not for the banks), the 42001 crosswalk (Phase 2) and OWASP LLM Top 10 (a community risk list of 10 items, not a control framework that maps to the 72 subcategories; the existing OWASP-based overlay is being replaced by this track).

**What the source files contain (checked Oct 2026):**
- Playbook: 72 subcategories, each with a "Suggested Actions" block; parseable.
- Companion guides: organised by CIS Control and Safeguard, with an AI applicability column plus hosting notes (enterprise-hosted vs SaaS-hosted); ~75 to 87 safeguard rows each. They map only to base CIS safeguards — no AI RMF or CSF references.
- The guides exclude fairness/bias/explainability/ethics; exclude HITL in the LLM guide (covered in the agents guide, which supports keeping `agentic` as its own rung); cover RAG only as retrieved text at the context window (vector-store infrastructure is out of scope); exclude non-text modalities and non-LLM ML.

**Translation tables: status and provenance**

| Link | Source | Status |
|---|---|---|
| CIS v8.1 → ISO 27001:2022 | CIS official, June 2024 | Have it, works (124 of 153 safeguards mapped), but NOT needed for this build and not in the repo. (The CSF tool's ISO 27001 handling is a different file: the NIST ISO 27001 → CSF crosswalk `data/csf/crosswalks/olir_iso27001.json`, used for the SoA scope.) Optional later. |
| CIS v8.1 → NIST CSF 2.0 | CIS official, 6/24/2024 | Have it, works, in `data/ai/source/`. Sparse: ~46 of 153 safeguards map; 48 of 106 CSF subcategories reached. The CSF tool has no CIS mapping and nothing AI-related for orgs without AI (checked Oct 2026). Used by build Step 5 (AI impact notes). |
| AI RMF ↔ ISO/IEC 42001 | Microsoft; hosted on NIST AIRC | Community submission, not NIST-endorsed; maps the FDIS draft, not the published 2023 edition; cites clauses + Annex B IDs; some apparent errors (e.g. Map 1.4 "B.2.2 Customers", Govern 3.2 "B.3.2", "7..2"). Verify before use (Phase 2). |
| AI RMF → CIS safeguards | Caizin | Does not exist. Build once: an agent maps the 72 subcategories to safeguards, a script validates the IDs, logged. Many GOVERN/MEASURE subcategories will map to none. |

The 42001 standard itself (ISO/IEC 42001:2023) is official; only this crosswalk is unendorsed.

**Parsing gotcha:** the CIS xlsx files store safeguard IDs as numbers, so 4.10, 8.10 and 16.10 collapse into 4.1, 8.1 and 16.1 (150 seen vs 153). Read IDs as text or rebuild them from the control number and row order. The v8 → ISO file (Jan 2023) is superseded by the v8.1 file; do not use it.

**Where the CIS → CSF table IS used:** the "no AI but exposed" notes, which are part of this build (Step 5), not a later extra. Chain: CIS MCP/agents guide safeguard (AI-specific text) → CIS safeguard ID → CSF subcategory (via the table, by script) → short note in `data/csf/ai_impact_notes.json`. Notes are written once by an agent and reviewed. Only the ~48 mapped CSF subcategories get notes; unmapped ones (mostly governance) get none unless added by hand. The existing CSF tool has nothing like this today (it has only the OWASP-based overlay for orgs that DO use AI).

### 10. Decision log (confirmed)
- `code_generation` is a separate usage context (section 2).
- Per-subcategory applicability to each bank is decided before any generation loop (build Step 1b).
- Separate small recording script (`record_ai_bank.py`) calling `audit.py`, same contract as `record_judgements.py` (the agent hands in a file; the whole file is rejected if invalid; nothing is stored until it passes); share generic helpers; reuse `record_judgements.py log --base --patch` for patch steps.
- AI impact notes are keyed per CSF subcategory.
- Bank build uses plain subagents in this repo; Stage 2 uses gen-eval-loop (build approach below).

---

## Design rules carried over from the CSF rebuild (apply to the AI RMF build)

Settled while simplifying the CSF side (Oct 2026). Follow them here; read `README.md` for the working example.

1. **Scripts never decide.** They parse, join, look up, validate, format, hash and write. Anything that needs judgement goes to an agent. A script that cannot settle an item writes a `pending_*.json` and exits 2; it never guesses.
2. **Agents see only the pending items,** never bulk data (source PDFs, full banks, crosswalks). Parse the PDFs into compact JSON (`ai_rmf_core.json`) with a script first; the agent reads that, not the PDFs.
3. **Agents return patches, not full lists.** Output tokens are the expensive ones. The agent returns only the entries it changed; a script validates and merges them (see `record_judgements.py log --base --patch`).
4. **Policy and content live in data files, not code.** Max questions per type, evidence hints, scope rules, tag and rung mappings go in `data/ai/*.json`. Scripts stay stable; changing a rule means editing JSON. Keep each constant in one place only.
5. **Everything is audited, built once and inherited.** Every new script calls `scripts/audit.py` (`begin` at the start, `finish`/`fail`/`pending` at the end), which appends to the folder's `audit.jsonl`; every agent step goes through a recording script. Do not write a separate logging scheme. Judgements are also kept write-once with model, prompt hash, inputs and output snapshot. Suggested AI RMF locations: `data/ai/bank_build/audit.jsonl` and `data/ai/bank_build/judgement_log/`.
6. **Evaluators run in a fresh context** (subagent) with only what they need, and return only failing IDs with a one-line reason.
7. **Few scripts, small files.** Reuse the CSF scripts where the logic is the same rather than adding new ones. Add a script only for a genuinely new deterministic job (e.g. `parse_ai_rmf_sources.py`, `record_ai_bank.py`). Add commands only where a step is repeated.
8. **Handoff by files.** Each stage reads and writes a schema-validated file and passes paths, not content. Print one summary line on success; put detail in a file read only on failure.
9. **Stays a repo** (not a plugin or MCP server): plain bash and CLI. Revisit only if non-developers need to run it.

### What to reuse from the CSF side
- Freshness gate: `check_freshness.py` and `data/metadata.json` (add the four source PDFs; the command updates `last_refreshed` after a rebuild).
- Pending / judge / record loop: `build_question_bank.py`, `prompts/question_bank_judge.md`, `record_judgements.py` (same exit-2 pattern). The AI RMF bank needs its own recording script because its unit differs (subcategory + role + rung + usage tags + topic, not CSET question IDs).
- Question types and scope: `data/csf/scope_rules.json` and `compute_scope.py` are the pattern. The AI RMF scope drivers are the three dimensions, the modifiers, the AI-in-use gate and the engagement flags (section 5), not certifications alone; add `data/ai/scope_rules.json`.
- Bank layout: one file per bank under `data/<framework>/banks/`, shared across runs; a copy is snapshotted into each run folder as `question_bank_used.json`.

### Open items
- Where `tier_definitions.json` (currently unused) is used: maturity scoring of answers into the profile XLS is a judgement step, best done in the same pass as answering.
- Whether the Stage 3 HTML skills could fill a fixed template from the XLS in a script instead of the agent writing the HTML (check how much the skills generate by agent).
- (Resolved) The OWASP-based AI overlay and the old AI scope intake are replaced in the new session; see "Rewrite of the AI-related parts of the existing questionnaire flow".
- Optional: consider NIST AI 600-1 (the Generative AI Profile) as an additional source.

---

## Build approach: generate–evaluate with subagents

### Why generate–evaluate
No CSET equivalent exists for AI RMF. Questions must be generated from the source documents. A generate–evaluate loop ensures each subcategory's candidates are grounded in the Playbook and CIS controls and meet a quality bar before being frozen into the bank.

### Orchestration choice
- **Bank build** (many independent runs, per-run input, results must flow through our recording script and audit trail): plain subagents in this repo. Reasons: `gen-eval-loop` has no per-run input placeholder, writes a summarizer (an extra Opus session) per run, and returns a single status rather than failing IDs. Generator and evaluator prompts live in this repo under `prompts/`.
- **Stage 2 answer session** (one loop over all questions, revising only the weak IDs): `gen-eval-loop` (`/Users/srilekhamisra/workstuff/gen-eval-loop`) fits well.

### Granularity: pilot per subcategory, full run per category
- Token estimate (rough, unmeasured): ~144 per-subcategory loops ≈ 2–4M tokens; ~38 category batches (the AI RMF has ~19 categories of 3–7 subcategories, × 2 banks) ≈ 1–1.5M; ~8 function batches < 1M, but the evaluator must then judge 20+ subcategories at once (weaker checking). The applicability pass shrinks all of these.
- Initial confidence in the prompts is low and failures are correlated, so: pilot at per-subcategory size (cheap, tune both prompts), review passes as well as failures, then move to category batches once the pass rate is stable and the evaluator catches planted weak questions. Re-decide batch size from real token counts after the pilot.
- The evaluator fails when unsure, returns only failing IDs with a one-line reason; the generator revises only those; max 2 turns; anything still failing goes to human review.
- Spot-check a sample of passes in the full run.
- Cost levers in any option: applicability pass first; agents read compact JSON, not PDFs; a cheaper model for the evaluator; capped turns.
- Everything that passes is recorded through the recording script and appended to the bank.

### Pilot
Run 5–6 subcategories spanning the range before the full run:
- One from GOVERN (producer)
- One from MAP (consumer, internal)
- One from MEASURE (consumer, customer_facing)
- One from MANAGE (consumer, third_party_embedded)
- One with capability: mcp
- One with capability: agentic

Tune the generator and evaluator prompts on the pilot, then run all.

---

## Source documents
In the repo, like `data/csf/source/`, under `data/ai/source/` (copied from the NIST folder Oct 2026, registered with SHA-256 in `data/metadata.json`):
- `CIS_Controls_v8.1_Mapping_to_NIST_CSF_v2.0_2024-06-24.xlsx` — official CIS v8.1 → CSF 2.0 mapping, used by Step 5 only
- `AI_RMF_Playbook.pdf` — AI RMF Playbook (primary content source)
- `CIS_Controls_v8.1_AI_and_LLM_Companion_Guide_April_2026.pdf`
- `CIS_Controls_v8.1_Model_Context_Protocol_Companion_Guide_April_2026.pdf`
- `CIS_Controls_v8.1_AI_Agents_Companion_Guide_April_2026.pdf`

The CIS guides are CC BY-NC-ND 4.0: internal non-commercial use only. If this repo is ever shared outside Caizin, keep the PDFs out of it (or fetch them with a download step).

Other files, outside the repo in `/Users/srilekhamisra/workstuff/NIST/`:
- `ciscontrols_ai/caizin_ai_rmf_profile_v2.xlsx` — AI RMF profile: 72 subcategories, 11 columns; also the Stage 2 output schema (a copy is in `tests/fixtures/`)
- `CSF 2.0 Organizational Profile Template-final.xlsx` — the CSF profile (19 columns), the Stage 2 output schema for CSF

`check_freshness.py` today compares dates against `refresh_threshold_days`; the AI RMF gate compares SHA-256 values (stored in `metadata.json`). Extending the script is build Step 4.

## Existing tool to mirror
`/Users/srilekhamisra/workstuff/caizin-csf-tool`. Key files to understand before building:
- `scripts/build_questions.py` — how bank + scope → `questions_draft.json`
- `scripts/check_freshness.py` — freshness gate pattern
- `data/csf/banks/question_bank_finance.json` — bank schema to mirror
- `scripts/build_question_bank.py` and `scripts/record_judgements.py` — pending / judge / record loop
- `.claude/commands/build-question-bank.md` — full build command spec
- `README.md` — current structure of the whole repo

---

## What to build

### Step 1: `parse_ai_rmf_sources.py`
Parses the sources into compact JSON (script only, no judgement):
- From the Playbook: subcategory ID, outcome text, function, and the Suggested Actions block for each of the 72 subcategories.
- From the three companion guides: one row per safeguard (ID with guide prefix e.g. `LLM-15.4`, title, base text, AI applicability text), plus the hosting notes.
- It does NOT extract an AI RMF → CIS link; the guides carry none.

Output: `ai_rmf_core.json` (subcategories) and `cis_ai_safeguards.json` (safeguards) — the input feed for the later steps.

### Step 1b: Applicability pass (agent, once)
For each of the 72 subcategories, decide whether it applies to the producer bank, the consumer bank, or both. Seeded with the profile XLS "Applicability Layer" column (Caizin's judgement for one consumer org; a starting point only — in that copy 52 are User, 19 not included, 1 Shared, 0 Developer). The agent returns a patch; a script validates and logs it. Only applicable subcategory/bank pairs go to the generation step.

### Step 1c: AI RMF → CIS safeguard link (agent, once)
The agent maps each subcategory to relevant companion-guide safeguards (many GOVERN/MEASURE subcategories will map to none). A script validates that every ID exists; the result is stored as `data/ai/crosswalks/airmf_to_cis.json` and logged. Used for evidence prompts and for tagging rung / usage context / topic, not as question text.

### Step 2: Generator and evaluator prompts
`prompts/ai_rmf_question_generator.md` and `prompts/ai_rmf_question_evaluator.md` (in this repo).

Generator context per run: subcategory ID, outcome, bank (producer/consumer), Playbook actions, mapped CIS safeguards. Task: produce 3–5 candidate questions with tags (capability rung, usage-context `scope_tags`, topic, `cis_refs`, modifier tags) as structured JSON.

Evaluator checks (FAIL if any):
- The question is checkbox-style ("do you have X") → it must be practice-revealing.
- The question is not traceable to a cited Playbook action or CIS control.
- `scope_tags`, `capability` or `topic` are inconsistent with the source material.
- The question is too vague to be answerable from org documentation.

### Step 3: Orchestration script and recording script
The orchestration script reads `ai_rmf_core.json` and the applicability result, spawns generator/evaluator subagents (per subcategory for the pilot, per category afterwards), and hands each batch's output to `record_ai_bank.py`, which validates and appends to the two bank files and flags still-failing items for human review.

### Step 4: Freshness gate
Extend `check_freshness.py` (or add a small script) to SHA-check the four source PDFs and skip regeneration if unchanged.

### Commands and prompts plan
Commands say what to run; prompts say how to judge (see `README.md`). New command files point to this decisions file for the rules and do not duplicate them.

- **`/build-question-bank`, `/generate-questionnaire`, `/assess-questionnaire`: unchanged.** They are CSF-only (domain, CSET, SoA).
- **`/generate-questions` and `/generate-questionnaire`: the AI-related parts are rewritten in the new session** (old AI scope intake replaced by the AI-in-use gate and usage profile; Phase 3 Step A, the OWASP overlay, removed). The CSF steps themselves (domain, certs, SoA, scope, bank, assessor) are unchanged. The AI RMF questionnaire is a separate deliverable with its own XLSX, not an overlay on the CSF questionnaire.
- **New `/build-ai-rmf-bank`** (mirrors `/build-question-bank`): freshness check → `parse_ai_rmf_sources.py` → applicability pass (agent) → AI RMF → CIS link (agent) → generate/evaluate with subagents → `record_ai_bank.py` → write both banks → AI impact notes (Step 5). Repeated quarterly, so a command is justified.
- **New `/generate-ai-questions`**: AI RMF intake (AI in use, role, rung, usage contexts, modifiers, engagement flags) → scope from `data/ai/scope_rules.json` → pick from the banks → assessor review → write XLSX. Stops where an answer is needed, like `/generate-questions` does at the SoA question.
- **New prompts** under `prompts/`: `ai_rmf_applicability_judge.md`, `ai_rmf_cis_linker.md`, `ai_rmf_question_generator.md`, `ai_rmf_question_evaluator.md`, `ai_rmf_questionnaire_assessor.md` (the existing `questionnaire_assessor.md` is CSF-specific).
- **AI impact notes (build Step 5):** part of `/build-ai-rmf-bank`. Where the notes appear (settled): in the **Considerations** column (column 19) of the CSF profile XLS ("Current and Target Profile" sheet), written by the Stage 2 XLS writer from `ai_impact_notes.json` according to the intake. No schema change: NIST defines Considerations as supporting details for the outcome in the context of the Profile, it is empty in the Caizin copy, and the `caizin-nist-assessment` skill already reads it and shows it in each subcategory popup. The Notes column (18) is left for assessor comments. Format: labelled lines "AI-world (exposure): …" and, only where AI is in use, "AI-world (use): …"; if Considerations already has assessor text, append. Showing the notes in the Stage 1 questionnaire for control owners is optional and not required.
- New prompt `ai_impact_notes_writer.md` for the Step 5 agents (one prompt, two layers: exposure and use).

### Step 5: AI impact notes for orgs with no AI but exposed (part of this build)
1. Script: load the CIS → CSF 2.0 table (`data/ai/source/CIS_Controls_v8.1_Mapping_to_NIST_CSF_v2.0_2024-06-24.xlsx`; read safeguard IDs as text) and join it to the MCP and agents companion-guide safeguards by safeguard ID, giving per CSF subcategory the AI-specific safeguard text. Subcategories with no mapped safeguard are listed, not guessed.
2. Agent, layer 1 (exposure): for each mapped CSF subcategory (~48) write a short "how this changes in an AI world" note, framed for any org that can be reached by external agents/MCP clients or AI-enabled attackers (identity and access, API/network protection, monitoring, incident response, supplier access). Returns a patch; a script validates that every subcategory ID exists and logs it.
3. Agent, layer 2 (use): for the subset of those subcategories where AI use changes the reading (~25 to 30), write a short use note, with wording by highest rung (`base`/`rag` vs `mcp`/`agentic`), pointing to the AI RMF topic that covers it. Same patch, validate and log contract.
4. Output: `data/csf/ai_impact_notes.json`, keyed per CSF subcategory, each entry with an `exposure` note and an optional `use` object (`base_rag`, `mcp_agentic`). A script selects which notes to show from the intake (AI in use, highest rung); the exposure note is always shown. Re-run when the companion guides or the mapping change (covered by the freshness gate).

### Rewrite of the AI-related parts of the existing questionnaire flow (IN SCOPE for the new session)
Everything AI-related in the existing questionnaire flow was built for the old model (an AI scope intake and an OWASP overlay) and is not correct under these decisions. It is rewritten in the new session together with the bank build, not deferred:
- **Old AI scope intake:** `/generate-questionnaire` asks for an AI scope (`saas_tools` / `internal_workflows` / `customer_facing` / `regulated`) and passes it to `check_freshness.py --ai` and `compute_scope.py --ai-scope` (audit trail only). Replace with the AI-in-use gate and the usage profile (role, technology rung, usage contexts, modifiers, engagement flags).
- **OWASP overlay:** remove `/generate-questions` Phase 3 Step A; the `ai_overlay` field in `build_questions.py`, `write_questionnaire.py` and `prompts/questionnaire_assessor.md`; the OWASP crosswalk in `parse_crosswalk.py` and `paths.py` (`olir_owasp_llm.json`) and its entry in `data/metadata.json`. AI questions now come only from the AI RMF track (`/generate-ai-questions`).
- **Shared intake:** capture the AI usage profile once per engagement and save it in the run folder (e.g. `ai_usage.json`) so the CSF steps, the AI RMF steps and the XLS writer all read the same file.

Still later, not in this session: the Stage 2 XLS writer, which writes the AI-world notes into the CSF profile's Considerations column. Step 5 only produces `ai_impact_notes.json`.

### Stage 2 note (not part of the bank build)
The XLS writer also fills the CSF "Considerations" column with the AI-world notes (see Step 5). Answers are written into the profile XLS: AI RMF = 11 columns (ID, outcome, included, rationale, priority, applicability layer, current maturity/state, target maturity/state, evidence); CSF = 19 columns on the "Current and Target Profile" sheet. The schemas are fixed by the downstream skills; do not change them without updating the skills.

### Phase 2 (optional, after the banks exist): ISO 42001 coverage
Use the 42001 ↔ AI RMF crosswalk to set `gap` / `confirmatory` on governance subcategories for clients that hold a 42001 certificate (with their SoA if provided). Deferred because the crosswalk is a community submission, not endorsed by NIST, and maps a draft edition. To do before use: verify Annex A vs Annex B numbering against the published standard; review the apparent errors; confirm the edition. If a client holds 42001 and nothing is verified, treat everything as `full_discovery`.
