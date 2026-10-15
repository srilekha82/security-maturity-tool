You are judging CSET questions for a NIST CSF 2.0 question bank. Python has already done everything that
can be decided from the CSET schema. You only see the questions it could not decide. Each item in
`pending_judgements_<domain>.json` lists what it `needs`: any of `domains`, `rewrite`, `fit`.

Judge only from the item's own fields (question text or practice fields, source model, the mapped
subcategory outcomes). Do not read other files. Do not invent facts about any organisation.

## domains  (when `needs` has "domains")
Which sectors can this question be put to? Answer with a list from:
`healthcare`, `finance`, `manufacturing_ot`, `saas_cloud`, `consulting`, `other`, or `["all"]`.

- `["all"]` — a general security practice that any organisation can answer. Most CISA CPG / SSG IT
  practices are this. Use it whenever the wording does not depend on a sector.
- A specific list — the question only makes sense for those sectors: it names sector regulation or
  data (FFIEC, PCI, GLBA, PHI, HIPAA, SCADA, PLC), or uses sector wording ("the institution",
  "patients", "field devices") that a different kind of organisation could not answer as written.
- `other` means "organisations with no particular sector", NOT "any organisation". Never use it as a
  stand-in for general; use `["all"]`.
Give a one-sentence `reason`.

## rewrite  (when `needs` has "rewrite")
The row has no question, only a practice statement (`practice`: security_practice, outcome, scope,
risk_addressed, recommend_action). Write one question a control owner can answer and evidence:
- One or two sentences. Ask whether and how the organisation does this, and who owns it.
- Keep the scope and meaning of the practice. Add no requirement that is not in the practice.
- No yes/no-only questions: ask what exists, who owns it, and how it is evidenced.
If the practice cannot be asked as a question (it is a heading, a note or a pure definition),
set `"rewrite": null`.

A `rewrite` is also needed when the question text itself looks cut off (ends in ":" or ",", or is
very short). Judge only from the text, its category and the mapped outcomes:
- If the text is actually complete, return it unchanged.
- If the intended question is clear from the text and the outcomes, return the completed question.
- If it cannot be recovered without guessing, set `"rewrite": null` (the question is dropped).

## fit  (when `needs` has "fit")  — only for the subcategories in `check_fit_for`
This question maps to many subcategories, so some mappings are probably loose. For each id in
`check_fit_for`, compare the question with that subcategory's outcome (in `mapped_subcategories`):
- `accept` — answering the question would give real evidence for that outcome.
- `reject` — the question is generic, about a different topic, or only loosely related.
Be strict: a question that fits everything fits nothing. Give a one-sentence `reason` for each.

## Output
A JSON object keyed by qid. Include only the keys that item `needs`:
```json
{
  "172": {"reason": "...", "fit": {"GV.RM-01": {"verdict": "accept", "reason": "..."}}},
  "8503": {"reason": "...", "domains": ["all"], "rewrite": "Are all software development ..."}
}
```
`reason` is required whenever `domains` is present. Do not add other keys.
