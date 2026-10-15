You decide which of the 72 NIST AI RMF 1.0 subcategories each AI RMF question bank can ask about. You judge from
`data/ai/bank_build/applicability_pending.json` and this file only. Do not read the Playbook or CIS PDFs, other data
files, or any file from a client run.

## Input
`applicability_pending.json` has `definitions` (what producer and consumer mean), `categories` (per bank: `producer`, `consumer`; each category has an id, a topic and
what it `covers`) and `items` (each of the 72 subcategories with its outcome and the Playbook suggested actions).

## Task
For every item, for each bank, list the category ids for which the subcategory's outcome and suggested actions can
produce a practice-revealing question for an org of that role (a question about what the org does, who owns it and what
evidence exists). A subcategory applies to a bank if and only if its list for that bank is non-empty.

## Rules
1. Roles are defined in `definitions`: a producer builds or distributes models; a consumer uses AI (including
   fine-tuning an existing model for its own use). The two are different question sets, not tiers: an
   outcome about training-data provenance has no consumer question, while one about vetting an embedded vendor feature
   has no producer question. Many subcategories apply to both.
2. Map to the category that best fits; most subcategories map to 1 or 2 categories. Map to 3 or more only when the
   suggested actions truly span them.
3. Do not map because a subcategory is important. Map only if a question about the org's own practice can be written
   from the suggested actions. Outcomes that only restate a duty that does not apply to the role map to nothing for that
   bank (empty list).
4. Do not decide by sector, by org size or by how Caizin or any client works. Sector is not an input.
5. Bias, fairness and explainability outcomes (MEASURE 2.x and related) belong to the producer category
   `fairness_safety_eval`; for consumers they apply only through how outputs are used (`use_context_impact`).
6. Give one sentence of `reason` per subcategory that names why each bank does or does not apply.

## Output
Write ONE JSON object with all 72 subcategory ids as keys (nothing else), to the file the command names:

```json
{
  "GOVERN 1.1": {
    "producer": ["gov_accountability"],
    "consumer": ["gov_accountability"],
    "reason": "Legal and regulatory duty applies to builders and users alike."
  },
  "MAP 3.3": {
    "producer": ["intended_use_impact"],
    "consumer": [],
    "reason": "Scoping of intended use is the builder's duty; a consumer's use context is covered under MAP 1.x."
  }
}
```

A script validates it (all 72 ids, category ids exist for that bank, a reason on each) and rejects the whole file if
anything is wrong; nothing is stored until it passes. Never invent a category id.
