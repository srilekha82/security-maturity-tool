# AI RMF build — extra notes from the CSF rebuild

Separate from `AI_RMF_QuestionBank_Decisions.md` (which is not changed by this file). Read both, plus `README.md`, at the start of the AI RMF session.

## Reuse of the audit trail (built once)
- Every new script calls `scripts/audit.py`: `ev = begin(log_path, "<script>", args)` at the start, then `ev.finish(...)`, `ev.fail(msg)` or `ev.pending(msg)`. It appends one line to that folder's `audit.jsonl`; a crash still leaves an `incomplete` line.
- Every agent step is handed in through `record_judgements.py` (validate, store or merge, then log). Do not invent a separate logging scheme.
- Suggested log locations for the AI RMF bank build: `data/ai/bank_build/audit.jsonl` and `data/ai/bank_build/judgement_log/`.

## `record_judgements.py` needs generalising for the AI RMF bank
Its bank mode (`record_judgements.py <verdicts.json>`) is CSET-specific:
- it reads `cset_candidates.json` and checks verdicts against CSET question IDs and CSF subcategories;
- it stores verdicts in `data/csf/bank_build/cset_judgements.json`, keyed by question and hashed on question text;
- it imports `DOMAINS`, `REWRITE_FLAGS` and `text_hash` from `build_question_bank.py`.

The AI RMF bank has different units (subcategory + role + technology rung + usage tags + topic), so it needs its own store and its own validation of verdicts.

**Decided (Oct 2026):** give the AI RMF bank its own small recording script, `record_ai_bank.py`, that calls `audit.py` and writes the same kind of write-once record, sharing the generic helpers (write-once storage, hashing) with `record_judgements.py`. Not an AI RMF mode inside `record_judgements.py`, to avoid two validation schemas in one CSET-specific file.

Keep the same contract: the agent hands in a file, the script validates it and rejects the whole file if anything is wrong, and nothing is stored until it passes.

The assessor-patch mode (`record_judgements.py log --base --patch`) is generic and can be reused as is for any agent step that returns changed entries.

## Not yet covered by the audit trail
- The AI overlay in `/generate-questions` (the agent writes `questions_final.json` directly). It goes away when the AI RMF track replaces it.
- Stage 2 (answers, XLS writer) and Stage 3 (HTML skills) are not built or are outside this repo. When built, their scripts use `audit.py` and their agent steps use `record_judgements.py log`.

## Commands: what changes
No change to `/build-question-bank` or `/assess-questionnaire`. In `/generate-questionnaire` and `/generate-questions` only the AI-related parts change: the old AI scope intake is replaced by the AI-in-use gate and usage profile, and the OWASP-based AI overlay (Phase 3 Step A) is removed. This is done in the new session, not deferred. Two new commands (`/build-ai-rmf-bank`, `/generate-ai-questions`) and new prompts are planned. Details in the "Commands and prompts plan" section of `AI_RMF_QuestionBank_Decisions.md`.

## Where the other decisions live
`AI_RMF_QuestionBank_Decisions.md` is the source of truth for the AI RMF track (scoping dimensions, banks, mappings, build steps, orchestration choice). The bank build uses plain subagents in this repo; `gen-eval-loop` is for the Stage 2 answer session.
