# /ai-questionnaire — NIST AI RMF 1.0 draft questions for an engagement

Argument: the run folder (`runs/<Org>_<date>`, created by `/generate-questions` or `scripts/intake.py`). Reads its
`ai_usage.json` (how the org uses AI); writes `ai_scope.json` and `ai_questions_draft_<bank>.json` for the two banks
(foundation, areas). It does not
review the draft or write the workbook: `/assess-questionnaire` does both. Needs the AI RMF banks
(`/build-ai-bank`). Scripts decide everything here; there is no agent judgement in this command.

Tools: Bash, Read. Working directory: repo root. Say little: the script's summary line, and anything you need from the
user.

## 1 — Run folder
If no run folder was given: `ls runs/` and ask which one. It must contain `ai_usage.json`; if not, tell the user to run
`/generate-questions` (or `scripts/intake.py`) first and stop.

## 2 — Check the banks
`.venv/bin/python ./scripts/check_freshness.py --ai-bank`

Read only `bank foundation`, `bank areas` and `pilot` (every client needs both banks). Ignore the exit code and the
other stages.
- A needed bank `missing`, or `pilot` not accepted: tell the user to run `/build-ai-bank` (pilot first) and stop.
- A needed bank `stale` or `incomplete`: say so and ask whether to continue anyway.

## 3 — Scope and questions
`.venv/bin/python ./scripts/build_ai_questions.py <run_dir>`

Picks the client's questions from the banks by their role, producer flags and AI areas (policy in
`data/ai/scope_rules.json`: do not read it or re-apply it by hand) and writes `ai_scope.json`,
`ai_questions_draft_<bank>.json` and a snapshot `ai_question_bank_used_<bank>.json`. A question shared by several of
the client's areas carries a note naming them. Subcategories with no question for this client are left out (they do
not apply). With a CSF assessment or ISO 27001 it prints that the per-row gap rule is not built yet: pass that on. Exit 1 lists what is wrong with `ai_usage.json`: tell the user, fix it with them
(re-run `scripts/intake.py` for a new intake) and run again.

## Done
Tell the user: the run folder and the counts per bank (subcategories, questions). Next:
`/assess-questionnaire <run_dir>`.
