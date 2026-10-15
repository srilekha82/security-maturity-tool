# /build-csf-bank — build a domain's CSF 2.0 question bank from the CSET SQL

Argument: the domain (`finance`, `healthcare`, `manufacturing_ot`, `saas_cloud`, `consulting`, `other`) or `all`.
Builds `data/csf/banks/question_bank_<domain>.json` from the CSET SQL migration files, several candidates per
subcategory. Scripts do everything the CSET schema decides; an agent step (Step 3) judges only what the schema cannot
(domain of generic questions, rewording statement-only practices as questions, loose subcategory mappings).
`build_questions.py` later picks the right number per engagement. Do not re-implement any parsing or routing inline.
The banks are shared across clients: build or refresh one when it is missing or CSET changed, not per engagement.

Tools: Bash, Read, Write. Working directory: repo root. Say little: the script summary lines and the final report.

## 1 — Domain and CSET path
If no domain was given: `.venv/bin/python ./scripts/intake.py menu domain`, ask the user to pick a number (or `all`),
and use that domain's value. The CSET repo is `~/workstuff/cset` unless the user says otherwise (expand `~`).

## 2 — Extract candidates (deterministic)
`.venv/bin/python ./scripts/extract_cset_candidates.py --cset-path <cset_path>`

Pulls the CSET repo, replays the SQL (reference INSERT minus DELETE, question INSERT / UPDATE / DELETE) and writes
`data/csf/bank_build/cset_candidates.json`. Same commit as stored: prints "up to date" and exits. Commit moved but no
`.sql` changed: only patches the stored commit. Otherwise it re-extracts. If it reports "could not update CSET repo",
relay the message and stop. Add `--force` only if the user asks.

## 3 — Build the bank (deterministic routing)
`.venv/bin/python ./scripts/build_question_bank.py --domain <domain>`

- **Exit 0**: bank written. Go to Step 5.
- **Exit 2**: some candidates need a judgement. It wrote `data/csf/bank_build/pending_judgements_<domain>.json` and no
  bank. Go to Step 4.

## 4 — Judge the pending questions (agent)
`prompts/question_bank_judge.md` is your complete instruction for this step.

1. Read `data/csf/bank_build/pending_judgements_<domain>.json`; work through `items` in batches of about 25.
2. For each item write only the verdicts it `needs`, in the format the prompt defines, all into
   `data/csf/bank_build/verdicts_<domain>.json`.
3. Save them (your model id):
   ```bash
   .venv/bin/python ./scripts/record_judgements.py data/csf/bank_build/verdicts_<domain>.json \
       --pending data/csf/bank_build/pending_judgements_<domain>.json --model <model id>
   ```
   If it lists problems, fix those entries and run it again; nothing is saved until it passes.
4. Run Step 3 again: it should now exit 0.

Verdicts are stored in `data/csf/bank_build/cset_judgements.json` and reused by every domain and every later build; they
are redone only for questions CSET has changed. Each recording also writes a write-once record to
`data/csf/bank_build/judgement_log/`. Delete `verdicts_<domain>.json` once recorded.

## 5 — Report
Relay the script output: subcategories with candidates, empty ones, the routing counts (accept/schema, accept/agent,
reject/schema, reject/agent), and how many questions the agent judged. Do not re-read the bank file unless the user asks.
