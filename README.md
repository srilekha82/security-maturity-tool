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
| Build or refresh the AI RMF banks and the CSF AI impact notes | `/build-ai-bank`: pilot first; after you accept the pilot (`ai_pilot.py accept`) later rebuilds run on their own. |
| Use a new Playbook, CIS guide or CSF download | Replace the file (`data/ai/source/` or `data/csf/source/csf2.xlsx`, links in `data/metadata.json`). The freshness check sees the change; rebuild with the commands above. |
| Change how many questions per type, or when a question is `gap` | `data/csf/scope_rules.json` (CSF), `data/ai/scope_rules.json` (AI). No code change. |
| Change an intake menu, a domain, a certification or the question-type order | `data/common/intake_options.json`. Every script reads it through `scripts/options.py`. |
| Change the AI question categories or definitions | `data/ai/question_categories.json`. The applicability stage then shows stale; re-run `/build-ai-bank` to redo it. |
| Change the AI areas (usage and ecosystem components, their impact) | Edit `data/ai/authoring/ai_areas.xlsx` (the decision), then `.venv/bin/python ./scripts/sheet_io.py import ai_areas` (checks every row, writes `data/ai/ai_areas.json`). The model is in `AI_RMF_Mapping_Sheet_Design.md`; the areas are not yet used to build the banks (see `TODO.md`). |
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
- The AI RMF sources (Playbook, CIS companion guides, CIS to CSF mapping) are not in the repo; see `data/ai/source/README.md`.
- A local clone of the CSET repo at `~/workstuff/cset` (only for building question banks).
- Run everything from the repo root, inside Claude Code.

## Commands

| Command | What it does |
|---|---|
| `/generate-questions` | The whole flow: intake (numbered choices) → freshness for CSF and AI together (missing banks are rebuilt, stale ones after asking) → `/csf-questionnaire` → `/ai-questionnaire` → `/assess-questionnaire` → one `questionnaire.xlsx`. Stops at the SoA question. Send the XLSX to control owners. |
| `/csf-questionnaire` | CSF drafts for a run folder: SoA question, scope, questions from the bank. Writes `csf_scope.json`, `csf_questions_draft.json`. |
| `/ai-questionnaire` | AI RMF drafts for a run folder: checks the banks, scope from `ai_usage.json`, picks from the banks. Writes `ai_scope.json`, `ai_questions_draft_<bank>.json`. |
| `/assess-questionnaire` | Independent review of every draft in a run folder (one fresh subagent each, in parallel), merges the changes, writes the sheets of `questionnaire.xlsx`. |
| `/build-csf-bank` | Builds the CSF question bank for one domain from the CSET repo (occasional; reused by every engagement). |
| `/build-ai-bank` | Builds the AI RMF producer and consumer banks and the CSF AI impact notes from the Playbook and CIS companion guides (quarterly, or when a source changes). Pilot first, then full run. |

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
2. `parse_ai_rmf_sources.py` turns the Playbook and the three CIS guides into `ai_rmf_core.json` (72 subcategories, suggested actions) and `cis_ai_safeguards.json` (153 safeguards per guide).
3. Applicability pass (agent, `prompts/ai_rmf_applicability_judge.md`): which question categories (`data/ai/question_categories.json`) each subcategory can produce questions for, per bank. A subcategory applies to a bank iff it maps to at least one category.
4. AI RMF → CIS link (agent, `prompts/ai_rmf_cis_linker.md`): evidence and tagging links, validated against the guides.
5. Generate and evaluate with subagents (`prompts/ai_rmf_question_generator.md`, `prompts/ai_rmf_question_evaluator.md`), two turns at most; `record_ai_bank.py assemble` and `candidates` store the result (`prepare_ai_bank.py batch` prepares each batch). Pilot of 6 subcategories first; when the user accepts it (`ai_pilot.py accept`, tied to the current generator and evaluator prompts) later rebuilds run without asking, like the CSF banks.
6. AI impact notes: `build_ai_impact_inputs.py` joins the CIS → CSF mapping to the MCP and agents guides (48 CSF subcategories); an agent writes an exposure layer and a use layer (`prompts/ai_impact_notes_writer.md`); `record_ai_bank.py notes` stores `data/csf/ai_impact_notes.json`.

