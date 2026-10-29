# Caizin AI Assessment Pipeline — Design Document

## Overview

End-to-end pipeline that takes org inputs and produces interactive assessment HTMLs for NIST CSF 2.0 and NIST AI RMF 1.0. The XLS is the canonical handoff between stages — everything upstream produces it, everything downstream consumes it.

---

## Pipeline Architecture

```
Question Bank Build  (subagents in caizin-csf-tool — infrequent, runs only when sources change)
├── CSF      → CSET already exists; freshness check only
└── AI RMF   → mapping (AI area x subcategory), then two banks (foundation, areas), generated from: AI RMF Playbook + CIS AI companion guides
               gate: skip if Playbook and CIS guides unchanged this quarter
               design: AI_RMF_Mapping_Sheet_Design.md
         ↓
Stage 1: Questionnaire Generation  (caizin-csf-tool)
         uses question bank above + org profile + compliance status + AI usage profile
         ↓
Stage 2: Agentic Answer Session    (gen-eval-loop — runs per org engagement)
         fills answers from org knowledge docs; gen-eval validates grounding
         ↓
Stage 3: HTML Generation           (Claude skills)
```

---

## Stage 1 — Questionnaire Generation

**Tool:** `caizin-csf-tool` (exists and working)

**Inputs:**
- Org profile: name, industry/domain, compliance certifications held (ISO 27001, SOC2, PCI DSS)
- AI usage profile (see the AI RMF track below): AI in use none / some / unsure, role (producer / consumer / both), producer flags (built on an existing model, given to others), the client's AI areas; plus engagement flags (CSF assessment done, ISO 27001 held, ISO 42001 held)
- SOA (Statement of Applicability) if ISO 27001 certified
- Compliance reports if available

**CSF track (exists):**
- Question bank: CSET (`CSET_Industry_Questions_CSF2_v2.xlsx`) — structured questions mapped to CSF 2.0 subcategories
- Scope logic: SOA → OLIR crosswalk (ISO→CSF) → question type per subcategory
- Question types: `full_discovery` / `gap` / `confirmatory` / `skip`
- Output: `csf_questions_assessed.json`

