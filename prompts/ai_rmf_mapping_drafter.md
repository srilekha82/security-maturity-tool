You map ONE AI area to the NIST AI RMF 1.0. You judge from `data/ai/bank_build/mapping_input_<area>.json` and this file
only. Do not read the Playbook or CIS PDFs, other data files, or any file from a client run.

## Input
- `area`: the AI area (id, name, kind, applies_to, impact, covers). `covers` says what is exposed and what can go wrong.
  `impact` lists the attack areas a failure here hits: data, access, process, assets.
- `functions`: the functions you map: MAP, MEASURE, MANAGE.
- `function_definitions`: the Playbook's own statement of each AI RMF function, including GOVERN.
- `foundation`: GOVERN, and any single subcategory listed with it. It is the foundation: how the organisation works with
  AI (policies, roles, inventory, culture, third parties, how risk management is run). It is asked once for the
  organisation elsewhere, so you never map it to an area (listed subcategories are left out of `subcategories`).
- `subcategories`: per mapped function, every AI RMF subcategory with its outcome and some Playbook suggested actions.
- `cis_candidates`: the CIS safeguards you may cite (id, title, lowest Implementation Group, AI-specific text).
- `rules`: `min_why_chars`, `required_checks` (checks this area must have).

## Task
Go through every subcategory in `subcategories`, one by one, and decide for each whether it checks this area. Do not
stop at the obvious ones (security, privacy, logging, switching off): requirements, intended use, benefits, failing
safely, performance in real conditions, feedback from the people affected and the like count as much. For each of the
three mapped functions, choose the subcategories of that function that check THIS area: a subcategory
whose outcome and suggested actions let an assessor ask how the org handles this area in practice (what it does, who
does it, what evidence exists). A later step writes the questions; you decide only where they land. GOVERN sets the
policies these practices follow; a row here asks whether the practice happens for this area, not whether a policy
exists.
- MAP (context): this area applied to the organisation's systems, processes, assets and data: what it connects to and
  can reach, its components and suppliers, its purpose and limits, the risks and impacts that follow.
- MEASURE (operations: checking): how the area's risks are tested and evaluated (security, reliability, safety,
  privacy, fairness) and monitored in use.
- MANAGE (operations: responding): how the area's risks are prioritised and treated (access control, encryption,
  separation), how it is switched off, how incidents are responded to, rectified and recorded.

## Rules
1. Each row is one mapped function + one subcategory of THAT function. Never a GOVERN row: a policy, role, inventory or
   approval for the area belongs to GOVERN; what is done about the area in practice is MAP, MEASURE or MANAGE (for
   example, granting a tool access is MANAGE, not GOVERN 2.1). There is no target number of rows: add a row for
   every subcategory that really checks this area, and no others. A narrow area may need few rows, a broad one many.
   Do not repeat a function + subcategory.
2. Map only where a question about this area's own practice can be asked. Do not map because a subcategory is important
   in general. A function with no fitting subcategory gets a `no_question` entry with a one-sentence reason instead of
   rows.
3. Meet every entry in `required_checks`: a row on one of its `any_of` subcategories, and where it has `cis_control`,
   that row cites a safeguard of that CIS control.
4. `cis_refs`: ids from `cis_candidates` only, and only safeguards that support this row (evidence an assessor would
   ask for). Prefer the lowest IG that fits; cite every safeguard that supports the row and no others. Look through
   all the candidates before leaving it empty: `[]` only when no candidate supports the row (the evaluator fails an
   empty list when one does).
5. `impact`: the one or more of the area's impacts this row protects (e.g. a MEASURE 2.10 privacy row on source data is
   `data`; a MEASURE 2.7 row on retrieval permissions is `access`). Never an impact the area does not list.
6. `why`: one sentence saying what this subcategory checks about this area.
7. `folded` (optional): when one row's question fully asks what another subcategory of the same area would check (you
   merged them instead of writing two rows), list that subcategory there, e.g. `"folded": ["MAP 2.2"]`. A folded
   subcategory has no row and no question of its own: it is asked and scored through this row, so fold only when the
   row's `why` really covers the folded outcome. When in doubt, write two rows. Leave `folded` out when nothing was
   merged.
8. Do not decide by sector, org size or how any client works. Never invent an id.

## Output
Write ONE JSON object to the file the command names:

```json
{
  "area": "mcp_tools",
  "rows": [
    {"function": "MAP", "subcategory": "MAP 4.1", "cis_refs": ["MCP-2.1"], "impact": ["access"],
     "why": "The MCP servers and tools the AI can call, inside and outside, are identified with what each can reach."},
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
failing row, add a row for each subcategory the evaluator lists as `missing` unless you are sure it does not check
this area (then leave it out; it stays flagged for the person reviewing), and leave correct rows unchanged.
Evaluator `note` entries are for the person reviewing; you need not act on them. When you remove a row and move
its content into another row, list the removed subcategory in that row's `folded`, so a reviewer can see where it
went.
