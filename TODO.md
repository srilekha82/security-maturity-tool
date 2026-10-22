# TODO (last updated 2026-10-21)

State: the AI bank pilot has been run and recorded but NOT accepted (`AI_RMF_Pilot_Decisions.md`). The AI RMF model was
redesigned: AI areas (usage and components) -> attack areas -> AI RMF function -> subcategory, in `AI_RMF_Mapping_Sheet_Design.md`. That note is
the starting point; it supersedes steps 3 and 4 of "finish the AI bank pilot" below.

## Build the AI RMF mapping (steps of the design note)
0. ~~Write the model down (design note, sector rule in `DESIGN_RULES.md`, this TODO).~~ Done 2026-10-21.
1. ~~AI areas sheet `data/ai/authoring/ai_areas.xlsx` (the decision; 14 areas, kind, applies to, impact) ->
   `data/ai/ai_areas.json` via `scripts/sheet_io.py`; intake asks "How do you use AI?" and "What does your AI include?"
   and writes the client's `ai_areas` (automatic ones in `scope_rules.json` `ai_area_rules`), plus the old fields derived
   for the current filter.~~ Done 2026-10-21. Open for the producer: ask "pure or modified" (only if base-model
   questions are wanted) and "is the model given to others?" (release questions only then).
2. Draft the mapping. BUILT 2026-10-22, not run yet: `prepare_ai_bank.py mapping --area ID`, the drafter and evaluator
   prompts, `record_ai_bank.py mapping` (all rules below enforced), `data/ai/mapping_rules.json`, the "Mapping" section
   of `/build-ai-bank`. Review the DRAFT `area_cis` (candidate CIS controls per area) and `org_wide` lists in
   `mapping_rules.json`, then run the pilot on one area. Add the `mapping` freshness stage in step 3, when the mapping
   replaces applicability. Original plan: a script crosses the AI areas with the four functions and prepares a compact input per area;
   drafter and evaluator prompts; recording script (ids, safeguards, impacts, coverage of all 72, and the required
   checks of the design note: inventory, audit trail, incident response, reliability). Pilot on one area
   first (MCP / tools) to check quality and tokens.
3. Review and accept: `sheet_io.py export` / `import` for the mapping, `decided_by: human` on changed rows, accept gate.
4. Rewire question generation to mapping rows: `prepare_ai_bank.py batch`, generator prompt, `build_ai_questions.py`
   (the client's `ai_areas` from the intake; gap rule from the CIS -> CSF mapping per row). Retire the old profile
   fields (`legacy_profile`), the modifiers and `question_categories.json` here.
5. Severity: the standard criticality question (USD under 100k / 100k-500k / over 500k; reputation; safety) and the
   priority rules (domain floor, process criticality, data classification) for the Stage 2 writer.
6. Re-run the pilot (same 6 subcategories), accept, then the full producer and consumer banks.
7. Tests and docs; fix the code review findings listed at the end of the design note (two are reproduced bugs).

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
