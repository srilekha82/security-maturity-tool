# /assess-questionnaire — independent review of the drafts, then the workbook

Argument: the run folder (`runs/<Org>_<date>`). Reviews every draft in it, CSF and AI RMF, each by its own fresh
subagent, merges what the reviewers changed and writes the sheets of `questionnaire.xlsx`. The reviewers have not seen
how the questions were made: they get the draft file and their prompt, nothing else.

Tools: Bash, Read, Agent. Working directory: repo root. Say little: the script summary lines, and the final report.

## 1 — Find the drafts
If no run folder was given: `ls runs/` and ask which one. Then `ls <run_dir>`. The drafts present decide the work:

| Draft | Reviewer prompt | Patch file the reviewer writes | Assessed file (written by the script) | Log step |
|---|---|---|---|---|
| `csf_questions_draft.json` (CSF) | `prompts/questionnaire_assessor.md` | `csf_questions_assessed_patch.json` | `csf_questions_assessed.json` | `assessor` |
| `ai_questions_draft_<bank>.json` (AI RMF, one per bank) | `prompts/ai_rmf_questionnaire_assessor.md` | `ai_questions_assessed_patch_<bank>.json` | `ai_questions_assessed_<bank>.json` | `ai_assessor_<bank>` |

No draft at all: tell the user to run `/csf-questionnaire` and / or `/ai-questionnaire` first, and stop.

## 2 — Review (one fresh subagent per draft, all started together)
Start the subagents in ONE message (Agent tool), one per draft. Brief each with paths only:

> Follow `<reviewer prompt>` exactly. Your only input is `<run_dir>/<draft file>`; do not read any other file under
> `runs/` or `data/`, and do not ask the user anything. Write only the entries you changed, each complete, to
> `<run_dir>/<patch file>` (`[]` if you changed none). Finish with your model id.

## 3 — Merge and log
For each draft, with the reviewer's model id (a script validates the patch and writes the whole merged file):

```bash
.venv/bin/python ./scripts/record_judgements.py log <run_dir> --step <log step> --base <draft file> \
    --patch <patch file> --output <assessed file> --inputs <draft file> --prompt <reviewer prompt> --model <model id>
```

It prints how many entries changed. If it exits 1 it lists what is wrong with the patch: have the same subagent fix
those entries (SendMessage) and run it again. Never write an assessed file yourself.

## 4 — Write the workbook
Each framework writes only its own sheet, so the order does not matter and a re-run never loses the other sheet:

```bash
.venv/bin/python ./scripts/write_questionnaire.py <run_dir>/csf_questions_assessed.json <run_dir>/questionnaire.xlsx
.venv/bin/python ./scripts/write_questionnaire.py <run_dir>/ai_questions_assessed_<bank>.json [<the other bank's file>] \
    <run_dir>/questionnaire.xlsx --framework ai
```

## Done
Tell the user, in a few lines: the run folder, the sheets written, question counts by type per sheet, the number of
entries the reviewers changed (one line of key issues each), and the number of LOW-confidence entries
(`grep -c '"confidence_flag": "LOW' <assessed file>`). Next: share `questionnaire.xlsx` with control owners; the answers
filled into its sheets go to Stage 2 (two profile XLS files, CSF and AI RMF).
