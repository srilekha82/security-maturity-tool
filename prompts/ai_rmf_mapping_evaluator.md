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
3. The `impact` matches what the row protects (data, access, process, assets).
4. The `why` is specific to this area.
5. A `folded` list (optional) names subcategories this row also covers. Fail it when the row does not really cover
   them, or when a folded subcategory would be clearer as a row of its own.

## Check what is missing
6. An obvious subcategory for this area that no row covers (for example: MEASURE 2.7 security for an access area,
   MEASURE 2.10 privacy for a data area, MANAGE 2.4 switching off for something that acts). Report it as a failure of
   the function, with `subcategory` null and the reason naming what is missing.
7. A `no_question` entry that is not justified.

Do not re-check ids, required checks or formats; a script does that. Fail when unsure. One line per failure.

## Output
Write ONE JSON list to the file the command names, failures only (`[]` if everything passes):

```json
[
  {"function": "MEASURE", "subcategory": "MEASURE 2.11", "reason": "Fairness is not something tool credentials can be checked for."},
  {"function": "MANAGE", "subcategory": null, "reason": "Missing MANAGE 2.4: revoking a tool's access when it misbehaves."}
]
```
