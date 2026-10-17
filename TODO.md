# TODO (last updated 2026-10-17)

State: the commands and scripts were restructured this session (all 42 tests pass). The AI bank pilot has been run and recorded
but NOT accepted. Full details of the pilot, with the judgement calls, are in `AI_RMF_Pilot_Decisions.md`.

## First, next session: build the AI RMF mapping sheet (supersedes steps 3 and 4 below)
Design agreed on 2026-10-17 in `AI_RMF_Mapping_Sheet_Design.md`: replace the applicability judge and CIS linker as
decision makers with a mapping (check area x AI RMF subcategory x CIS safeguards x impact), drafted by an agent,
evaluated by a fresh agent, recorded by a script, exported to a spreadsheet for human review, imported back, accepted.
1. Settle the open points: training data as its own area; fairness split out of "Testing".
2. Areas sheet (11 areas, human) in `data/ai/authoring/`.
3. Drafter and evaluator prompts; recording, export and import scripts; accept gate; tests.
4. Switch `prepare_ai_bank.py batch`, `build_ai_questions.py` and the generator input to mapping rows; re-run the pilot.
5. Code review findings (two reproduced bugs in `parse_soa.py` and `extract_cset_candidates.py`) are listed at the end
   of the design note.

## Next session: finish the AI bank pilot
1. **Review the 6 pilot entries** in `data/ai/banks/question_bank_ai_rmf_producer.json` (GOVERN 6.1) and
   `question_bank_ai_rmf_consumer.json` (MAP 1.1, MEASURE 3.3, MANAGE 3.1, MAP 2.2, MAP 3.5). Section 4 of
   `AI_RMF_Pilot_Decisions.md` lists what failed and which 3 are flagged `needs_human_review` (MAP 1.1 Q3, MANAGE 3.1 Q4, MAP 2.2 Q5).
2. **Edit `prompts/ai_rmf_question_generator.md`** (the evaluator prompt needs no change):
   - line 30 / 33 (`scope_tags`, `modifiers`): tag a usage context only if the question makes no sense without it, otherwise `[]`
   - line 28 (`capability`): the rung must be at least the highest rung of any cited safeguard and of what the question asks (tool calling is `mcp`, not `rag`)
   - line 18 (one thing per question): at most one "who / where recorded" and one "how often"; no list of subjects in one question
   - line 27 (`cis_refs`): cite a safeguard only if it supports this question; when in doubt `[]`
3. **Decide the MAP 2.2 access mapping** (`AI_RMF_Pilot_Decisions.md` section 1, item 2). The evaluator said `ai_access` does not fit a
   "where are connections recorded" question. Either re-tag it as governance, or move the `ai_access_*` mapping to a better
   subcategory (then redo the applicability pass, `/build-ai-bank` step 3).
4. **Re-run the pilot** with `/build-ai-bank` (same 6 subcategories is fine; the work files in `data/ai/bank_build/work/` can be
   deleted first). Editing a prompt after acceptance makes the acceptance stale, so edit first, accept last.
5. **Accept** only when happy: `.venv/bin/python ./scripts/ai_pilot.py accept --note "<what you decided>"`.

## Then: full builds
6. `/build-ai-bank` full run (both banks, `--missing`, one AI RMF category per batch; cheaper per subcategory than the pilot,
   which cost about 0.85M tokens for 6 subcategories). Then Step 7, the CSF AI impact notes.
7. `/build-csf-bank all` (only `finance` exists today).
8. Run `/generate-questions` end to end on a test client. The restructured commands have not been run as a whole in a live session yet.

## Parked, no rush
- `validate_questions.py`: move the mechanical assessor checks (truncated text, duplicates, blank evidence, GV must be
  `full_discovery`, wrong cert named, missing LOW flag) out of the two assessor prompts into a script.
- Update the decision docs (`AI_RMF_*.md`, `AI_Assessment_Pipeline_Design.md`) to the new command and file names once things are final.
- Unit tests for `compute_scope.py` and `build_questions.py` (checked by hand so far, not in the test suite).
- `.claude/settings.local.json` holds two leftover permissions from an older session's scratchpad: remove them.
- Kept on purpose: `max_questions` stays in both `scope_rules.json` files; the CSF fallback question (38 finance subcategories)
  and auto-building missing banks inside `/generate-questions`.
- Delete the pilot work files (`data/ai/bank_build/work/`, `batch_*.json`) after the review.