**Running an engagement (`/ai-questionnaire`, run by `/generate-questions` or alone):** `build_ai_questions.py` gives each subcategory a question type per bank from `ai_usage.json` and `data/ai/scope_rules.json` (topic-level: with a CSF assessment done or ISO 27001 held, data, infrastructure and access topics become `gap`), then filters bank candidates by rung, usage context and modifiers and writes one draft per bank. `/assess-questionnaire` then reviews it (`prompts/ai_rmf_questionnaire_assessor.md`) and `write_questionnaire.py --framework ai` writes the AI RMF sheet of `questionnaire.xlsx`.

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
| `write_questionnaire.py` | `csf_questions_assessed.json` → the CSF sheet of `questionnaire.xlsx`; with `--framework ai`, the AI question file(s) → the AI RMF sheet of the same workbook (Role column when both banks apply). Each replaces only its own sheet. |
| `parse_ai_rmf_sources.py` | AI RMF Playbook and CIS companion guide PDFs → `ai_rmf_core.json`, `cis_ai_safeguards.json`. |
| `sheet_io.py` | Spreadsheet ↔ JSON for every sheet a person edits or reviews (`import` checks the whole sheet and writes the JSON; `export` writes the spreadsheet with dropdowns). Columns and allowed values are in `data/common/sheet_specs.json`. Today: `ai_areas`. |
| `prepare_ai_bank.py` | Writes the compact input an agent reads in the AI bank build: `applicability`, `crosswalk`, `batch`. |
| `record_ai_bank.py` | The door for AI RMF agent output: `applicability`, `crosswalk`, `candidates`, `notes` (validate, store, log); script-only `assemble`. |
| `ai_pilot.py` | The pilot gate: `accept` records the user's acceptance of the pilot; `pilot_status()` is what the freshness check reads. |
| `ai_bank_common.py` | Helpers shared by the three AI bank scripts. Not run directly. |
| `build_ai_impact_inputs.py` | CIS → CSF 2.0 mapping joined to the MCP and agents guide safeguards → `impact_pending.json` (Step 5 input). |
| `build_ai_questions.py` | `ai_usage.json` + `scope_rules.json` + banks → `ai_scope.json` (question type per subcategory and bank) and `ai_questions_draft_<bank>.json`. |

### Prompts (`prompts/`)

How the agent judges: `question_bank_judge.md`, `soa_exclusion_judge.md`, `questionnaire_assessor.md` (CSF); `ai_rmf_applicability_judge.md`, `ai_rmf_cis_linker.md`, `ai_rmf_question_generator.md`, `ai_rmf_question_evaluator.md`, `ai_rmf_questionnaire_assessor.md`, `ai_impact_notes_writer.md` (AI RMF). Commands (`.claude/commands/`) say what to run; prompts say how to judge.

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
    ├── ai_rmf_core.json        72 subcategories + suggested actions (parsed)
    ├── cis_ai_safeguards.json  safeguards of the three guides (parsed)
    ├── question_categories.json  categories per bank, enums and shared definitions (roles, rungs, usage contexts, modifiers, topics)
    ├── authoring/ai_areas.xlsx  AI areas and their impact, decided by a person (sheet_io.py import -> ai_areas.json)
    ├── ai_areas.json           generated from authoring/ai_areas.xlsx; scripts read this
    ├── applicability.json      subcategory → bank applicability (agent, recorded)
    ├── scope_rules.json        question-type policy, filters and ranking for engagements, function and bank order
    ├── evidence_prompts.json   evidence hint per question topic
    ├── crosswalks/             airmf_to_cis.json (agent, recorded)
    ├── banks/                  question_bank_ai_rmf_<producer|consumer>.json
    └── bank_build/             audit.jsonl, pending/work files, judgement_log/ (write-once records of agent steps)
