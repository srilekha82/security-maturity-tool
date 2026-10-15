# AI RMF bank: first build, decisions and pilot (2026-10-14)

Written during the first live run of `/build-ai-bank`. It records what was decided and why, so it can be reviewed later.
Nothing here is final until you accept the pilot (`ai_pilot.py accept`). The raw judgements are in
`data/ai/applicability.json` (one `reason` per subcategory) and `data/ai/crosswalks/airmf_to_cis.json`; the write-once
records are in `data/ai/bank_build/judgement_log/`. This file is the summary of the judgement calls.

## 1. Applicability pass (recorded, model claude-sonnet-5-5)
Producer bank applies to **72 of 72** subcategories, consumer bank to **67 of 72**.

Consumer bank has no question for (builder-only duties): MAP 1.6, MAP 2.3, MAP 3.3, MEASURE 2.2, MEASURE 2.12.
- MAP 3.3 follows the example in the prompt (scoping of intended use is the builder's duty).
- MEASURE 2.2 (human-subject evaluations, representative test datasets) and MAP 2.3 (experimental design, data
  selection) are builder work; consumer fairness is asked through `use_context_impact` under MEASURE 2.11.
- MEASURE 2.12 (energy and emissions of training and running a model): a consumer's footprint is the vendor's.
- MAP 1.6 (eliciting system requirements, design decisions): builder work; the consumer side is covered by MAP 1.x and
  GOVERN 6.

Judgement calls you may want to challenge:
1. **MEASURE 2.12 (environmental impact) for producers is mapped to `intended_use_impact`.** No category covers
   energy or emissions; "impact assessment" was the closest fit. A different option is to leave it unmapped.
2. **The `ai_access_*` categories were given to a few subcategories on purpose.** The Playbook says almost nothing
   about agents or MCP, so without this the bank would have no access questions. Mapped: MAP 2.2, MAP 3.5, MANAGE 2.2,
   MEASURE 2.7, MEASURE 2.8 (consumer `ai_access_identity`; producer `ai_access_tools` for MAP 2.2, MAP 3.5, MEASURE 2.8).
   If you would rather have access questions come from somewhere else, this is the place to change.
3. **Some producer-only categories were given to one subcategory each** where the Playbook text fits:
   `model_assets_ip` (GOVERN 1.6 inventory and registry, MEASURE 2.7 watermarking against extraction, MANAGE 4.3 version
   history), `build_infra` (MANAGE 2.2 security countermeasures), `training_data` (MAP 2.3, MAP 4.1, MEASURE 2.2, MEASURE 2.10).
   Expect thin coverage of these categories: the Playbook is light on them and CIS guides give evidence prompts, not questions.
4. **MANAGE 3.2 (pre-trained models monitored) applies to consumers** (`third_party_supply`), on the reasoning that a
   consumer who fine-tunes or runs a pre-trained model tracks it as third-party risk.
5. Bias, fairness and explainability (MEASURE 2.9, 2.11) go to the producer category `fairness_safety_eval`; consumers
   get them only through `use_context_impact`, as the prompt's rule 5 says.

## 2. AI RMF to CIS link (recorded)
**30 of 72** subcategories link to at least one CIS safeguard; 42 deliberately link to nothing (bias, fairness,
stakeholder engagement, culture, policy-only outcomes). The link is for evidence prompts and tagging, never question text.

- Linked mostly where a safeguard's subject really supports the outcome: inventory (GOVERN 1.6), third-party and
  supply chain (GOVERN 6.1/6.2, MANAGE 3.1/3.2, MAP 4.1/4.2), incident response and monitoring (GOVERN 1.5, MANAGE 2.3/2.4/4.1/4.3,
  MEASURE 2.4/3.1), security testing and logging (MEASURE 2.7/2.8), data handling and privacy (MEASURE 2.10, GOVERN 1.1), training (GOVERN 2.2, MAP 3.4).
- **The links are LLM-guide heavy.** Few subcategories carry MCP or AGENT safeguards, so strictly MCP-heavy subcategories
  do not exist. In the pilot, MAP 2.2 is the nearest "MCP" case (2 of 6 safeguards from the MCP guide) and MAP 3.5 the
  "agentic" one (2 AGENT, 1 MCP). If the full bank shows too few MCP or agent questions, widen the links first.

## 3. Pilot set (6 subcategories, confirmed by the user)
| # | Subcategory | Bank | Categories | What it tests |
|---|---|---|---|---|
| 1 | GOVERN 6.1 | producer | upstream_models | GOVERN case, supply-chain safeguards from all three guides |
| 2 | MAP 1.1 | consumer (internal use) | use_context_impact | no CIS links: the Playbook-only path |
| 3 | MEASURE 3.3 | consumer (customer-facing) | use_context_impact, incident_recovery | feedback and appeal channels for users |
| 4 | MANAGE 3.1 | consumer (third-party embedded) | third_party_supply | vendor AI, LLM, MCP and AGENT supplier safeguards |
| 5 | MAP 2.2 | consumer | use_context_impact, ai_access_identity | closest to MCP-heavy |
| 6 | MAP 3.5 | consumer | use_context_impact, ai_access_identity | agent-heavy, human oversight of AI actions |

Per subcategory: generator subagent, then evaluator subagent (sonnet), one revision turn if it fails, then recorded.
Prompts under test: `prompts/ai_rmf_question_generator.md`, `prompts/ai_rmf_question_evaluator.md`.

## 4. Pilot results
All 6 subcategories were recorded (producer bank 1, consumer bank 5). **The pilot is NOT accepted yet**: `ai_pilot.py accept`
has not been run, so `check_freshness.py --ai-bank` shows `pilot: missing` and both banks `incomplete`. That is expected.

| Subcategory | Turn 1 failures | Turn 2 | Recorded as |
|---|---|---|---|
| GOVERN 6.1 (producer) | 1 | 0 | pass |
| MAP 1.1 (consumer) | 2 | 1 | needs_human_review |
| MEASURE 3.3 (consumer) | 2 | 0 | pass |
| MANAGE 3.1 (consumer) | 2 | 1 | needs_human_review |
| MAP 2.2 (consumer) | 1 | 1 | needs_human_review |
| MAP 3.5 (consumer) | 2 | 0 | pass |

- **Turn 1: 0 of 6 passed** (10 of 30 questions failed). **After turn 2: 3 of 6 pass, 3 need human review** (3 of 30 questions still failing).
- What failed on turn 1 was mostly tagging, not question quality: `scope_tags` claimed (customer_facing x3, poc, third_party_embedded) when
  the question does not depend on that context; one capability/rung mismatch (rag tagged but the question needs mcp); one
  unrelated CIS reference; two questions that chain several asks into one.
- **Still failing after turn 2 (for you to judge):**
  - MAP 1.1 Q3: chains context of use, who is affected, impacts, where it is kept and how often it is revisited. Fix: split or trim.
  - MANAGE 3.1 Q4 (contingency plan for a critical vendor AI): cited `LLM-15.6` does not support it. My crosswalk has no safeguard that
    backs a contingency plan for this subcategory, so the right fix is probably `cis_refs: []`, not a stretched reference.
  - MAP 2.2 Q5 (record of connections of tool-calling AI): the evaluator says topic `ai_access` does not fit a documentation
    question about where connections are recorded. This points back at my applicability decision (section 1, item 2): MAP 2.2 may
    not be a good home for `ai_access_identity`. Either re-tag as governance, or move the access mapping to a better subcategory.
- **The evaluator caught all 3 deliberately weak questions** (added to a copy of MAP 3.5, never recorded): "Do you have a policy for
  human oversight...?", "Is there a process for reviewing AI outputs? (yes/no)", "Have you documented who is responsible...?" were
  each failed under check 1 (yes/no, not practice-revealing).
- Passing examples to read: GOVERN 6.1 Q1 and Q4, MEASURE 3.3 Q1 and Q2, MAP 3.5 Q3 and Q5 (in the bank files).
- **Cost:** 25 subagent calls (6 generators, 6 evaluators, 6 revisions, 6 re-evaluations, 1 weak-question test), about 33-35K
  tokens each, roughly 0.85M in total. Most of each call is fixed overhead (the prompt and tools), not the batch (6-8 KB), so a
  full run batched one AI RMF category at a time (about 3 to 8 subcategories per call) should cost far less per subcategory
  than this one-subcategory-per-call pilot.
- Work files are kept for review in `data/ai/bank_build/work/` (`<tag>_gen1`, `_eval1`, `_gen2`, `_eval2`, `_record`,
  `weaktest_eval.json`) and the batch inputs are `data/ai/bank_build/batch_*.json`. Delete them once you have reviewed.

Suggested tuning of `prompts/ai_rmf_question_generator.md` before the full run (all about the failures above):
1. Tag a question `customer_facing`, `poc`, `third_party_embedded` etc. only if it makes no sense without that context;
   otherwise leave `scope_tags` and `modifiers` empty.
2. The `capability` rung must be at or above every cited `cis_ref` and the question's own subject.
3. One question asks one thing: no more than one "where is it kept" plus one "how often" per question.
4. If no listed safeguard really supports the question, use `cis_refs: []`.

## 5. How to review and what to do next
1. Read the bank entries for the 6 pilot subcategories (`data/ai/banks/question_bank_ai_rmf_producer.json` and `..._consumer.json`).
   Check: practice-revealing (how, who, how often, what evidence), not checkbox; fit with the subcategory outcome;
   tags (rung, usage context, topic) sensible.
2. Tune `prompts/ai_rmf_question_generator.md` / `ai_rmf_question_evaluator.md` if needed and re-run the pilot with
   `/build-ai-bank`.
   Editing either prompt after acceptance makes the acceptance stale.
3. When happy: `.venv/bin/python ./scripts/ai_pilot.py accept --note "<what you decided>"`.
4. Then `/build-ai-bank` full run (both banks, `--missing`, one AI RMF category per batch), then the CSF AI impact
   notes (Step 7), then `/build-csf-bank all`.
