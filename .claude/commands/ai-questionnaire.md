# /ai-questionnaire — NIST AI RMF 1.0 draft questions for an engagement

Argument: the run folder (`runs/<Org>_<date>`, created by `/generate-questions` or `scripts/intake.py`). Reads its
`ai_usage.json` (how the org uses AI); writes `ai_scope.json` and `ai_questions_draft_<bank>.json` per bank. It does not
review the draft or write the workbook: `/assess-questionnaire` does both. Needs the AI RMF banks
(`/build-ai-bank`). Scripts decide everything here; there is no agent judgement in this command.

Tools: Bash, Read. Working directory: repo root. Say little: the script's summary line, and anything you need from the
user.

## 1 — Run folder
If no run folder was given: `ls runs/` and ask which one. It must contain `ai_usage.json`; if not, tell the user to run
`/generate-questions` (or `scripts/intake.py`) first and stop.

## 2 — Check the banks
`.venv/bin/python ./scripts/check_freshness.py --ai-bank`

Read only the lines this profile needs: `bank producer` for role producer or both, `bank consumer` for role consumer or
both (`none` and `unsure` use consumer), and `pilot`. Ignore the exit code and the other stages.
- A needed bank `missing`, or `pilot` not accepted: tell the user to run `/build-ai-bank` (pilot first) and stop.
- A needed bank `stale` or `incomplete`: say so and ask whether to continue anyway.

## 3 — Scope and questions
`.venv/bin/python ./scripts/build_ai_questions.py <run_dir>`

Works out the question type per subcategory from the profile (policy in `data/ai/scope_rules.json`: do not read it or
re-apply it by hand), picks bank candidates and writes `ai_scope.json`, `ai_questions_draft_<bank>.json` and a snapshot
`ai_question_bank_used_<bank>.json`. It lists subcategories with no fitting bank candidate; they are dropped, not
replaced with a generic question. Exit 1 lists what is wrong with `ai_usage.json`: tell the user, fix it with them
(re-run `scripts/intake.py` for a new intake) and run again.

## Done
Tell the user: the run folder, the counts by type per bank and the number of subcategories dropped. Next:
`/assess-questionnaire <run_dir>`.
