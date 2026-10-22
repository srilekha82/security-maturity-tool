# /build-ai-bank — build the AI RMF 1.0 producer and consumer question banks

Builds `data/ai/banks/question_bank_ai_rmf_producer.json` and `question_bank_ai_rmf_consumer.json` from the AI RMF
Playbook and the three CIS AI companion guides, then the CSF AI impact notes (`data/csf/ai_impact_notes.json`).
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

One line per stage (parse, applicability, crosswalk, each bank, notes): `current`, `missing`, `stale` or `incomplete`. A
stage is current only if it was built from the exact source files on disk (each output records the SHA-256 of its inputs).

- Exit 0: everything is current and complete. Tell the user and stop, unless they ask to force a rebuild.
- Exit 1 with `sources: missing ...`: point to `data/ai/source/README.md` and stop.
- Exit 1 otherwise: do only the stages that are not current, in the order below; a stale stage makes the ones after it
  stale too. Tell the user which stages you will run.

## Step 2 — Parse the sources

```bash
.venv/bin/python ./scripts/parse_ai_rmf_sources.py
```

Writes `data/ai/ai_rmf_core.json` (72 subcategories with Playbook suggested actions) and
`data/ai/cis_ai_safeguards.json` (the safeguards of the three guides). It fails, writing nothing, if a count is off.
Agents read these files, never the PDFs.

> **Steps 3, 4 and 5 below are the old flow, being replaced** (`AI_RMF_Mapping_Sheet_Design.md`, `TODO.md`). Their
> outputs (applicability.json, airmf_to_cis.json, the pilot banks and work files) were removed on 2026-10-22. Do not
> run Steps 3 to 5; the freshness check will report them missing until the new flow replaces them. Use the
> "Mapping" section, and only when the user asks.

## Step 3 — Applicability pass (old; replaced by the Mapping section)

Decides, per subcategory and per bank, which question categories it can produce questions for.

```bash
.venv/bin/python ./scripts/prepare_ai_bank.py applicability
```

Read `prompts/ai_rmf_applicability_judge.md` (your complete instruction) and
`data/ai/bank_build/applicability_pending.json`. Write the verdicts to
`data/ai/bank_build/applicability_verdicts.json`, then:

```bash
.venv/bin/python ./scripts/record_ai_bank.py applicability data/ai/bank_build/applicability_verdicts.json --model <model id>
```

If it lists problems, fix those entries and run it again; nothing is stored until it passes. Delete the pending and
verdicts files once recorded. Show the user the producer / consumer counts it prints.

## Step 4 — AI RMF → CIS link (old; replaced by the Mapping section)

```bash
.venv/bin/python ./scripts/prepare_ai_bank.py crosswalk
```

Read `prompts/ai_rmf_cis_linker.md` and `data/ai/bank_build/crosswalk_pending.json`. Write
`data/ai/bank_build/crosswalk_verdicts.json`, then:

```bash
.venv/bin/python ./scripts/record_ai_bank.py crosswalk data/ai/bank_build/crosswalk_verdicts.json --model <model id>
```

Same fix-and-rerun loop. Delete the pending and verdicts files once recorded.

## Mapping (new; will replace Steps 3 and 4 once accepted, see `AI_RMF_Mapping_Sheet_Design.md`)

Maps each AI area (`data/ai/ai_areas.json`, decided by the user in `data/ai/authoring/ai_areas.xlsx`) to AI RMF
subcategories per function, with the CIS safeguards that prove them. Run only when the user asks for it, one AI area at a
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
   `prompts/ai_rmf_mapping_evaluator.md` with the input and the draft; write the failures to
   `work/mapping_<area>_eval1.json`.
4. If there are failures: a fresh drafter revises (inputs: the input file, `draft1`, `eval1`; output the complete
   `work/mapping_<area>_draft2.json`), and a fresh evaluator checks it into `work/mapping_<area>_eval2.json`. Two turns at
   most.
5. Record the last draft with the last evaluation (rows still failing are stored as `needs_human_review`):
   ```bash
   .venv/bin/python ./scripts/record_ai_bank.py mapping data/ai/bank_build/work/mapping_<area>_draft<N>.json \
       --review data/ai/bank_build/work/mapping_<area>_eval<N>.json --model <drafter model id> --session "evaluator=<model id>"
   ```
   If it lists problems (ids, candidates, impacts, a missing function or required check), send them back to the drafter
   and repeat; nothing is stored until it passes. It prints how many areas are recorded and how many AI RMF
   subcategories are not reached yet.

