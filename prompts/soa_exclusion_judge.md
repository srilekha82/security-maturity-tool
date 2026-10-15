You are reading ISO 27001 Statement of Applicability (SoA) rows for a CSF 2.0 questionnaire. Python has
already parsed the SoA and decided everything it can. `soa_pending.json` lists only the controls it could
not decide: controls excluded in the SoA, or whose "applicable" cell held an unrecognised value.

Judge only from each item's own fields (`applicable_raw`, `exclusion_reason`). Do not read other files.
Do not invent facts about the organisation.

## For every item
Give a one-sentence `reason`.

## If `applicable_recognised` is false
The cell held something other than a plain yes/no (for example "Partial", "Y - phase 2", "TBD").
Set `"applicable": true` or `false` from what the cell and reason say. If you cannot tell, use `false` and
class it `unclear` below (a control we cannot confirm is applicable is asked in full).

## If the control is (or you set it to) not applicable
Set `exclusion_class`:
- `covered_elsewhere` — the reason says the control is met by another control, a parent policy, a
  provider or a shared service ("covered by ...", "handled by the parent company", "see A.5.1").
- `not_relevant` — the reason says the control does not apply to the organisation's business or
  environment ("no physical premises", "no software development").
- `unclear` — the reason is blank, boilerplate, or could mean either.

Be conservative: when torn between `covered_elsewhere` and anything else, choose the other class.
`covered_elsewhere` makes the question lighter, so it needs an explicit statement that something else covers it.

## Output
A JSON object keyed by `control_id`, written to `<run_dir>/soa_judgements.json`:
```json
{
  "Annex A Controls: 7.2": {"exclusion_class": "not_relevant", "reason": "Remote-only company, no offices."},
  "Annex A Controls: 5.9": {"applicable": false, "exclusion_class": "unclear", "reason": "Cell says 'TBD'."}
}
```
`applicable` only for items whose `applicable_recognised` was false. Do not add other keys.
