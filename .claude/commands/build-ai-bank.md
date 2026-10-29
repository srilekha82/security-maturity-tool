# /build-ai-bank — build the AI RMF 1.0 mapping and question banks

Builds the AI RMF mapping (AI area x subcategory, `data/ai/mapping.json`), then the two question banks,
`data/ai/banks/question_bank_ai_rmf_foundation.json` (asked once for the organisation) and
`question_bank_ai_rmf_areas.json` (per mapping row), from the AI RMF Playbook and the three CIS AI companion guides, then
the CSF AI impact notes (`data/csf/ai_impact_notes.json`). The banks hold every possible question, each tagged with the
roles it is asked of and any producer flags; `/ai-questionnaire` picks a client's questions from them.
Run quarterly, or when a source file changes. Scripts parse, prepare, validate, record and decide nothing; agents judge,
and hand every result in through `scripts/record_ai_bank.py`, which rejects a whole file if anything is wrong. The judging rules are
in the prompts named in each step. Do not re-implement any parsing or validation inline.

Use your tools (Bash, Read, Write, Agent). Working directory: `caizin-csf-tool/` repo root.

Say little: the script summary lines and the final report.

Replace `<model id>` in the record commands with the model id of the agent that produced the file.

---

## Step 1 — Freshness gate

```bash
.venv/bin/python ./scripts/check_freshness.py --ai-bank
```

One line per stage (parse, bank foundation, bank areas, notes, pilot, ai areas, mapping): `current`, `missing`, `stale`
or `incomplete`. A
stage is current only if it was built from the exact source files on disk (each output records the SHA-256 of its inputs).

- Exit 0: everything is current and complete. Tell the user and stop, unless they ask to force a rebuild.
- Exit 1 with `sources: missing ...`: point to `data/ai/source/README.md` and stop.
- Exit 1 otherwise: do only the stages that are not current, in the order below; a stale stage makes the ones after it
  stale too. Tell the user which stages you will run.

## Step 2 — Parse the sources

```bash
.venv/bin/python ./scripts/parse_ai_rmf_sources.py
```

Writes `data/ai/ai_rmf_core.json` (the 4 functions with their Playbook descriptions, and their 72 subcategories with
suggested actions) and
`data/ai/cis_ai_safeguards.json` (the safeguards of the three guides). It fails, writing nothing, if a count is off.
Agents read these files, never the PDFs.

## Steps 3 and 4 — Mapping (see `AI_RMF_Mapping_Sheet_Design.md`)

Maps each AI area (`data/ai/ai_areas.json`, decided by the user in `data/ai/authoring/ai_areas.xlsx`) to AI RMF
subcategories of MAP, MEASURE and MANAGE, with the CIS safeguards that prove them. GOVERN is the foundation (asked once
for the organisation, by role) and is never mapped to an area. Run only when the user asks for it, one AI area at a
time; the first run is a pilot on one area the user names, then stop and report. Work files go under
`data/ai/bank_build/work/` (delete them once the area is recorded).

1. Prepare the area's input:
   ```bash
   .venv/bin/python ./scripts/prepare_ai_bank.py mapping --area <area id>
   ```
   It writes `data/ai/bank_build/mapping_input_<area>.json`.
2. **Drafter** (a fresh subagent): follow `prompts/ai_rmf_mapping_drafter.md` with that input; write
   `work/mapping_<area>_draft1.json`. Pass paths, not content.
