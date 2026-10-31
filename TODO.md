# TODO (last updated 2026-10-31)

State: the AI RMF model was redesigned (2026-10-16 to 2026-10-22): AI areas (how AI is used and what it is made of) ->
attack areas -> AI RMF function -> subcategory. `AI_RMF_Mapping_Sheet_Design.md` is the starting point for every
session. **The mapping is accepted (2026-10-28).** **Step 4 (question tooling) is built (2026-10-29)**; the old model (question categories, rungs, usage contexts, modifiers, producer and consumer banks) is
removed. **Both AI RMF question banks and the CSF AI impact notes are built (2026-10-31)**: every
`check_freshness.py --ai-bank` stage is current. The audit trail (`data/ai/bank_build/audit.jsonl`,
`judgement_log/`) is kept.

## Start here next session
**Next, in order (updated 2026-10-31 after the end-to-end test):**
1. ~~Impact notes~~ done 2026-10-31: `exposure` is optional (written only where the safeguard text supports something
   real for an org with no AI); the 19 flagged notes lost their exposure note, ID.IM-02's model note points to Output,
   PR.PS-03 and RC.CO-04 lost their use layer too and have no note. 46 notes, all pass (29 exposure, 43 use layers).
2. ~~The 8 flagged question subcategories~~ done 2026-10-31 (the user agreed to Claude's suggestions): GOVERN 4.2
   asks sharing impacts beyond the team; GOVERN 5.1 dropped the published-principles question; MAP 3.5, MAP 4.1 (two),
   MEASURE 2.10 reworded; MEASURE 2.4 dropped LLM-13.1; MANAGE 4.1 cites action 9 only; MANAGE 4.3 has its own
   hosting question. Both banks pass (foundation 84 questions, areas 203).
3. ~~`/generate-questions` end to end~~ done 2026-10-31 in the cloud session on a test client (`runs/TestBank_2026-10-31`,
   not committed: finance, no certs, role both, 11 AI areas). The workbook is complete: CSF 106 subcategories / 220
   questions, AI RMF 72 / 254 (foundation 84, areas 170), the AI systems sheet; 14 entries LOW (CSF 5, AI 3 + 6). The
   reviewers changed almost every entry (CSF 103 of 106, AI 31 of 31 and 41 of 41) and the rewrite checker failed 82,
   10 and 12 in round 1. About 1.3M subagent tokens; hit the 5-hour limit once and resumed. Freshness cannot run in
   the cloud container (CIS and CSET sources are only in the codespace). Fix before a real client, in order:
   a. Align the reviewer prompts (`prompts/questionnaire_assessor.md`, `prompts/ai_rmf_questionnaire_assessor.md`) with
      the rewrite checker's check 3 (one "how" plus at most one short follow-up): the reviewers add coverage, "how
      often" and owner clauses that the checker then fails as chained (all 82 CSF round-1 failures). Coverage and
      artefacts go in the evidence prompt.
   b. Write specific evidence prompts once, in the AI banks (generator, per question), instead of one generic line per
      bank or impact (`data/ai/evidence_prompts.json`) that every engagement's reviewer rewrites on every entry.
   c. Give the CSF draft the client's domain: the reviewer removed financial-sector wording (FS-ISAC, "institution")
      for a financial client because the draft does not say the sector and the prompt forbids assuming one.
   d. Tell the AI reviewer which areas have the criticality frame optional (`question_rules.json`
      `criticality_frame_optional`): it added "highest-criticality" to Model, Model building and Test data questions.
   e. The finance CSF bank is weak: 38 subcategories use the generic fallback and many bank questions test a
      neighbouring topic (the reviewer replaced them). `/build-csf-bank finance` again, then the other domains.
   Then re-run the test client to compare (fewer changes, fewer round-1 failures, lower cost).
4. Optional: skim the ~280 passing questions in the two question review sheets.
5. `/build-csf-bank all` (after 3e).
6. Later: step 5 (severity), Stage 2 (maturity XLS and answer session), the parked items below.
- Pilot accepted 2026-10-29 (four rounds; GOVERN 1.2, 1.6, 6.1; MAP 1.4, MAP 3.2, MEASURE 2.7, MEASURE 2.8, MANAGE 3.2).
- Full run 2026-10-29 to 2026-10-31 (Sonnet generator, Opus evaluator, 9 batches, two rounds each; interrupted once by
  the usage limit and resumed from the work files): foundation 31 subcategories, 84 questions; areas 41, 202 questions.
- Was flagged, decided 2026-10-31 (see 2. above; review sheets `data/ai/authoring/questions_<foundation|areas>.xlsx`;
  the user decides in chat, Claude applies and imports): GOVERN 4.2 (sharing impacts beyond the
  team not asked), GOVERN 5.1 Q3 (publishing principles is not taking in outside feedback), MAP 3.5 Q6 (depends on
  the previous question), MAP 4.1 Q6 and Q9 (two asks, citations), MEASURE 2.4 Q4 (LLM-13.1 does not fit outside
  agents), MEASURE 2.10 Q1 (lost its secrets-in-code focus, repeats the Input question), MANAGE 4.1 Q4 (action 8 only
  fits removal), MANAGE 4.3 (the Hosting row's incidents are not asked).
- CSF AI impact notes (`data/csf/ai_impact_notes.json`), 2026-10-31: 48 subcategories (58 have no CIS mapping, no
  note). Now checked like the questions: Opus evaluator (`prompts/ai_impact_notes_evaluator.md`,
  `record_ai_bank.py notes-review`), writer revision turn, round 2 judges only rewritten notes; review sheet
  `sheet_io.py export|import impact_notes`. Round 1 flagged 34 (exposure notes assuming the org runs AI, missing use
  layers); after the revision 45 have a use layer and 19 are still flagged (mostly exposure notes the safeguard text
  does not support for orgs without AI).
- Every writer is checked (DESIGN_RULES rule 7, 2026-10-31): the questionnaire reviewers' rewrites now go to an Opus
  checker (`prompts/assessor_rewrite_checker.md`, `/assess-questionnaire` step 3); `record_judgements.py log --check`
  flags rewrites it does not confirm LOW (`data/common/assessor_check.json`). Not yet run on a real engagement.
- Step 5 (severity) can wait. The step 4 decisions are in the design note, section 7.

Where things stand:
- `data/ai/mapping.json` is accepted (`data/ai/bank_build/mapping_accepted.json`): 14 AI areas, 208 rows (41
  subcategories), every subcategory reached by an area row, a fold or the foundation. Review sheet:
  `data/ai/authoring/mapping.xlsx`.
- Foundation (asked once for the organisation, never per area): all 19 GOVERN subcategories plus 12 in
  `mapping_rules.json` `foundation.subcategories` (MAP 1.3, 1.5, 3.4; MEASURE 1.1, 1.2, 3.1, 3.2, 4.1; MANAGE 1.2, 1.3,
  1.4, 2.1).
- Built 2026-10-29: `data/ai/question_rules.json` (banks foundation and areas, roles, producer flags, impacts);
  `prepare_ai_bank.py batch <foundation|areas>` (area batch: one item per subcategory with every area's row);
  generator and evaluator prompts (shared questions with `rows`, roles, flags, criticality frame, policies asked as
  practice); `record_ai_bank.py questions` (every row asked once per allowed role, folds cited, foundation needs a
  consumer and a producer question; stores `rows_sha` and each row's area and impact) and `bank_freshness`;
  `build_ai_questions.py` (a filter on role, producer flags and AI areas, "This question covers: ..." note, evidence by
  impact); questionnaire AI sheet with an Area column; intake without the old fields; `scope_rules.json` and
  `evidence_prompts.json` rewritten; `question_categories.json` removed; commands, README, DESIGN_RULES and the
  pipeline design updated; review sheets `sheet_io.py export / import area_questions`, `foundation_questions` (a
  person's edits are stored as `decided_by: human` and protected from later agent output unless `--replace-human`).
- Any change is a delta: a change to an area's own row in `ai_areas.xlsx` or to the sources needs that area
  re-drafted; a change to the rules or to another area needs only `record_ai_bank.py revalidate` (no agent). A change
  in the review sheet is imported and the mapping accepted again. A changed mapping row makes its subcategory's area
  questions incomplete in the freshness check.
- The user cannot easily edit spreadsheets: they decide in chat, Claude applies it to the sheet and imports.

Open for step 4 and after:
- No AI gap rule (decided 2026-10-29): every AI question asks what is done for AI, so it never repeats the CSF sheet
  or ISO 27001, and ISO SoA exclusions leave no hole. The CIS -> CSF xlsx is now in `data/ai/source/` (parses: 153
  safeguards, 46 mapped to 48 CSF subcategories); it is used only for the CSF AI impact notes.
- Scoring when several areas ask one subcategory: Stage 2 (questions keep their subcategory and rows).


## Build the AI RMF mapping (steps of the design note)
0. ~~Write the model down.~~ Done 2026-10-21.
1. ~~AI areas and intake.~~ Done 2026-10-22. `data/ai/authoring/ai_areas.xlsx` (the decision: 14 areas, kind, applies
   to, impact) -> `data/ai/ai_areas.json` via `scripts/sheet_io.py`. The intake asks AI in use; "Do you build AI, use AI,
   or both?" (for producer or both: built on an existing model? given to others?); "How do you use AI?"; "What does
   your AI include?". It writes `role`, `producer`, `ai_areas` (automatic ones in `scope_rules.json` `ai_area_rules`);
   the old derived fields were removed in step 4.
2. ~~Draft the mapping.~~ Done 2026-10-27 (all 14 areas, Sonnet drafter and evaluator; history below): `prepare_ai_bank.py mapping --area ID`, `prompts/ai_rmf_mapping_drafter.md`,
   `prompts/ai_rmf_mapping_evaluator.md`, `record_ai_bank.py mapping` (rejects a draft that breaks
   `data/ai/mapping_rules.json`: no GOVERN row, subcategory of the right function, the area's candidate safeguards and
   impacts, MAP, MEASURE and MANAGE each covered, the required checks: audit trail with a CIS control 8 safeguard,
   incident response, reliability; an optional `folded` list names subcategories a row also covers).
3. ~~Review and accept the mapping.~~ Accepted 2026-10-28 (tooling built 2026-10-23). Review sheet: `sheet_io.py export mapping` writes
   `data/ai/authoring/mapping.xlsx` (one line per area x MAP/MEASURE/MANAGE subcategory, mapped or not, Playbook outcome,
   safeguard titles; a Coverage sheet), `import mapping` validates every area like agent output and stores changed
   lines as `decided_by: human` (a fold shows as a note on the Why cell; removed lines are kept as
   `removed_by_human`). Accept gate: `ai_pilot.py accept-mapping` (`mapping_accepted.json`, a hash of the mapping's
   content). Freshness: a `mapping` stage in `check_freshness.py --ai-bank` (missing, incomplete, stale, rows needing
   review, sheet edited but not imported, not accepted or changed since, subcategories reached by no area). A re-drafted
   area keeps the person's decisions (`decided_by: human` rows and `removed_by_human`), checked against the rules again.
   2026-10-26: evaluator findings `row` / `missing` / `note`, folds count as reached. 2026-10-27: a change is a delta
   (`revalidate`). 2026-10-28: editable "Folded into this row" column (clear it to unfold; a row's folds must be
   cleared before it can be removed).
4. ~~Question generation from the mapping rows.~~ Built 2026-10-29 (see "Start here" and design note section 7): two banks (foundation, areas) of every possible question tagged with roles and producer flags;
   batch per subcategory with every area's row so similar rows share a question; recording checks coverage;
   selection is a filter. The old model (`legacy_profile`, rungs, usage contexts, modifiers, topics,
   `question_categories.json`, `AI_APPLICABILITY`, producer and consumer banks) is removed. Review sheets built.
   No gap rule: the questions are AI-specific (design note section 7).
5. Severity: the standard criticality question (USD under 100k / 100k-500k / over 500k; reputation; safety) and the
   priority rules (domain floor for healthcare and manufacturing / OT, process criticality, data classification) for
   the Stage 2 writer. The criticality question becomes the AI system inventory (GOVERN 1.6): each system with its AI
   areas and criticality; foundation subcategories (non-GOVERN) are picked like GOVERN, once for the organisation.
6. Pilot the question banks on a few mapping rows, accept (`ai_pilot.py accept`), then the full producer and consumer
   banks, then the CSF AI impact notes.
7. Tests and docs; fix the code review findings listed at the end of the design note (two are reproduced bugs:
   `parse_soa.py` numeric ids, `extract_cset_candidates.py` replay order).

## History of the mapping (2026-10-22 to 2026-10-28)
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
GOVERN); internal_process and customer_facing covers add that wrong or biased output is tested at Output and the area asks how staff or customers check, report and challenge it and how high-impact decisions are caught and audited (the business view: audit and high-impact decisions, not bias). Any change to the AI areas sheet makes every recorded area stale (each draft's input carries the other areas'
covers), so all 6 recorded areas must be re-drafted. Sonnet is fine for the remaining runs.
**All 14 areas drafted (Sonnet, 2026-10-27)**: 190 rows, 31 flagged, 19 missing lines, 3 unreached (MAP 1.2, MAP
1.4, MEASURE 1.3). Decisions held (bias and TEVV at Output, Model is IP, Model building the activity, people only on
Output and customer_facing). Decided 2026-10-27: MAP 1.2 and MAP 1.4 stay area subcategories, mapped by hand in the
sheet (MAP 1.2 on model_building, impact assets: the team that builds the model spots bias; consumers' bias knowledge
is GOVERN. MAP 1.4 on internal_process, customer_facing and vendor_ai: business value of what the AI's results are
used for; not invisible_usage, whose need is MAP 3.1; not Output, a noun; not code_generation, which goes through the audit and usual software review process, assessed by the CSF). A change is now a delta:
`record_ai_bank.py revalidate` re-checks areas after a rules or other-area change, no agent.
**Step 3 done 2026-10-28: mapping accepted** (14 areas, 208 rows, every MAP/MEASURE/MANAGE subcategory reached by an area or the foundation; `data/ai/bank_build/mapping_accepted.json`). MEASURE 2.9 mapped on Output (answers presented with enough context to judge trust). Next: TODO step 4.
2026-10-28: the user reviewed part of the sheet in chat; Claude filled the rest as suggestions the user agreed to;
MEASURE 2.9 mapped on Output; imported (74 lines decided by a person) and accepted.
2026-10-29 review decisions (invisible_usage frame optional; MAP 1.4 internal_process and customer_facing shared;
MEASURE 2.8 Q10 and Q12 framed; MEASURE 2.7 Q5 cites suggested action 2).

## Then
- `/build-csf-bank all` (only `finance` exists today).
- Run `/generate-questions` end to end on a test client (finance). The restructured commands, including the rewrite
  checker, have not been run as a whole in a live session yet.
- Optional: a "Client sees" column in the area question review sheet (the client label next to each question).

## Parked, no rush
- `validate_questions.py`: move the mechanical assessor checks (truncated text, duplicates, blank evidence, GV must be
  `full_discovery`, wrong cert named, missing LOW flag) out of the two assessor prompts into a script.
- Unit tests for `compute_scope.py` and `build_questions.py` (checked by hand so far, not in the test suite).
- `.claude/settings.local.json` holds two leftover permissions from an older session's scratchpad: remove them.
- Kept on purpose: `max_questions` stays in `data/csf/scope_rules.json` (the AI questionnaire has no cap); the CSF fallback question (38 finance subcategories)
  and auto-building missing banks inside `/generate-questions`.
