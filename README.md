# caizin-csf-tool

Stage 1 of the Caizin AI Assessment Pipeline. Given an organisation's profile (domain, certifications, optional ISO 27001 SoA) it produces one questionnaire (`questionnaire.xlsx`) to send to control owners, with two sheets: a tailored NIST CSF 2.0 sheet and a NIST AI RMF 1.0 sheet scoped by how the org uses AI. The client sees one questionnaire; the two tracks are internal. In Stage 2 the answers from the two sheets become two profile XLS files (CSF profile, AI RMF profile). Rules for changing the repo are in `DESIGN_RULES.md`; `CLAUDE.md` is the short operating guide. Pipeline design: `AI_Assessment_Pipeline_Design.md`.

```
Question banks  →  Stage 1: Questionnaire  →  Stage 2: Answers        →  Stage 3: HTML report
(CSF and AI RMF    (this repo)                (gen-eval-loop, TBD)       (Claude skills)
 built)
```

## I want to…

| I want to… | Do this |
|---|---|
| Generate a questionnaire for a client | `/generate-questions`. It asks the intake once (numbered choices), checks freshness, rebuilds missing banks, then runs the CSF and AI commands and the review, and writes one `questionnaire.xlsx` (CSF sheet + AI RMF sheet). |
| Generate only the CSF part, or only the AI part | On an existing run folder: `/csf-questionnaire` or `/ai-questionnaire`, then `/assess-questionnaire` (it writes the sheet; either sheet can be written in any order). |
| Have an independent review of a draft | `/assess-questionnaire <run folder>`: one fresh reviewer per draft (CSF and each AI bank), then the sheets are written. |
| See what is stale or missing | `.venv/bin/python ./scripts/check_freshness.py --all --run runs/<Org>_<date>` (CSF and AI together; `--domain <d> --certs <c>` instead of `--run` before a run exists). |
| Build or refresh the CSF bank for a domain | `/build-csf-bank`. `/generate-questions` does it for you when the bank is missing. |
| Build or refresh the AI RMF mapping, the question banks (foundation, areas) and the CSF AI impact notes | `/build-ai-bank`: pilot first; after you accept the pilot (`ai_pilot.py accept`) later rebuilds run on their own. |
| Use a new Playbook, CIS guide or CSF download | Replace the file (`data/ai/source/` or `data/csf/source/csf2.xlsx`, links in `data/metadata.json`). The freshness check sees the change; rebuild with the commands above. |
| Change how many questions per type, or when a question is `gap` | `data/csf/scope_rules.json` (CSF). AI: `data/ai/scope_rules.json` says which roles each client is asked as; every AI question is `full_discovery` (they ask what is done for AI, so they never repeat general security; no gap rule). No code change. |
| Change an intake menu, a domain, a certification or the question-type order | `data/common/intake_options.json`. Every script reads it through `scripts/options.py`. |
| Change the AI question roles, producer flags or impacts | `data/ai/question_rules.json` (what the generator and evaluator are told, and what `record_ai_bank.py questions` checks). |
| Review the AI RMF mapping (right, wrong, missing) | `.venv/bin/python ./scripts/sheet_io.py export mapping`, open `data/ai/authoring/mapping.xlsx` (one line per AI area x subcategory, mapped or not, with the Playbook text; a Coverage sheet), edit, then `sheet_io.py import mapping`. Then accept it: `.venv/bin/python ./scripts/ai_pilot.py accept-mapping`. |
| Review the AI RMF questions | `.venv/bin/python ./scripts/sheet_io.py export area_questions` (and `foundation_questions`), open `data/ai/authoring/questions_areas.xlsx` / `questions_foundation.xlsx` (one line per question: areas covered, who it is asked of, flag, question, Playbook actions, status), edit, then `sheet_io.py import area_questions`. Changed subcategories are stored as decided by a person and a later generator run does not overwrite them. |
| Review the CSF AI impact notes | `.venv/bin/python ./scripts/sheet_io.py export impact_notes`, open `data/ai/authoring/impact_notes.xlsx` (one line per CSF subcategory: exposure note, the two use notes, status from the notes evaluator), edit, then `sheet_io.py import impact_notes`. Changed lines are stored as decided by a person. |
| Change the AI areas (usage and ecosystem components, their impact) | Edit `data/ai/authoring/ai_areas.xlsx` (the decision), then `.venv/bin/python ./scripts/sheet_io.py import ai_areas` (checks every row, writes `data/ai/ai_areas.json`). The model is in `AI_RMF_Mapping_Sheet_Design.md`. A change to an area makes its mapping rows, and then their questions, out of date. |
| Change how an agent judges | The file in `prompts/` (see the table below). Editing the AI generator or evaluator prompt makes the accepted pilot stale. |
| See what happened in a run | `runs/<Org>_<date>/audit.jsonl` (timeline) and `judgement_log/` (what each agent was shown and answered). |
| Change the code or add a stage | Read `DESIGN_RULES.md` first, then run the tests (`.venv/bin/python -m unittest discover -s tests`). |
| Get the maturity XLS or the HTML report | The XLS writer is not built yet. HTML comes from the skills `caizin-nist-assessment` and `caizin-ai-rmf-assessment`, one profile XLS each. |