```

### Runs (`runs/<Org>_<date>/`)

One folder per engagement. It holds client data, so keep it out of any shared repo.

| File | What |
|---|---|
| `inputs/soa_original.xlsx` | Client SoA (if provided) |
| `soa_parsed.json`, `soa_pending.json`, `soa_judgements.json` | Parsed SoA, controls needing a reading, the agent's classifications |
| `intake.json` | Org, date, domain, certifications (from `intake.py`; read by scope, question building and the freshness check) |
| `ai_usage.json` | The AI usage profile (AI in use, the client's AI areas, engagement flags; plus role, rung and usage contexts derived from the areas for the current question filter), from the same intake |
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
- AI RMF track: parser, freshness gate, recording script, scope and question builders, prompts, commands and tests are built. The sources are parsed (72 subcategories, 459 safeguards). The agent passes (applicability, CIS link, pilot, full bank, impact notes) have not been run yet: run `/build-ai-bank`, pilot first.

## Glossary

| Term | Meaning |
|---|---|
| **Bank** | A frozen set of candidate questions, built once and reused. CSF: one per domain, from CSET. AI RMF: two, producer and consumer, generated from the Playbook and CIS guides. |
| **Candidate** | One bank question with its tags (AI: rung, usage context, topic, modifiers). A questionnaire picks candidates; it never invents questions. |
| **Question type** | Set per subcategory at engagement time. `full_discovery`: nothing is covered, ask everything. `gap`: existing controls cover the standard part, ask what goes beyond (AI: what differs for AI). `confirmatory`: a certification should cover it, ask for evidence (CSF only today). `skip`: not asked. |
| **Assessor** | An independent agent that reviews a draft questionnaire and returns only what it changed. |
| **Domain** | The client's sector for the CSF bank: healthcare, finance, manufacturing_ot, saas_cloud, consulting, other. |
| **SoA** | The client's ISO 27001 Statement of Applicability. It sets CSF question types for ISO-mapped subcategories. |
| **AI in use** | `none`, `some` or `unsure`. `unsure` is scoped like `some` (consumer, base rung) and the questions discover what AI is used. `none` still asks the shadow-AI check. |
| **Producer / consumer** | Producer builds or distributes AI models. Consumer uses AI (including fine-tuning a model for own use). Different question sets, not tiers; an org can be both. |
| **Rung** | How far the AI reaches, each includes the ones below: `base` (prompt only) < `rag` (reads org data) < `mcp` (has tools) < `agentic` (autonomous). |
| **Usage context, modifier** | Context: `internal`, `code_generation`, `customer_facing`, `third_party_embedded`. Modifier: `poc`, `self_hosted`, `builds_on_base_model`, `unsanctioned_use` (shadow AI). |
| **Topic** | The area a question covers: `governance`, `data_model`, `infra`, `reliability`, `ai_access`. |
| **Pending file / exit 2** | A script that cannot settle an item writes a `pending_*.json` and exits 2; an agent decides it and a recording script stores the answer. |
| **Recording** | Validating an agent's output file as a whole, storing it, and writing a write-once log of who decided what. A bad file is rejected and nothing is stored. |
| **Pilot** | The first AI bank run on 6 hand-picked subcategories, reviewed by a person. Accepting it lets later rebuilds run without asking. |
| **Stale / incomplete** | Freshness report words. Stale: built from sources that have since changed. Incomplete: not every applicable subcategory is in the bank yet. |
| **Run folder** | `runs/<Org>_<date>/`: everything one engagement produced. It holds client data. |
| **Profile XLS (Stage 2)** | The XLS built from the answered questionnaire, one for CSF and one for AI RMF, used for the HTML reports. Not built yet. |
| **CSET, OLIR, Playbook, CIS guides** | CSET: CISA's assessment tool whose SQL holds the CSF questions. OLIR: NIST's mappings between frameworks (ISO 27001 and PCI DSS to CSF). Playbook: the AI RMF's suggested actions. CIS guides: the CIS Controls v8.1 AI companion guides (LLM, MCP, agents). |

## Notes

- Caizin-specific AI RMF working files are archived in `~/workstuff/caizin-ai-rmf-archive/` (downstream copies in `~/workstuff/NIST/`). Retired CSF-tool material is in `~/workstuff/caizin-csf-tool-archive/`.
- Related repos: `gen-eval-loop/` (Stage 2 harness), `NIST/` (reference data, profile XLS files, assessment HTMLs).