**AI RMF track (being built — the model is `AI_RMF_Mapping_Sheet_Design.md`, build steps in `TODO.md`; the first design is in `archive/`):**
- Model: how AI is used and what it is made of (**AI areas**, decided by a person in `data/ai/authoring/ai_areas.xlsx`) -> the attack areas they impact -> AI RMF function -> subcategory. GOVERN and 12 other subcategories are the **foundation**, asked once for the organisation; MAP, MEASURE and MANAGE are mapped per AI area (`data/ai/mapping.json`, reviewed and accepted by a person).
- Question banks: **two files, foundation and areas** (`question_bank_ai_rmf_foundation.json`, `question_bank_ai_rmf_areas.json`, under `data/ai/banks/`, reused across org runs). They hold every possible question: area questions per mapping row (a question may stand for several areas' rows), foundation questions per subcategory, each tagged with the roles it is asked of (none / consumer / producer) and any producer flags. No CSET equivalent exists for AI RMF, so they are generated.
- Sources: **AI RMF Playbook** (72 subcategories and their suggested actions — the primary question content) and the three **CIS v8.1 AI companion guides** (LLM, MCP, Agents — evidence and safeguards per mapping row, not question text). The profile XLS supplies the 72-subcategory structure.
- Generation: a generate–evaluate loop with subagents in this repo (pilot, then per-function batches), not the `gen-eval-loop` harness. One-time or infrequent build, not per-org.
- **Freshness gate:** the banks are not regenerated unless the Playbook or the CIS guides changed, or a mapping row changed after its questions were written. Mirrors `check_freshness.py`.
- **Scope driver is how AI is used, not certifications or sector.** Sector sets a severity floor and decorates the report. The intake captures AI in use (none / some / unsure), role (producer / consumer / both), for a producer whether the model is built on an existing model and given to others, how AI is used and what it includes (the client's AI areas; some areas are automatic).
- Selection is a filter: a client gets the questions whose roles, producer flags and (for area questions) AI areas match its intake. Area questions are asked once, proportionate to criticality ("for your highest-criticality AI systems"); the AI system inventory (GOVERN 1.6) is the only per-system question.
- Question types: same names as CSF. Every AI RMF question is `full_discovery`: each asks what is done for AI (an AI area, or AI in the organisation), never general security, so it does not repeat the CSF sheet or ISO 27001 and needs no gap rule (an ISO control excluded in the SoA leaves no hole). ISO 42001 coverage is a later optional phase.
- Engagement sequence: the CSF assessment first, then the AI RMF assessment scoped by AI usage, then the CSF output is updated with the AI-world notes according to the same usage pattern.
- Orgs that use no AI but are exposed to external agents or AI-enabled attackers are covered on the CSF side by short "AI-world impact" notes per CSF subcategory (`data/csf/ai_impact_notes.json`). The notes have two layers: an exposure note shown to every org, plus a use note added only when AI is in use (one wording for orgs with MCP / tools or agents, one for the rest). They are produced in the AI RMF build (CIS MCP/agents safeguards joined to CSF subcategories through the official CIS v8.1 → CSF 2.0 mapping).

The earlier usage models are retired: the 3-tier model (LLM prompting / MCP-agentic / client environment) was derived from internal Caizin work and mixed technology reach with usage context, and the first AI RMF design (technology rungs, usage contexts, modifiers, topic categories; `archive/`) under-mapped the attack surface.

---

## Stage 2 — Agentic Answer Session

**Tool:** `gen-eval-loop` (exists, generic harness)

**What it does:** Takes the questionnaire (`csf_questions_assessed.json`) and available org knowledge, fills answers per question using a generator–evaluator loop, outputs a completed profile XLS.

**Inputs:**
- `csf_questions_assessed.json` (from Stage 1)
- Org profile markdown (collected during intake)
- Interview notes / knowledge wiki (from assessor interviews with client)
- Compliance reports (SOA, audit reports, penetration test summaries if available)
- `soa_parsed.json` (if ISO 27001)

**NOT inputs:** Any back-and-forth assessment decisions specific to Caizin. Inputs are only what any org would provide through standard intake. This must be repeatable for any org.

**Gen-eval loop design:**

```
Generator agent
├── Context: one question + question_type + mapped controls + org knowledge docs
├── Task: draft an answer grounded in the org knowledge; cite specific evidence
└── Output: draft answer with evidence citations

        ↓ if evaluator returns FAIL

Evaluator agent (fresh session — no org context)
├── Input: question + draft answer only
├── Checks:
│   ├── Every claim traceable to a cited source (no inference)
│   ├── Gap questions honestly acknowledge the gap (not papered over)
│   ├── Evidence prompt answered with specifics (not "yes we do this")
│   └── Scope not over-claimed (answer doesn't assert org-wide coverage without basis)
└── Output: PASS or FAIL with specific critique per failing point

Loop: max 2–3 cycles. If still FAIL → human_review_required: true
```

**Output schema per question:**
```json
{
  "subcategory_id": "PR.DS-01",
  "question_type": "gap",
  "answer": "...",
  "evidence_cited": ["SOA: A.8.24 — Implemented", "..."],
  "fill_confidence": "HIGH | MEDIUM | LOW",
  "human_review_required": false,
  "fill_iterations": 1,
  "ai_overlay": true
}
```

**Final outputs:**
- CSF profile XLS — answers mapped to maturity scores; schema = NIST CSF 2.0 Organizational Profile Template (`NIST/CSF 2.0 Organizational Profile Template-final.xlsx`, sheet "Current and Target Profile", 19 columns: outcome ID and description, included, rationale; current priority / status / policies and processes / internal practices / roles / informative references / artifacts and evidence; target priority / tier / policies / practices / roles / informative references; notes; considerations)
- AI RMF profile XLS — answers mapped to maturity scores; schema = `caizin_ai_rmf_profile_v2.xlsx` format (11 columns: ID, Outcome, Included, Rationale, Priority, Layer, CurrentMaturity, CurrentState, TargetMaturity, TargetState, Evidence)

The XLS schema is fixed by what the downstream skills expect. Do not change it without updating the skills.

**Granularity:** Run one loop over all questions (generator fills all, evaluator flags specific subcategory IDs that are weak, generator revises only those in turn 2). Batch by CSF function if context becomes unwieldy.

---

## Stage 3 — HTML Generation

**Tool:** Claude skills (exist and working)

| Track | Skill | Input | Output |
|-------|-------|-------|--------|
| CSF | `caizin-nist-assessment` | CSF profile XLS | `Caizin_NIST_Assessment.html` |
| AI RMF | `caizin-ai-rmf-assessment` | AI RMF profile XLS | `Caizin_AI_RMF_Assessment.html` |

Both HTMLs are self-contained (no external dependencies). Both work on OneDrive (event delegation pattern, no inline onclick).

CIS controls appear in the roadmap tab of each HTML as the "how to fix it" layer — baked into the skill, not derived from the XLS. They don't change the gap assessment; they prescribe implementation actions to close each gap.

---

## What Exists vs What Needs Building

| Component | Status |
|-----------|--------|
| CSF question bank (CSET) | ✅ Exists |
| Questionnaire generation tool (caizin-csf-tool) | ✅ Exists and working |
| Gen-eval loop harness | ✅ Exists (generic, needs scenario config) |
| CSF skill + HTML | ✅ Exists and working |
| AI RMF skill + HTML | ✅ Exists and working |
| AI RMF mapping and question banks (foundation, areas) | 🟡 Mapping accepted; question tooling built, banks not generated yet |
| Agentic answer session (gen-eval scenario config + prompts) | ❌ To build |
| XLS writer (maps filled answers → profile XLS) | ❌ To build |

---

## Key Design Principles

1. **XLS is the canonical artefact.** Everything upstream produces it; everything downstream consumes it. Schema is fixed by the skills.

2. **Question bank must be grounded and frozen.** Free-form LLM question generation per engagement is costly and non-deterministic. The bank is built once from structured sources (CSET for CSF; the Playbook and CIS guides for AI RMF), checked by an evaluator, then frozen and reused. For AI RMF the bank is generated with subagents under a strict generate–evaluate loop (see `AI_RMF_Mapping_Sheet_Design.md`); the `gen-eval-loop` harness is used for *answering* (Stage 2).

3. **Evaluator has no org context.** The evaluator agent runs in a fresh session with only the question and draft answer. This ensures it judges the answer on its own merits, not on what it knows about the org.

4. **Honest gaps are mandatory.** If the org profile has no evidence for a control, the answer must say so. The evaluator must reject any answer that claims coverage without cited evidence. This is what makes the output usable vs. misleading.

5. **CIS controls are prescription, not diagnosis.** They live in the roadmap (how to fix gaps), not in the gap assessment itself (which is driven by maturity scores from the XLS).

6. **Pipeline is org-agnostic.** The tool must work for any org, not just Caizin. Caizin-specific decisions from the AI RMF review sessions are not inputs to this pipeline.

---

## Codebase Locations

| Repo | Purpose |
|------|---------|
| `caizin-csf-tool/` | Stage 1: questionnaire generation; also hosts the AI RMF bank build |
| `gen-eval-loop/` | Stage 2 harness (generic) |
| `NIST/` | Reference data, profile XLS files, assessment HTMLs |

New scenario for Stage 2 goes in: `gen-eval-loop/examples/csf-questionnaire-fill/`