## How it works

- **Scripts do the repetitive, deterministic work and never decide.** Parsing, joining, looking up, validating, formatting. This is what keeps agent token use low.
- **Agents do every judgement**, and see only the small set of items a script could not settle (a `pending` file, exit code 2).
- **Everything that happens in a run is audited.** Each script run and agent step appends one line to an `audit.jsonl` (who, what, inputs and outputs with hashes, how it ended). Agent judgements also get a full write-once record in `judgement_log/` (model, prompt hash, output snapshot). Any new script or stage should use the same helper, `scripts/audit.py`.
- **Policy and content live in data files, not code.** To change a rule or a wording, edit a JSON file.

## Setup

- Python 3. Create the project venv once: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (`openpyxl`, `pdfplumber`). Every command in this README runs as `.venv/bin/python ./scripts/<script>.py`.
- GitHub Codespaces: `.devcontainer/devcontainer.json` creates the venv and installs the requirements when the codespace is created (Python 3.12, Node for the Claude Code CLI). The licensed sources in `data/ai/source/` are not in the repo; upload them to the codespace if you need to re-parse.
- The AI RMF sources (Playbook, CIS companion guides, CIS to CSF mapping) are not in the repo; see `data/ai/source/README.md`.
- A local clone of the CSET repo at `~/workstuff/cset` (only for building question banks).
- Run everything from the repo root, inside Claude Code.

## Commands

| Command | What it does |
|---|---|
| `/generate-questions` | The whole flow: intake (numbered choices) → freshness for CSF and AI together (missing banks are rebuilt, stale ones after asking) → `/csf-questionnaire` → `/ai-questionnaire` → `/assess-questionnaire` → one `questionnaire.xlsx`. Stops at the SoA question. Send the XLSX to control owners. |
| `/csf-questionnaire` | CSF drafts for a run folder: SoA question, scope, questions from the bank. Writes `csf_scope.json`, `csf_questions_draft.json`. |
| `/ai-questionnaire` | AI RMF drafts for a run folder: checks the banks, picks the client's questions by role, producer flags and AI areas from `ai_usage.json`. Writes `ai_scope.json`, `ai_questions_draft_<foundation|areas>.json`. |
| `/assess-questionnaire` | Independent review of every draft in a run folder (one fresh subagent each, in parallel), merges the changes, writes the sheets of `questionnaire.xlsx`. |
| `/build-csf-bank` | Builds the CSF question bank for one domain from the CSET repo (occasional; reused by every engagement). |
| `/build-ai-bank` | Builds the AI RMF mapping (AI area x subcategory), the two question banks (foundation, areas) and the CSF AI impact notes from the Playbook and CIS companion guides (quarterly, or when a source changes). Pilot first, then full run. |

