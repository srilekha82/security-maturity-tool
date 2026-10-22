# TODO (last updated 2026-10-22)

State: the AI RMF model was redesigned (2026-10-16 to 2026-10-22): AI areas (how AI is used and what it is made of) ->
attack areas -> AI RMF function -> subcategory. `AI_RMF_Mapping_Sheet_Design.md` is the starting point for every
session. The old AI bank pilot (`archive/AI_RMF_Pilot_Decisions.md`) was never accepted. Its outputs (applicability.json,
airmf_to_cis.json, the two pilot banks, the work and batch files) were removed on 2026-10-22, so `/ai-questionnaire` has no
AI RMF bank until step 6. The audit trail (`data/ai/bank_build/audit.jsonl`, `judgement_log/`) is kept.

## Start here next session
All open decisions are settled (2026-10-22): `area_cis` kept as drafted, `org_wide` = GOVERN 3.1, 4.1, 4.2, 4.3, 5.2,
MANAGE 1.2, 1.3; `always_cis_controls` 1, 2, 8, 17 named and checked against the guides; no row count (content
decides, the evaluator fails padding); the producer area is `model_development` ("Model development and release");
criticality bands in USD (under 100k / 100k-500k / over 500k).
1. Run the mapping pilot on ONE area (planned: `mcp_tools`) with `/build-ai-bank`, section "Mapping": prepare, drafter,
   evaluator, one revision turn, record. About 4 agent runs of ~25k tokens input each. Ask the user before running.
2. Review the recorded rows with the user (function, subcategory, safeguards, impact, why, evaluator failures,
   subcategories still unreached), tune the two mapping prompts if needed, then draft the other 13 areas one at a time.

## Build the AI RMF mapping (steps of the design note)
0. ~~Write the model down.~~ Done 2026-10-21.
1. ~~AI areas and intake.~~ Done 2026-10-22. `data/ai/authoring/ai_areas.xlsx` (the decision: 14 areas, kind, applies
   to, impact) -> `data/ai/ai_areas.json` via `scripts/sheet_io.py`. The intake asks AI in use; "Do you build AI, use AI,
   or both?" (for producer or both: built on an existing model? given to others?); "How do you use AI?"; "What does
   your AI include?". It writes `role`, `producer`, `ai_areas` (automatic ones in `scope_rules.json` `ai_area_rules`) and
   the old fields derived for the current filter.
2. Draft the mapping. Built 2026-10-22, not run: `prepare_ai_bank.py mapping --area ID`, `prompts/ai_rmf_mapping_drafter.md`,
   `prompts/ai_rmf_mapping_evaluator.md`, `record_ai_bank.py mapping` (rejects a draft that breaks
   `data/ai/mapping_rules.json`: subcategory of the right function, the area's candidate safeguards and impacts, every
   function covered, the required checks: inventory, audit trail with a CIS control 8 safeguard, incident response,
   reliability). Run it: "Start here" above.
3. Review and accept the mapping: a `mapping` entry in `data/common/sheet_specs.json` so `sheet_io.py` exports it to a
   spreadsheet and imports the person's edits back (`decided_by: human`); an accept gate like `ai_pilot.py accept`; a
   `mapping` stage in `check_freshness.py` (missing, incomplete, stale, subcategories unreached).
4. Rewire question generation to mapping rows: `prepare_ai_bank.py batch` from mapping rows, generator prompt (questions
   per AI area x subcategory, the row's safeguards as evidence), `build_ai_questions.py` (rows from the client's
   `ai_areas`; base-model questions only when `producer.built_on_existing_model`; release questions only when
   `producer.given_to_others`; gap rule per row from the CIS -> CSF mapping; up to 6 questions per subcategory). Retire `legacy_profile`, the modifiers,
   `question_categories.json` and the `AI_APPLICABILITY` path (the applicability and CIS-linker prompts, modes and
   freshness stages were already removed on 2026-10-22). Carry over the generator prompt fixes from
   the old pilot (`archive/AI_RMF_Pilot_Decisions.md` section 4): one subject per question; cite a safeguard only if it supports
   the question.
5. Severity: the standard criticality question (USD under 100k / 100k-500k / over 500k; reputation; safety) and the
   priority rules (domain floor for healthcare and manufacturing / OT, process criticality, data classification) for
   the Stage 2 writer.
6. Pilot the question banks on a few mapping rows, accept (`ai_pilot.py accept`), then the full producer and consumer
   banks, then the CSF AI impact notes.
7. Tests and docs; fix the code review findings listed at the end of the design note (two are reproduced bugs:
   `parse_soa.py` numeric ids, `extract_cset_candidates.py` replay order).

## Then
- `/build-csf-bank all` (only `finance` exists today).
- Run `/generate-questions` end to end on a test client. The restructured commands have not been run as a whole in a live
  session yet.

## Parked, no rush
- `validate_questions.py`: move the mechanical assessor checks (truncated text, duplicates, blank evidence, GV must be
  `full_discovery`, wrong cert named, missing LOW flag) out of the two assessor prompts into a script.
- Update `AI_Assessment_Pipeline_Design.md` where the new model supersedes it, once the mapping is accepted (the three
  first-design AI RMF notes are in `archive/`).
- Unit tests for `compute_scope.py` and `build_questions.py` (checked by hand so far, not in the test suite).
- `.claude/settings.local.json` holds two leftover permissions from an older session's scratchpad: remove them.
- Kept on purpose: `max_questions` stays in both `scope_rules.json` files; the CSF fallback question (38 finance subcategories)
  and auto-building missing banks inside `/generate-questions`.
