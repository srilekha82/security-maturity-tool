You map ONE AI area to the NIST AI RMF 1.0. You judge from `data/ai/bank_build/mapping_input_<area>.json` and this file
only. Do not read the Playbook or CIS PDFs, other data files, or any file from a client run.

## Input
- `area`: the AI area (id, name, kind, applies_to, impact, covers). `covers` says what is exposed and what can go wrong.
  `impact` lists the attack areas a failure here hits: data, access, process, assets.
- `functions`: GOVERN, MAP, MEASURE, MANAGE.
- `subcategories`: per function, every AI RMF subcategory with its outcome and some Playbook suggested actions.
- `cis_candidates`: the CIS safeguards you may cite (id, title, lowest Implementation Group, AI-specific text).
- `rules`: `min_why_chars`, `required_checks` (checks this area must have), `org_wide` (subcategories asked once for
  the whole org; map one only if this area adds its own angle).

## Task
For each of the four functions, choose the subcategories of that function that check THIS area: a subcategory whose
outcome and suggested actions let an assessor ask how the org handles this area (what it does, who owns it, what
evidence exists). A later step writes the questions; you decide only where they land.
- GOVERN: owned, inventoried, approved, policies and roles for this area.
- MAP: what the area connects to and can reach, its context and impact.
- MEASURE: how the area is tested and evaluated (security, reliability, safety, privacy, fairness) and monitored.
- MANAGE: how its risks are treated (access control, encryption, separation), switched off, responded to and recorded.

## Rules
1. Each row is one function + one subcategory of THAT function. There is no target number of rows: add a row for
   every subcategory that really checks this area, and no others. A narrow area may need few rows, a broad one many.
   Do not repeat a function + subcategory.
2. Map only where a question about this area's own practice can be asked. Do not map because a subcategory is important
   in general. A function with no fitting subcategory gets a `no_question` entry with a one-sentence reason instead of
   rows.
3. Meet every entry in `required_checks`: a row on one of its `any_of` subcategories, and where it has `cis_control`,
   that row cites a safeguard of that CIS control.
4. `cis_refs`: ids from `cis_candidates` only, and only safeguards that support this row (evidence an assessor would
   ask for). Prefer the lowest IG that fits; cite every safeguard that supports the row and no others; `[]` when none
   fits (governance rows often have none).
5. `impact`: the one or more of the area's impacts this row protects (e.g. a MEASURE 2.10 privacy row on source data is
   `data`; a MEASURE 2.7 row on retrieval permissions is `access`). Never an impact the area does not list.
6. `why`: one sentence saying what this subcategory checks about this area.
7. Do not decide by sector, org size or how any client works. Never invent an id.

## Output
Write ONE JSON object to the file the command names:

```json
{
  "area": "mcp_tools",
  "rows": [
    {"function": "GOVERN", "subcategory": "GOVERN 1.6", "cis_refs": ["MCP-2.1", "MCP-2.3"], "impact": ["access"],
     "why": "Every MCP server and tool the AI can call is inventoried with an owner and an approval."},
    {"function": "MEASURE", "subcategory": "MEASURE 2.8", "cis_refs": ["MCP-8.2"], "impact": ["access"],
     "why": "Tool calls are logged with the credentials used, so actions can be traced and accounted for."}
  ],
  "no_question": [
    {"function": "MAP", "reason": "..."}
  ]
}
```

A script checks the whole file (ids, functions, candidates, impacts, required checks) and rejects it if anything is
wrong; nothing is stored until it passes.

## Revision turn
If you are given the evaluator's failures, return the complete corrected file in the same format: fix or remove each
failing row, add what the evaluator says is missing, and leave correct rows unchanged.