The intake is `scripts/intake.py`: it prints the numbered menus (from `data/common/intake_options.json`), turns the typed numbers into values, and writes `intake.json` (org, domain, certs) and `ai_usage.json` in the run folder. Every later step reads those files.

**Not built yet:** the agentic answer session (`gen-eval-loop`), the Stage 2 XLS writer (including writing the AI impact notes into the CSF profile's Considerations column), and HTML generation as a command (today it is the `caizin-nist-assessment` and `caizin-ai-rmf-assessment` skills). The AI RMF banks and notes are built by `/build-ai-bank`; they exist only once that has been run.

### Building a bank (`/build-csf-bank`)

1. `extract_cset_candidates.py` replays the CSET SQL migrations into `cset_candidates.json` (skipped if CSET has not changed).
2. `build_question_bank.py` routes each question for the domain: **reject** (not answerable or empty), **accept** (source model matches the domain), or **pending**.
3. If anything is pending the agent decides it using `prompts/question_bank_judge.md`: which domains a question suits, rewording statements and repairing truncated text, and whether a widely-mapped question fits each subcategory. `record_judgements.py` validates and stores the verdicts (reused by every domain, redone only when CSET changes a question).
4. Run the build again; it writes `data/csf/banks/question_bank_<domain>.json`.

Domains: `healthcare`, `finance`, `manufacturing_ot`, `saas_cloud`, `consulting`, `other`.

### Running an engagement (`/generate-questions`)

1. `intake.py` asks once, as numbered choices: org, domain, certs, the AI usage profile (AI in use none / some / unsure, then "How do you use AI?" and "What does your AI include?", which give the client's AI areas) and the engagement flags. It writes `intake.json` and `ai_usage.json`; every later step, including the AI RMF track, reads them.
2. `check_freshness.py --all --run <run>` reports reference data, the CSF bank of the domain (stale when the CSET SQL changed upstream; it runs `git fetch` and says so if that fails) and every AI RMF stage. A missing CSF bank is built at once, a stale one after asking. AI banks are rebuilt the same way once a pilot has been accepted (`ai_pilot.py accept`); before that the AI sheet waits for `/build-ai-bank`.
3. `/csf-questionnaire`: `parse_soa.py <run> <soa>` extracts the SoA. If any excluded control needs reading, `compute_scope.py` exits 2 and the agent classifies it with `prompts/soa_exclusion_judge.md`. `compute_scope.py` gives each subcategory a type: `full_discovery`, `gap` (cert covers it, ask what goes beyond), `confirmatory` (cert should cover it, ask for evidence) or `skip`; policy is in `data/csf/scope_rules.json`. `build_questions.py` picks questions from the bank and words them for the certs held, producing `csf_questions_draft.json`.
4. `/ai-questionnaire`: see below.
5. `/assess-questionnaire`: a fresh assessor subagent per draft (`prompts/questionnaire_assessor.md`, `prompts/ai_rmf_questionnaire_assessor.md`) reads only its draft and returns only the entries it changed. `record_judgements.py log` validates and merges them, then `write_questionnaire.py` writes each framework's sheet of `questionnaire.xlsx` (each replaces only its own sheet).

### AI RMF track

**Building the banks (`/build-ai-bank`):**
1. `check_freshness.py --ai-bank` compares the SHA-256 of the current source files with the hashes each output recorded about its inputs, one line per stage; all current means skip.
2. `parse_ai_rmf_sources.py` turns the Playbook and the three CIS guides into `ai_rmf_core.json` (the 4 functions with their Playbook descriptions, 72 subcategories, suggested actions) and `cis_ai_safeguards.json` (153 safeguards per guide).
3. Mapping (agents, `prompts/ai_rmf_mapping_drafter.md` and `ai_rmf_mapping_evaluator.md`): per AI area (`data/ai/ai_areas.json`), the MAP, MEASURE and MANAGE subcategories that check it and the CIS safeguards that prove them, recorded by `record_ai_bank.py mapping` against `data/ai/mapping_rules.json`, reviewed in `mapping.xlsx` and accepted (`ai_pilot.py accept-mapping`).
4. Questions, generated and evaluated with subagents (`prompts/ai_rmf_question_generator.md`, `prompts/ai_rmf_question_evaluator.md`), two turns at most, into two banks: **foundation** (GOVERN and the 12 foundation subcategories, asked once for the organisation) and **areas** (one item per subcategory with every area's mapping row on it; a question may stand for several rows). Every question carries the roles it is asked of and any producer flags. `prepare_ai_bank.py batch <foundation|areas>` prepares each batch; `record_ai_bank.py assemble` and `questions` store the result (every row asked once, or twice when its check holds two practices, per role its area allows). Pilot first; when the user accepts it (`ai_pilot.py accept`, tied to the current generator and evaluator prompts) later rebuilds run without asking, like the CSF banks.
5. AI impact notes: `build_ai_impact_inputs.py` joins the CIS → CSF mapping to the MCP and agents guides (48 CSF subcategories); an agent writes an exposure layer and a use layer (`prompts/ai_impact_notes_writer.md`); `record_ai_bank.py notes` stores `data/csf/ai_impact_notes.json`.

**Running an engagement (`/ai-questionnaire`, run by `/generate-questions` or alone):** `build_ai_questions.py` picks the client's questions from both banks by filtering on `ai_usage.json`: roles (`scope_rules.json` `client_roles`), producer flags and, for area questions, the client's AI areas. A question shared by several of the client's areas carries "This question covers: ..." naming them. Every question is `full_discovery`: it asks what is done for AI, so it never repeats the CSF sheet or ISO 27001. It writes one draft per bank. `/assess-questionnaire` then reviews it (`prompts/ai_rmf_questionnaire_assessor.md`) and `write_questionnaire.py --framework ai` writes the AI RMF sheet of `questionnaire.xlsx`, plus an "AI systems" sheet where the client answers the inventory question (GOVERN 1.6) as a table: one row per system, what it involves, and its criticality.

## What is where

### Scripts

| Script | Job |
|---|---|
| `paths.py` | Where every file lives. Other scripts import from it. |
| `options.py` | Shared facts read from the data files (domains, certs, question types, function order, bank names), so no script keeps its own copy. Not run directly. |
| `intake.py` | The numbered intake: `menu` prints the choices, `write` maps the typed numbers to values and writes `intake.json` and `ai_usage.json` in a new run folder. |
| `audit.py` | Shared helper (not run directly). Every script calls it to append to `audit.jsonl`; a step that crashes or is aborted still leaves an `incomplete` line. |
| `parse_crosswalk.py` | `data/csf/source/csf2.xlsx` (NIST download) → `csf2_core.json` and the crosswalks; records the refresh in `data/metadata.json`. |
| `check_freshness.py` | Reports stale data files from `data/metadata.json`; `--ai-bank` reports each stage of the AI RMF build as current, stale, missing or incomplete; `--all --run <run>` reports CSF and AI together for the start of an engagement. |
| `extract_cset_candidates.py` | CSET SQL → `cset_candidates.json`. |
| `build_question_bank.py` | Routes questions for a domain; writes the bank or a pending file. |
| `record_judgements.py` | Validates and logs agent judgements (bank build, and `log` mode for engagement steps). |
| `parse_soa.py` | SoA Excel → `soa_parsed.json` in the run folder. Extracts only; never assumes. |
| `compute_scope.py` | Question type per subcategory, from state plus `scope_rules.json`. |
| `build_questions.py` | Bank + scope → `csf_questions_draft.json`. |
| `write_questionnaire.py` | `csf_questions_assessed.json` → the CSF sheet of `questionnaire.xlsx`; with `--framework ai`, the AI question files → the AI RMF sheet of the same workbook (an Area column: whole organisation, the AI area, or the areas a shared question covers). Each replaces only its own sheet. |
| `parse_ai_rmf_sources.py` | AI RMF Playbook and CIS companion guide PDFs → `ai_rmf_core.json`, `cis_ai_safeguards.json`. |
| `sheet_io.py` | Spreadsheet ↔ JSON for every sheet a person edits or reviews (`import` checks the whole sheet and writes the JSON; `export` writes the spreadsheet with dropdowns). Columns and allowed values are in `data/common/sheet_specs.json`. Today: `ai_areas` (the spreadsheet is the decision), `mapping` (review sheet of `mapping.json`: one line per AI area x MAP, MEASURE or MANAGE subcategory with the Playbook outcome and safeguard titles, plus a Coverage sheet; edits come back as `decided_by: human`), and `area_questions` / `foundation_questions` (review sheets of the two question banks: one line per question, checked like agent output on import). |
| `prepare_ai_bank.py` | Writes the compact input an agent reads in the AI bank build: `batch <foundation|areas>` (questions) and `mapping --area ID` (one AI area, the function definitions, the MAP, MEASURE and MANAGE subcategories (GOVERN is the foundation, asked once for the organisation), the area's candidate CIS safeguards). |
| `record_ai_bank.py` | The door for AI RMF agent output: `mapping`, `questions`, `notes` (validate, store, log; `mapping` enforces `data/ai/mapping_rules.json`, `questions` the coverage of every mapping row and role); script-only `assemble` and `revalidate` (after a rules or other-area change, re-checks recorded areas without an agent). |
| `ai_pilot.py` | The human gates: `accept` records the user's acceptance of the pilot, `accept-mapping` of the reviewed AI RMF mapping; `pilot_status()` and `mapping_status()` are what the freshness check reads. |
| `ai_bank_common.py` | Helpers shared by the AI bank scripts. Not run directly. |
| `build_ai_impact_inputs.py` | CIS → CSF 2.0 mapping joined to the MCP and agents guide safeguards → `impact_pending.json` (Step 5 input). |
| `build_ai_questions.py` | `ai_usage.json` + `scope_rules.json` + the two banks → `ai_scope.json` (what was picked per subcategory and why) and `ai_questions_draft_<foundation|areas>.json`. |

### Prompts (`prompts/`)

How the agent judges: `question_bank_judge.md`, `soa_exclusion_judge.md`, `questionnaire_assessor.md` (CSF); `ai_rmf_mapping_drafter.md`, `ai_rmf_mapping_evaluator.md`, `ai_rmf_question_generator.md`, `ai_rmf_question_evaluator.md`, `ai_rmf_questionnaire_assessor.md`, `ai_impact_notes_writer.md` (AI RMF). Commands (`.claude/commands/`) say what to run; prompts say how to judge.

### Data (`data/`)

Not written during an engagement; that output goes to `runs/`.

```
data/
├── metadata.json            source, last refresh and staleness threshold per file
├── tier_definitions.json    NIST Tier 1-4 (not used yet; needed to map answers to tiers)
├── common/
│   ├── intake_options.json  intake menus, domains, certs, question types (shared by both tracks)
│   └── sheet_specs.json     columns and allowed values of every spreadsheet sheet_io.py converts
├── csf/
│   ├── source/csf2.xlsx     NIST CPRT export (refreshed about yearly)
│   ├── csf2_core.json       CSF 2.0 subcategories and examples
│   ├── scope_rules.json     state → question type, max questions per type, domain bump, function order
│   ├── domain_weights.json  per-sector priorities
│   ├── evidence_prompts.json  evidence hint per CSF category
│   ├── crosswalks/          ISO 27001 and PCI DSS mappings
│   ├── banks/               question_bank_<domain>.json
│   └── bank_build/          cset_candidates.json, cset_judgements.json (cannot be regenerated; back it up), judgement_log/, audit.jsonl
├── audit.jsonl              data refresh and freshness checks (created on first run)
└── ai/
    ├── source/                 AI RMF Playbook, CIS companion guides, CIS → CSF mapping (not in the repo; see source/README.md; SHA-256 in metadata.json)
    ├── parse_config.json       expected counts and file names for the parser
    ├── ai_rmf_core.json        4 functions (Playbook description) with their 72 subcategories + suggested actions (parsed)
    ├── cis_ai_safeguards.json  safeguards of the three guides (parsed)
    ├── question_rules.json     question banks: roles, producer flags, impacts, question counts, the AI systems sheet
    ├── area_client_labels.json what the client sees for each AI area (area id -> plain label)
    ├── authoring/ai_areas.xlsx  AI areas and their impact, decided by a person (sheet_io.py import -> ai_areas.json)
    ├── ai_areas.json           generated from authoring/ai_areas.xlsx; scripts read this
    ├── mapping_rules.json      candidate CIS controls per AI area, required checks, foundation subcategories
    ├── mapping.json            AI area x function -> subcategory, CIS safeguards, impact (record_ai_bank.py mapping)
    ├── authoring/mapping.xlsx  the mapping for review (sheet_io.py export mapping; edits back with import mapping)
    ├── authoring/questions_<areas|foundation>.xlsx  the question banks for review (sheet_io.py export area_questions / foundation_questions)
    ├── scope_rules.json        engagement policy: AI area rules for the intake, roles each client is asked as, notes
    ├── evidence_prompts.json   evidence hint per question (foundation, or by the impacts of the rows it covers)
    ├── banks/                  question_bank_ai_rmf_<foundation|areas>.json (none yet: generated in TODO step 6)
    └── bank_build/             audit.jsonl, pending/work files, judgement_log/ (write-once records of agent steps)
```

### Runs (`runs/<Org>_<date>/`)

One folder per engagement. It holds client data, so keep it out of any shared repo.

| File | What |
|---|---|
| `inputs/soa_original.xlsx` | Client SoA (if provided) |
| `soa_parsed.json`, `soa_pending.json`, `soa_judgements.json` | Parsed SoA, controls needing a reading, the agent's classifications |
| `intake.json` | Org, date, domain, certifications (from `intake.py`; read by scope, question building and the freshness check) |
| `ai_usage.json` | The AI usage profile (AI in use, role, producer flags, the client's AI areas, engagement flags), from the same intake |
| `csf_scope.json` | Question type per subcategory, with the reason |
| `ai_scope.json`, `ai_questions_draft_<bank>.json`, `ai_questions_assessed_<bank>.json` | The AI RMF track for the run (scope, drafts, assessor merge); the AI RMF sheet goes into `questionnaire.xlsx` |
| `csf_question_bank_used.json`, `csf_questions_draft.json` | Bank snapshot, generated questions |
| `csf_questions_assessed_patch.json`, `csf_questions_assessed.json` | Assessor's changes only, merged full list |
| `questionnaire.xlsx` | The deliverable workbook with the CSF sheet and the AI RMF sheet |
| `audit.jsonl` | Timeline of the whole run: every script and agent step, with status (`ok`, `pending`, `rejected`, `error`, `incomplete`), file hashes and the intake answers (domain, certs) |
| `judgement_log/` | Full write-once record of each agent step (model, prompt hash, output snapshot) |

### Tests

`tests/fixtures/` has `sample_soa.xlsx` and `caizin_ai_rmf_profile_v2.xlsx` (the schema the future XLS writer must match). `.venv/bin/python -m unittest discover -s tests` checks the AI RMF parser output and scripts, the intake, the shared options and the workbook writer (stores redirected to a temp dir).

## Status

- CSF bank pipeline is built and tested on real CSET data. First bank: `finance` (68 of 106 subcategories have candidate questions; the other 38 use a generic fallback question).
- Other domains are not built yet. The ACET questions are tagged for domain once, and those verdicts serve all remaining banks.
- A full engagement on the new pipeline has not been run end to end.
- AI RMF track: being rebuilt on the AI areas model (`AI_RMF_Mapping_Sheet_Design.md`, `TODO.md`). The sources are parsed (72 subcategories, 459 safeguards); the AI areas, intake and mapping are built and the mapping is accepted; the question tooling (batch, prompts, recording, selection) is built, but `/ai-questionnaire` has no AI RMF bank until the banks are generated (TODO step 6). The CSF track is unaffected.

## Glossary

| Term | Meaning |
|---|---|
| **Bank** | A frozen set of questions, built once and reused. CSF: one per domain, from CSET (candidate questions). AI RMF: two, foundation and areas, generated from the Playbook and CIS guides; they hold every possible question, each tagged with the roles it is asked of. A questionnaire picks from a bank; it never invents questions. |
| **AI area** | A way AI is used (internal process, code generation, customer-facing, vendor AI, model building, invisible usage) or a part of the AI ecosystem (input, output, data, model, source data, MCP / tools, agent, hosting). Decided in `data/ai/authoring/ai_areas.xlsx`. |
| **Mapping row** | One AI area x one AI RMF subcategory (MAP, MEASURE or MANAGE): what is checked for that area, the CIS safeguards that prove it, the impact. Area questions are written per row. |
| **Foundation** | GOVERN and 12 other subcategories about how the organisation runs AI risk management: asked once for the organisation, never per area. |
| **Question type** | Set per subcategory at engagement time. `full_discovery`: nothing is covered, ask everything. `gap`: existing controls cover the standard part, ask what goes beyond (AI: what differs for AI). `confirmatory`: a certification should cover it, ask for evidence (CSF only today). `skip`: not asked. |
| **Assessor** | An independent agent that reviews a draft questionnaire and returns only what it changed. |
| **Domain** | The client's sector for the CSF bank: healthcare, finance, manufacturing_ot, saas_cloud, consulting, other. |
| **SoA** | The client's ISO 27001 Statement of Applicability. It sets CSF question types for ISO-mapped subcategories. |
| **AI in use** | `none`, `some` or `unsure`. `unsure` is asked as a consumer and as an org with no AI; the questions discover what AI is used. `none` gets the AI policy and shadow-AI questions only. |
| **Producer / consumer** | Producer builds or distributes AI models. Consumer uses AI (including fine-tuning a model for own use). Different question sets, not tiers; an org can be both. |
| **Producer flags** | For a producer: the model is built on an existing model (base-model questions), and it is given to others (release questions). |
| **Covers note** | "This question covers: ..." on an area question that stands for several of the client's areas, naming only the client's own areas. |
| **Pending file / exit 2** | A script that cannot settle an item writes a `pending_*.json` and exits 2; an agent decides it and a recording script stores the answer. |
| **Recording** | Validating an agent's output file as a whole, storing it, and writing a write-once log of who decided what. A bad file is rejected and nothing is stored. |
| **Pilot** | The first AI bank run on a few hand-picked subcategories, reviewed by a person. Accepting it lets later rebuilds run without asking. |
| **Stale / incomplete** | Freshness report words. Stale: built from sources that have since changed. Incomplete: not every subcategory is in the bank yet (AI areas bank: or a mapping row changed after its questions were written). |
| **Run folder** | `runs/<Org>_<date>/`: everything one engagement produced. It holds client data. |
| **Profile XLS (Stage 2)** | The XLS built from the answered questionnaire, one for CSF and one for AI RMF, used for the HTML reports. Not built yet. |
| **CSET, OLIR, Playbook, CIS guides** | CSET: CISA's assessment tool whose SQL holds the CSF questions. OLIR: NIST's mappings between frameworks (ISO 27001 and PCI DSS to CSF). Playbook: the AI RMF's suggested actions. CIS guides: the CIS Controls v8.1 AI companion guides (LLM, MCP, agents). |

## Notes

- Caizin-specific AI RMF working files are archived in `~/workstuff/caizin-ai-rmf-archive/` (downstream copies in `~/workstuff/NIST/`). Retired CSF-tool material is in `~/workstuff/caizin-csf-tool-archive/`.
- Related repos: `gen-eval-loop/` (Stage 2 harness), `NIST/` (reference data, profile XLS files, assessment HTMLs).