After the pilot area: stop. Show the user the recorded rows (function, subcategory, safeguards, impact, why), what the
evaluator failed, the subcategories still unreached, and token use if you can see it. The user reviews before any other
area is drafted.

## Step 5 — Generate and evaluate (subagents) (old input; rewired to mapping rows in TODO step 4)

Ask the user: **pilot** (6 subcategories, per-subcategory loops, then stop for review) or **full** (all applicable
subcategories, one AI RMF category per batch).

### Pilot
Propose 6 subcategories from `data/ai/applicability.json` and `data/ai/crosswalks/airmf_to_cis.json` that span the range
and show them to the user before running (wait for confirmation):
- one GOVERN subcategory, producer bank
- one MAP, consumer bank, internal usage
- one MEASURE, consumer, customer-facing
- one MANAGE, consumer, third-party embedded
- one whose mapped safeguards are MCP-heavy (capability `mcp`)
- one whose mapped safeguards are agents-heavy (capability `agentic`)

### The loop (per batch: one subcategory in the pilot, one AI RMF category such as `GOVERN 1` in a full run)
Work files go under `data/ai/bank_build/work/` (create it; delete the files once the batch is recorded).

1. Prepare the batch input for the bank:
   ```bash
   .venv/bin/python ./scripts/prepare_ai_bank.py batch <producer|consumer> --ids "<ID>" ...    # pilot
   .venv/bin/python ./scripts/prepare_ai_bank.py batch <producer|consumer> --category "GOVERN 1"  # full
   ```
   It writes `data/ai/bank_build/batch_<bank>_<tag>.json`.
2. **Generator** (a fresh subagent via the Agent tool): tell it to follow `prompts/ai_rmf_question_generator.md` with the
   batch file as input and to write its output to `work/<tag>_gen1.json`. Pass paths, not content.
3. **Evaluator** (another fresh subagent, a cheaper model such as `sonnet`): tell it to follow
   `prompts/ai_rmf_question_evaluator.md` with the batch file and `work/<tag>_gen1.json`, and to write the failures to
   `work/<tag>_eval1.json`. It must not see the generator's prompt.
4. If `eval1` lists failures: a fresh generator subagent revises only those subcategories (inputs: the batch file,
   `gen1`, `eval1`; output `work/<tag>_gen2.json` with the COMPLETE candidate list of each failing subcategory), then a
   fresh evaluator checks `gen2` into `work/<tag>_eval2.json`. Two turns at most.
5. Assemble and record (the script marks a subcategory `needs_human_review` if it still fails after turn 2):
   ```bash
   .venv/bin/python ./scripts/record_ai_bank.py assemble --gen1 work/... --eval1 work/... [--gen2 ... --eval2 ...] --out data/ai/bank_build/work/<tag>_record.json
   .venv/bin/python ./scripts/record_ai_bank.py candidates <bank> data/ai/bank_build/work/<tag>_record.json \
       --model <generator model id> --session "evaluator=<evaluator model id>"
   ```
   If `candidates` lists problems, send those subcategories back to the generator and repeat; nothing is stored until it
   passes.

### After the pilot: stop
Do not continue to a full run on your own. Report to the user: how many subcategories passed on turn 1 and turn 2, how
many need human review, and token use per batch if you can see it. Show 2 or 3 PASSING questions as well as the
failures, so passes get reviewed too. Run the evaluator once on a file with 3 deliberately weak, checkbox-style
questions added to a copy of one subcategory (never recorded) and report whether it caught them. The user tunes the
generator and evaluator prompts from this, then runs `/build-ai-bank` again for the full run.

When the user says the pilot is good, record it:
```bash
.venv/bin/python ./scripts/ai_pilot.py accept --note "<what the user said>"
```
The acceptance is tied to the current generator and evaluator prompts. From then on `/generate-questions` rebuilds a
missing or incomplete AI bank on its own, like a CSF bank. If either prompt is edited later the acceptance goes stale
and a new pilot is needed before the next rebuild.

### Full run
Use `prepare_ai_bank.py batch <bank> --category "<function> <n>" --missing` so each batch holds only subcategories not yet
recorded, and run the loop per category. At the end show the user a random sample of 5 passing subcategories to spot-check.

## Step 6 — Check completeness (after both banks have every applicable subcategory)

```bash
.venv/bin/python ./scripts/check_freshness.py --ai-bank
```

Both banks must show `current`. `incomplete` means applicable subcategories are still missing from a bank: go back to
Step 5 with `--missing`.

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
