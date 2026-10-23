# TODO (last updated 2026-10-23)

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
`foundation` replaces `org_wide` in `mapping_rules.json` (on 2026-10-23 MEASURE 3.2, 4.1 and MANAGE 1.2, 1.3 were added as foundation subcategories);
the per-area inventory check is gone (inventory is GOVERN 1.6). `ai_rmf_core.json` now holds the functions with their
Playbook descriptions, which the drafter and evaluator get. See `AI_RMF_Mapping_Sheet_Design.md` section 3.
1. Re-run the mapping pilot on `mcp_tools` with the new rules (the first run, recorded 2026-10-22 with GOVERN rows,
   is superseded). Ask the user before running. From the review of the Codespace run (2026-10-23):
   - expect MAP 1.6 (intended access of each tool, against MAP 2.2 actual use), MEASURE 2.6 (tools fail safely: a
     failed or slow tool does not leave the agent acting on half a result) and MEASURE 2.10 (personal data passed in
     tool parameters or sent to outside MCP servers);
   - MEASURE 3.2, 4.1 and MANAGE 1.2, 1.3 are now foundation (2026-10-23): the drafter no longer sees them and the
     recording script rejects them; expect no row on MEASURE 3.1 or MANAGE 1.4 either (check after the run);
   - impact widened to access, process, data in `ai_areas.xlsx` (2026-10-23; tools act in processes and move data);
   - re-check MANAGE 2.2 (is it about this area or general?);
   - after the re-run, delete `data/ai/bank_build/mapping_input_mcp_tools.json` and `data/ai/bank_build/work/`.
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
   `data/ai/mapping_rules.json`: no GOVERN row, subcategory of the right function, the area's candidate safeguards and
   impacts, MAP, MEASURE and MANAGE each covered, the required checks: audit trail with a CIS control 8 safeguard,
   incident response, reliability). Run it: "Start here" above.
3. Review and accept the mapping. ~~Review sheet~~ done 2026-10-22: `sheet_io.py export mapping` writes
   `data/ai/authoring/mapping.xlsx` (one line per area x MAP/MEASURE/MANAGE subcategory, mapped or not, Playbook outcome,
   safeguard titles; a Coverage sheet), `import mapping` validates every area like agent output and stores changed
   lines as `decided_by: human`. Still to do: an accept gate like `ai_pilot.py accept`; a `mapping` stage in
   `check_freshness.py` (missing, incomplete, stale, subcategories unreached, sheet edited but not imported); and
   `record_ai_bank.py mapping` must not overwrite `decided_by: human` rows when an area is re-drafted (today it replaces
   the whole area). After all 14 areas are drafted: decide any further foundation subcategories from the Coverage
   sheet (unreached, or the same why in every area, and about method) and list them in `mapping_rules.json`
   `foundation.subcategories` (design note section 3); the scripts already honour the list.
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
