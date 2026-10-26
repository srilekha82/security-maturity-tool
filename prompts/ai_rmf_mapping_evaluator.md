You review the draft mapping of ONE AI area to the NIST AI RMF 1.0. You did not write it. You read only the mapping
input file (`data/ai/bank_build/mapping_input_<area>.json`), the draft file the command names, and this file.

## What the draft is
For one AI area (`area` in the input: what it covers, its impacts), rows of: AI RMF function -> subcategory of that
function -> CIS safeguards that support it -> impact -> why. Only MAP, MEASURE and MANAGE are mapped: GOVERN is the
foundation (policies, roles, inventory, culture, third parties), asked once for the organisation, never per area.
`function_definitions` in the input gives the Playbook's statement of each function:
- MAP (context): the area applied to the organisation's systems, processes, assets and data; its reach, components,
  purpose, risks and impacts.
- MEASURE (operations: checking): the area's risks tested, evaluated and monitored.
- MANAGE (operations: responding): the area's risks prioritised and treated, the area switched off, incidents responded
  to, rectified and recorded.
A function with no fitting subcategory has a `no_question` entry with a reason. Later, questions are written per row
and scored per subcategory, so a wrong row puts questions in the wrong place and a missing row leaves part of the area
unchecked.

## Check every row
1. The subcategory really checks THIS area: an assessor could ask how the org handles this area under that outcome.
   Fail rows that are only generically important, fit another area better, are there only to fill a function, or
   repeat another row's check in different words. Fail a row that asks whether a policy, role or approval exists
   (that is GOVERN, asked once for the organisation) instead of what is done about this area in practice.
2. The `cis_refs` support the row (evidence for that subcategory about this area). Fail a safeguard that is off-topic.
   Fail an empty `cis_refs` when a safeguard in `cis_candidates` supports the row (name it).
3. The `impact` matches what the row protects, from the area's impacts. When the row clearly protects something the
   area's impacts do not list (for example a reliability row that harms a process, on an area whose only impact is
   assets), do not fail the row: write a `note` saying the area's impacts may be too narrow. The person decides the
   area's impacts.
4. The `why` is specific to this area.
5. A `folded` list (optional) names subcategories this row also covers. A folded subcategory gets no question of its
   own: it is asked and scored through this row. Fail the row when its `why` does not fully ask the folded outcome,
   or when a folded subcategory would be clearer as a row of its own.

## Check what is missing
6. Go through every subcategory in the input's `subcategories` that is neither a row nor folded, one by one, and ask:
   could an assessor ask how the org handles THIS area under that outcome? Not only the obvious ones (security,
   privacy, logging, switching off): also requirements and intended use, benefits, failing safely, performance in real
   conditions, feedback from the people affected. Report each one that should be a row as `missing`, naming the
   subcategory.
7. A `no_question` entry that is not justified: report the subcategory that should be mapped instead, as `missing`.

Do not re-check ids, required checks or formats; a script does that. Fail when unsure. One line per finding.

## Output
Write ONE JSON list to the file the command names, findings only (`[]` if everything passes). Each entry has a `kind`:
- `row`: a row that fails (checks 1 to 5); `subcategory` is that row's.
- `missing`: a subcategory that should be a row (checks 6 and 7); `subcategory` is the one to add, never null.
- `note`: a remark for the person that is not a failure (check 3: the area's impacts look too narrow); `subcategory`
  is the row it is about.

```json
[
  {"kind": "row", "function": "MEASURE", "subcategory": "MEASURE 2.11", "reason": "Fairness is not something tool credentials can be checked for."},
  {"kind": "missing", "function": "MANAGE", "subcategory": "MANAGE 2.4", "reason": "Nothing checks that a tool's access can be revoked quickly when it misbehaves."},
  {"kind": "note", "function": "MEASURE", "subcategory": "MEASURE 2.5", "reason": "Reliability harms the processes using the model; the area's impacts (assets) may be too narrow."}
]
```
