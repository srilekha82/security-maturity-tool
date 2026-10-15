You link NIST AI RMF 1.0 subcategories to CIS v8.1 AI companion guide safeguards. You judge from
`data/ai/bank_build/crosswalk_pending.json` and this file only. Do not read PDFs or any other data file.

## Input
`crosswalk_pending.json`: `items` (the 72 subcategories with outcome) and `safeguards` (id and title of every
safeguard that has AI-specific guidance; ids carry the guide prefix: `LLM-`, `MCP-`, `AGENT-`).

## Task
For each subcategory list the safeguards that give relevant evidence for what the outcome asks the org to do: what a
control owner could show an assessor, or what a good practice question would be tagged with. The link is used for
evidence prompts and for tagging (technology rung, usage context, topic). It is not question text.

## Rules
1. Link only when the safeguard's subject matter really supports the outcome (for example MAP 4.1 on third-party and
   open-source component risk links to supply-chain and service-provider safeguards; MEASURE 2.7 on security and
   resilience links to vulnerability, logging and penetration-testing safeguards).
2. Many GOVERN, MAP and MEASURE subcategories link to nothing (bias, fairness, explainability, stakeholder engagement,
   organisational culture). Return an empty list for those. Do not stretch.
3. Prefer 1 to 6 safeguards per subcategory; more only when several guides genuinely apply (the same safeguard in the
   LLM, MCP and AGENT guides counts as separate ids; include each guide that applies).
4. Use only ids that appear in `safeguards`. A script rejects the whole file on any unknown id.

## Output
Write ONE JSON object with all 72 subcategory ids as keys and a list of safeguard ids as the value (empty list
allowed):

```json
{"GOVERN 6.1": ["LLM-15.1", "LLM-15.4", "MCP-15.1"], "MAP 1.1": [], "MEASURE 2.7": ["LLM-7.1", "LLM-8.2"]}
```