3. **Evaluator** (another fresh subagent; it must not see the drafter's prompt): follow
   `prompts/ai_rmf_mapping_evaluator.md` with the input and the draft; write its findings (kinds `row`, `missing`,
   `note`) to `work/mapping_<area>_eval1.json`.
4. If there are `row` or `missing` findings (notes alone do not need a revision): a fresh drafter revises (inputs: the input file, `draft1`, `eval1`; output the complete
   `work/mapping_<area>_draft2.json`), and a fresh evaluator checks it into `work/mapping_<area>_eval2.json`. Two turns at
   most.
5. Record the last draft with the last evaluation (rows still failing are stored as `needs_human_review`, subcategories
   still missing in the area's `missing` list, notes in `notes`; all three show in the review sheet):
   ```bash
   .venv/bin/python ./scripts/record_ai_bank.py mapping data/ai/bank_build/work/mapping_<area>_draft<N>.json \
       --review data/ai/bank_build/work/mapping_<area>_eval<N>.json --model <drafter model id> --session "evaluator=<model id>"
   ```
   If it lists problems (ids, candidates, impacts, a missing function or required check), send them back to the drafter
   and repeat; nothing is stored until it passes. It prints how many areas are recorded and how many AI RMF
   subcategories are not reached yet.

After each area is recorded, refresh the review sheet: `.venv/bin/python ./scripts/sheet_io.py export mapping` (writes
`data/ai/authoring/mapping.xlsx`; it refuses if the sheet has edits not yet imported: ask the user to import them first
with `sheet_io.py import mapping`).

After the pilot areas (the user names them; for the 2026-10-26 re-run: `mcp_tools`, `agent`, `model`): stop. Show the user the recorded rows (function, subcategory, safeguards, impact, why), what the
evaluator failed, the missing rows and notes, the subcategories still unreached, and token use if you can see it, and point them to the review
sheet. The user reviews before any other area is drafted.

A changed mapping row makes the area questions written for it stale (Step 6 lists them). The review sheet flags
such a subcategory on every line ("the mapping rows changed ..."); the user either has it regenerated (Step 5,
`--ids`) or, if the questions still fit, sets its lines pass and imports, which stores them for the rows as they are
now.

After a change to `data/ai/mapping_rules.json` or to another AI area's row, do not re-draft: run
`.venv/bin/python ./scripts/record_ai_bank.py revalidate` (script only). Re-draft only the areas it names (their own
row or the sources changed), and send the user any rule problems it lists to fix in the sheet.

When every area is recorded and the user has reviewed the sheet (no row left needs_human_review, edits imported), the
user accepts the mapping: `.venv/bin/python ./scripts/ai_pilot.py accept-mapping`. Re-drafting an area later keeps the
user's decisions (rows decided_by human, lines they removed).

## Step 5 — Questions (subagents; needs the mapping accepted as it is now)

Two banks, built the same way: **foundation** (GOVERN and the 12 foundation subcategories of
`data/ai/mapping_rules.json`; questions per subcategory from the Playbook, each tagged with the roles it is asked of:
none, consumer, producer) and **areas** (one item per subcategory with every AI area's mapping row on it; each row is
asked once per role its area allows, or twice when its check holds two practices, and rows that would get the same
question share one). Use Sonnet
(`model: "sonnet"`) for the generator and Opus (`model: "opus"`) for the evaluator (decided 2026-10-29: two Sonnet
evaluators agreed on style but each missed different wrong citations and duplicates).

Ask the user: **pilot** (a few subcategories the user agrees to, then stop for review) or **full** (all subcategories
not yet recorded, one AI RMF function per batch).

### Pilot
Propose about 6 subcategories and show them to the user before running (wait for confirmation):
- two foundation: one GOVERN policy subcategory (e.g. GOVERN 1.2) and GOVERN 1.6 (the AI system inventory)
- one area subcategory with many areas (e.g. MEASURE 2.8, the audit trail: tests sharing)
- one with producer-only areas and a producer flag (e.g. a MANAGE row on model_building about releases)
- one with a folded subcategory (e.g. MAP 3.2 on internal_process folds MAP 5.1)
- one MAP subcategory on usage areas (e.g. MAP 1.4)

### The loop (per batch: the pilot's ids of one bank, or one AI RMF function in a full run)
Work files go under `data/ai/bank_build/work/` (create it; delete the files once the batch is recorded).

1. Prepare the batch input:
   ```bash
   .venv/bin/python ./scripts/prepare_ai_bank.py batch <foundation|areas> --ids "<ID>" ... --tag <tag>   # pilot
   .venv/bin/python ./scripts/prepare_ai_bank.py batch <foundation|areas> --function MEASURE --missing    # full
   ```
   It writes `data/ai/bank_build/batch_<bank>_<tag>.json`.
2. **Generator** (a fresh subagent via the Agent tool, Sonnet): tell it to follow
   `prompts/ai_rmf_question_generator.md` with the batch file as input and to write its output to `work/<tag>_gen1.json`.
   Pass paths, not content.
3. **Evaluator** (another fresh subagent, Opus): tell it to follow `prompts/ai_rmf_question_evaluator.md` with the
   batch file and `work/<tag>_gen1.json`, and to write its verdicts (every check of every question, and a `complete`
   verdict per subcategory) to `work/<tag>_eval1.json`. It must not see the generator's prompt.
4. If `eval1` fails anything: a fresh generator subagent revises only those subcategories (inputs: the batch file,
   `gen1`, `eval1`; output `work/<tag>_gen2.json` with the COMPLETE question list of each failing subcategory), then a
   fresh evaluator checks `gen2` into `work/<tag>_eval2.json`, given also `gen1` and `eval1` (round 2: unchanged
   questions that passed keep their verdicts, except checks 6 and 7). Two turns at most.
5. Assemble and record (the script marks a subcategory `needs_human_review` if it still fails after turn 2; it rejects
   an evaluator file without a verdict on every check of every question, or a round 2 file that fails an unchanged
   question that passed round 1 on a check other than 6 and 7: send it back to the evaluator):
   ```bash
   .venv/bin/python ./scripts/record_ai_bank.py assemble --gen1 work/... --eval1 work/... [--gen2 ... --eval2 ...] --out data/ai/bank_build/work/<tag>_record.json
   .venv/bin/python ./scripts/record_ai_bank.py questions <foundation|areas> data/ai/bank_build/work/<tag>_record.json \
       --model <generator model id> --session "evaluator=<evaluator model id>"
   ```
   If `questions` lists problems (a row not asked, or asked more than twice, for a role; a role the area does not allow; a
   safeguard not of the row; a fold not cited; a foundation subcategory without a consumer or producer question), send
   them back to the generator and repeat; nothing is stored until it passes. A subcategory the user decided in the
   review sheet is refused: leave it out of the batch, or add `--replace-human` only if the user agreed.
6. Refresh the review sheet of that bank: `.venv/bin/python ./scripts/sheet_io.py export area_questions` (or
   `foundation_questions`); it refuses if the sheet has edits not yet imported: ask the user to import them first.

### After the pilot: stop
Do not continue to a full run on your own. Report to the user: how many subcategories passed on turn 1 and turn 2, how
many need human review, and token use per batch if you can see it. Show 2 or 3 PASSING questions as well as the
failures (include a shared question and its rows), so passes get reviewed too. Run the evaluator once on a file with 3
deliberately weak, checkbox-style questions added to a copy of one subcategory (never recorded) and report whether it
caught them. Point the user to the review sheets (`data/ai/authoring/questions_areas.xlsx`,
`questions_foundation.xlsx`); the user cannot easily edit spreadsheets, so take their decisions in chat, apply them to
the sheet and run `sheet_io.py import area_questions` / `foundation_questions`. The user tunes the generator and
evaluator prompts from this, then runs `/build-ai-bank` again for the full run.

When the user says the pilot is good, record it:
```bash
.venv/bin/python ./scripts/ai_pilot.py accept --note "<what the user said>"
```
The acceptance is tied to the current generator and evaluator prompts. From then on `/generate-questions` rebuilds a
missing or incomplete AI bank on its own, like a CSF bank. If either prompt is edited later the acceptance goes stale
and a new pilot is needed before the next rebuild.

### Full run
Use `prepare_ai_bank.py batch <bank> --function <MAP|MEASURE|MANAGE|GOVERN> --missing` so each batch holds only
subcategories not yet recorded (split a function with `--ids` if the batch is large), and run the loop per batch. At
the end show the user a random sample of 5 passing subcategories to spot-check.

## Step 6 — Check completeness

```bash
.venv/bin/python ./scripts/check_freshness.py --ai-bank
```

Both `bank foundation` and `bank areas` must show `current`. `incomplete` lists what is missing, or the area
subcategories whose mapping rows changed after their questions were written: go back to Step 5 (`--missing`, or
`--ids` for the changed ones).

## Step 7 — AI impact notes (agent; skip if sources are unchanged and notes exist)

Notes for orgs reached by external agents or AI-enabled attackers, and where AI use changes the reading.

```bash
.venv/bin/python ./scripts/build_ai_impact_inputs.py
```

It joins the CIS → CSF 2.0 mapping to the MCP and agents guide safeguards and writes
`data/ai/bank_build/impact_pending.json` (about 48 CSF subcategories; the unmapped ones are listed, not guessed). Read
`prompts/ai_impact_notes_writer.md` and that file. Run the two layers in order, each as a patch file, each recorded:

1. Layer 1 (exposure): write `data/ai/bank_build/notes_layer1.json`, then
   `.venv/bin/python ./scripts/record_ai_bank.py notes data/ai/bank_build/notes_layer1.json --model <model id>`
2. Layer 2 (use): write `data/ai/bank_build/notes_layer2.json` for the subset where use changes the reading, then
   the same command with that file.

Fix-and-rerun on problems. Delete the pending and patch files once recorded.

## Step 8 — Report

Tell the user: what was rebuilt or skipped, the gate output, counts (passed, needs human review), notes count, and
what is left to do. List any subcategory that needs human review with its reason (read it from the bank file only
for those).
