# TODO (last updated 2026-10-26)

State: the AI RMF model was redesigned (2026-10-16 to 2026-10-22): AI areas (how AI is used and what it is made of) ->
attack areas -> AI RMF function -> subcategory. `AI_RMF_Mapping_Sheet_Design.md` is the starting point for every
session. The old AI bank pilot (`archive/AI_RMF_Pilot_Decisions.md`) was never accepted. Its outputs (applicability.json,
airmf_to_cis.json, the two pilot banks, the work and batch files) were removed on 2026-10-22, so `/ai-questionnaire` has no
AI RMF bank until step 6. The audit trail (`data/ai/bank_build/audit.jsonl`, `judgement_log/`) is kept.

## Start here next session
All open decisions are settled (2026-10-22): `area_cis` kept as drafted; `always_cis_controls` 1, 2, 8, 17 named and
checked against the guides; no row count (content decides, the evaluator fails padding); the producer area is
`model_building` ("Model building"); criticality bands in USD (under 100k / 100k-500k / over 500k).
**GOVERN is the foundation** (decided 2026-10-22 after the first `mcp_tools` pilot put operational controls under GOVERN
labels): all 19 GOVERN subcategories are asked once for the organisation, picked by intake role (none, consumer,
producer), never mapped to an AI area; areas map only MAP (context), MEASURE (checking) and MANAGE (responding).
`foundation` replaces `org_wide` in `mapping_rules.json` (foundation subcategories: MEASURE 3.2, 4.1 and MANAGE 1.2, 1.3
on 2026-10-23; MAP 1.3, 1.5, 3.4, MEASURE 1.1, 1.2, 3.1, MANAGE 1.4, 2.1 on 2026-10-26);
the per-area inventory check is gone (inventory is GOVERN 1.6). `ai_rmf_core.json` now holds the functions with their
Playbook descriptions, which the drafter and evaluator get. See `AI_RMF_Mapping_Sheet_Design.md` section 3.
**First full run (2026-10-23) reviewed on 2026-10-26 and deleted** (`mapping.json`, `mapping.xlsx`; the judgement log
and audit trail are kept). 203 rows, 14 needing review, 11 subcategories reached by no area; the evaluator judged the
rows that were there well but missed what was absent. Decided and done (2026-10-26):
- MAP 1.3, 1.5, MEASURE 1.1, MANAGE 2.1 foundation (MAP 1.2, 1.4, MEASURE 4.3 stay area subcategories).
- Drafter and evaluator go through every subcategory, not only the obvious ones; an empty `cis_refs` fails when a
  candidate fits; folds only when the row fully asks the folded outcome.
- A folded subcategory counts as reached (asked and scored through its row).
- Evaluator findings have a kind: `row`, `missing` (named subcategory, stored once per area, shown as a flagged
  Mapped = no line; no longer flags every row of the function), `note` (does not block; e.g. area impact too narrow).
- A re-draft merged with the person's decisions is checked again; removing a row with folds in the sheet is
  rejected; the sheet column is "Why (comment)".
- Same model for drafter and evaluator in the pilot, so the comparison tests the prompt change only.
**Pilot re-run (mcp_tools, agent, model; 2026-10-26) reviewed and deleted.** It found what the first run missed
(MAP 1.6, MEASURE 2.6 on mcp_tools; MANAGE 4.1 on agent; MEASURE 2.3) but over-mapped: rows doubled (model 12 -> 34,
agent 16 -> 36, mcp_tools 14 -> 26), six subcategories written with the same why in all three areas, and model took
model-building rows (performance, benefits, go / no-go). Cause: the agents saw only their own area. Decided and done:
- Model is IP: impact back to `assets` (the 2026-10-26 widening to `process` was wrong).
- New impact `people` (AI RMF harm to People; no Ecosystem), on customer_facing and output only. Agent and MCP tools
  are access first; model building's people harm comes through output.
- MAP 3.4, MEASURE 1.2, MEASURE 3.1, MANAGE 1.4 foundation (12 in all); MAP 1.1 and MANAGE 1.1 stay per area.
- The input gives the agents `other_areas` (id, name, applies to, covers from the AI areas sheet); both prompts leave
  out (evaluator: fail) a row that belongs to another area's covers or whose why would read the same for any area.
- One question citing many safeguards is fine (no change).
**Second pilot (model, agent; 2026-10-26) reviewed:** model 15 rows, all about IP; agent 32 rows, agent-specific, the
six repeated rows gone. Decided: reliability / TEVV required checks on Output only (they forced accuracy and test
rows onto Model); Model building keeps impact `assets` (its harm reaches people and processes through Output); agent
impact adds `data` (personal data in memory and moved by actions). Both recorded areas are stale by these changes:
go to the full run.
**Batch 1 (customer_facing, output, internal_process, model_building; Sonnet drafter and evaluator; 2026-10-26)
reviewed:** sizes sensible (20, 20, 21, 26), the evaluator caught off-topic safeguards and real missing rows, Output
carries the reliability rows. But model_building did TEVV and recipient-harm rows, and bias (MEASURE 2.11) was mapped
on internal_process. Decided: Model building's covers narrowed to the activity (build or tune, base models, release,
limits told, withdraw; testing answers is Output, weights are Model, data is Test, tuning and evaluation data);
Output's covers add bias (treating people or groups unequally) and say TEVV of answers is done there for everyone;
internal_process does not get `people` (bias in answers is a people harm at Output; bias awareness is foundation,
GOVERN). Any change to the AI areas sheet makes every recorded area stale (each draft's input carries the other areas'
covers), so all 6 recorded areas must be re-drafted. Sonnet is fine for the remaining runs.
1. Run the remaining batches (ask the user before running; Sonnet): batch 2 model, agent, mcp_tools, source_data,
   test_tuning_data; batch 3 code_generation, vendor_ai, invisible_usage, input, hosting; batch 4 (re-draft)
   customer_facing, output, internal_process, model_building. Delete the work and `mapping_input_*.json` files after.
   Expect on model the two missing rows of the pilot (MANAGE 3.2 base models monitored, MANAGE 4.1 old versions
   disposed of); on output MEASURE 2.1, 2.4, 2.5 and 2.3; on agent MANAGE 4.1 and MEASURE 2.6; MAP 3.1 on
   customer_facing or internal_process, MAP 5.2 on customer_facing; no subcategory with the same why in every area.
