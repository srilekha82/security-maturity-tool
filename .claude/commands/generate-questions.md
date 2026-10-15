# /generate-questions — one questionnaire (CSF sheet + AI RMF sheet) for a client

The whole pipeline from one intake. This command does only the shared steps (intake, freshness, rebuilds) and then runs
the other commands in order, each of which also works on its own for a run folder:

  intake → freshness → `/csf-questionnaire` → `/ai-questionnaire` → `/assess-questionnaire` (both, fresh reviewers)

The client sees one `questionnaire.xlsx` with two sheets; the two tracks are internal. Banks are shared across clients
and are built by `/build-csf-bank` and `/build-ai-bank`.

Tools: Bash, Read, Skill. Working directory: repo root. Say little: the script summary lines, and anything you need
from the user.

## 1 — Intake (numbers, asked once)
`.venv/bin/python ./scripts/intake.py menu` prints every numbered menu. Ask the user the organisation name (free text),
then each menu one at a time, in order, and take the number(s) typed. Ask role, rung, usage contexts and modifiers only
if AI in use is option 2 (the menu says so). If the user asks what an option means, answer from the `definitions` block
of `data/ai/question_categories.json`. Then:

```bash
.venv/bin/python ./scripts/intake.py write --org "<name>" --domain N --certs "N N" --ai-in-use N \
    [--role N --rung N --usage-contexts "N N" --modifiers "N N"] --csf-assessment-done N --iso42001-held N
```

It maps the numbers to values, rejects anything not on a menu (exit 1: ask the user again for those questions only; if it
says the run folder already has an intake, ask whether to replace it and add `--replace`, knowing the old drafts are then
stale) and
prints the run folder (`runs/<Org>_<date>`) with `intake.json` and `ai_usage.json` in it. Use that folder for every
later step; nothing else needs the answers repeated.

## 2 — Freshness (CSF and AI together)
`.venv/bin/python ./scripts/check_freshness.py --all --run <run_dir>`

It prints the reference data table, one line for the CSF bank of this domain, one line per AI RMF stage and any `note:`
lines (for example when `git fetch` on the CSET clone failed: pass that on, it means the CSF bank was compared with the
local CSET commit only). It reports facts and decides nothing; exit 1 only means something needs work. Act on these
lines only; ignore the AI `crosswalk`, `notes` and `applicability` lines and any bank the profile does not need.
Say what you are about to rebuild before you start.

- **Reference data** flagged stale or seed: ask the user whether to refresh it first. NIST blocks automated downloads, so
  they download it: go to https://www.nist.gov/cyberframework/csf-20-informative-references, click "Download English
  (xlsx)", save as `data/csf/source/csf2.xlsx`, and tell you. Then run
  `.venv/bin/python ./scripts/parse_crosswalk.py --output ./data`; it also records the refresh in `data/metadata.json`.
  If they decline, note it and continue.
- **CSF bank** for this domain: `missing` → run `/build-csf-bank <domain>` without asking. `stale` → ask whether to
  rebuild; if yes, the same.
- **AI RMF banks**. Needed: consumer for role consumer, `none` and `unsure`; producer and consumer for role both;
  producer for role producer. Read those `bank ...` lines and the `pilot` line:
  - bank `missing` or `incomplete`, `pilot` accepted: run `/build-ai-bank` (full run, `--missing`) without asking.
  - bank `stale`, `pilot` accepted: ask whether to rebuild; if yes, the same.
  - `pilot` `missing` or `stale`: do not build. Tell the user the AI RMF banks need `/build-ai-bank` with a pilot review
    first, and continue with the CSF track only; the AI sheet is added later by `/ai-questionnaire` then
    `/assess-questionnaire`.

After any rebuild run the check once more to confirm.

## 3 — CSF questions
Run `/csf-questionnaire <run_dir>` (Skill tool). It has its own STOP for the SoA question when ISO 27001 is held: wait for
the user's answer.

## 4 — AI RMF questions
Otherwise run `/ai-questionnaire <run_dir>`.

## 5 — Independent review and workbook
Run `/assess-questionnaire <run_dir>`. It reviews every draft in the run folder with fresh reviewers and writes the
workbook.

## Done
Tell the user: the run folder, what was rebuilt in step 2 and what was already current, the files written
(`intake.json`, `ai_usage.json`, `csf_scope.json`, `csf_questions_draft.json`, `csf_questions_assessed.json`, and per bank
`ai_scope.json`, `ai_questions_draft_<bank>.json`, `ai_questions_assessed_<bank>.json`, `questionnaire.xlsx`,
`judgement_log/`), and the assessor's report from step 5. If the AI sheet is missing, say so plainly and what to run.