2. Review `mapping.xlsx` (Status = needs_human_review: failed rows and missing lines; Evaluator note), then the
   Coverage sheet; `sheet_io.py import mapping`.
3. Accept: `.venv/bin/python ./scripts/ai_pilot.py accept-mapping` (refuses while an area is missing or stale, a row
   needs review or the sheet has unimported edits; lists the unreached subcategories in the acceptance).
4. Then TODO step 4 below.
Note: in this codespace `check_freshness.py --ai-bank` stops at "sources missing: CIS -> CSF xlsx" before it reaches
the mapping line; upload that file (data/ai/source/README.md) to see the `mapping` stage.

## Build the AI RMF mapping (steps of the design note)
0. ~~Write the model down.~~ Done 2026-10-21.
1. ~~AI areas and intake.~~ Done 2026-10-22. `data/ai/authoring/ai_areas.xlsx` (the decision: 14 areas, kind, applies
   to, impact) -> `data/ai/ai_areas.json` via `scripts/sheet_io.py`. The intake asks AI in use; "Do you build AI, use AI,
   or both?" (for producer or both: built on an existing model? given to others?); "How do you use AI?"; "What does
   your AI include?". It writes `role`, `producer`, `ai_areas` (automatic ones in `scope_rules.json` `ai_area_rules`) and
   the old fields derived for the current filter.
2. Draft the mapping. Built and run on all 14 areas 2026-10-23; that run was reviewed and deleted on 2026-10-26 and
   is being re-run with the improved prompts ("Start here"): `prepare_ai_bank.py mapping --area ID`, `prompts/ai_rmf_mapping_drafter.md`,
   `prompts/ai_rmf_mapping_evaluator.md`, `record_ai_bank.py mapping` (rejects a draft that breaks
   `data/ai/mapping_rules.json`: no GOVERN row, subcategory of the right function, the area's candidate safeguards and
   impacts, MAP, MEASURE and MANAGE each covered, the required checks: audit trail with a CIS control 8 safeguard,
   incident response, reliability; an optional `folded` list names subcategories a row also covers).
3. ~~Review and accept the mapping (the tooling).~~ Done 2026-10-23. Review sheet: `sheet_io.py export mapping` writes
   `data/ai/authoring/mapping.xlsx` (one line per area x MAP/MEASURE/MANAGE subcategory, mapped or not, Playbook outcome,
   safeguard titles; a Coverage sheet), `import mapping` validates every area like agent output and stores changed
   lines as `decided_by: human` (a fold shows as a note on the Why cell; removed lines are kept as
   `removed_by_human`). Accept gate: `ai_pilot.py accept-mapping` (`mapping_accepted.json`, a hash of the mapping's
   content). Freshness: a `mapping` stage in `check_freshness.py --ai-bank` (missing, incomplete, stale, rows needing
   review, sheet edited but not imported, not accepted or changed since, subcategories reached by no area). A re-drafted
   area keeps the person's decisions (`decided_by: human` rows and `removed_by_human`), checked against the rules again.
   2026-10-26: evaluator findings `row` / `missing` / `note`, folds count as reached, a row with folds cannot be
   removed in the sheet. Foundation subcategories decided from the first run's Coverage sheet (8 in
   `foundation.subcategories`); after the re-run, check the Coverage sheet again for any further ones.
4. Rewire question generation to mapping rows: `prepare_ai_bank.py batch` from mapping rows, generator prompt (questions
   per AI area x subcategory, the row's safeguards as evidence; GOVERN questions per subcategory from the Playbook, each
   tagged with the roles it applies to: none (AI policy and shadow-AI discovery), consumer, producer, plus a producer
   flag where needed; a review sheet for them in `sheet_io.py`: GOVERN subcategory, questions, roles, since GOVERN is
   not in the mapping sheet), `build_ai_questions.py` (GOVERN questions by the intake role; area rows from the client's
   `ai_areas`; base-model questions only when `producer.built_on_existing_model`; release questions only when
   `producer.given_to_others`; gap rule per row from the CIS -> CSF mapping; up to 6 questions per subcategory). Retire `legacy_profile`, the modifiers,
   `question_categories.json` and the `AI_APPLICABILITY` path (the applicability and CIS-linker prompts, modes and
   freshness stages were already removed on 2026-10-22). Carry over the generator prompt fixes from
   the old pilot (`archive/AI_RMF_Pilot_Decisions.md` section 4): one subject per question; cite a safeguard only if it supports
   the question. Area questions are written proportionate to criticality ("for your highest-criticality AI
   systems, ..."), one per AI area x subcategory, never repeated per AI system (design note section 4).
5. Severity: the standard criticality question (USD under 100k / 100k-500k / over 500k; reputation; safety) and the
   priority rules (domain floor for healthcare and manufacturing / OT, process criticality, data classification) for
   the Stage 2 writer. The criticality question becomes the AI system inventory (GOVERN 1.6): each system with its AI
   areas and criticality; foundation subcategories (non-GOVERN) are picked like GOVERN, once for the organisation.
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
