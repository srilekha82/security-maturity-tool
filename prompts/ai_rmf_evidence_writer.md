You write the evidence prompt for each AI RMF question in a question bank: one short line telling an assessor what to
ask the organisation to show for that question. You judge from the input file the command names
(`data/ai/bank_build/evidence_input_<bank>.json`) and this file only. Do not read the banks, the Playbook, the CIS
guides or any other file.

## Input
`items`: per AI RMF subcategory, its `outcome` and the `questions` that have no evidence prompt yet, each with its
`number`, `question_text`, the `cis` safeguards it cites (id: title) and, in the area bank, the `areas` it is asked for
with their impacts (data, access, process, assets, people).

## Write, for every question
One evidence prompt of 1 to 2 short sentences (at most 400 characters) that:
- names the concrete artefacts that would show the practice the question asks about, for this question only: a named
  register, record, report, configuration, log extract, approval, contract clause, procedure and its last use. Fit it
  to the question's areas (an agent question: the agent's identity and permission settings, its action log; a vendor
  AI question: the vendor's terms or DPA, the feature's settings);
- carries what the question itself must not ask, so the question stays short: coverage (which AI systems, areas,
  vendors or teams it covers), how recent the artefact is;
- never repeats the question, never asks a yes / no, never names a vendor or product, never assumes the organisation
  has something (say "if any" where it may not). In particular, an event a well-run organisation may never have had
  (an alert, incident, finding, report, complaint, re-rating, declined vendor feature, deletion request) is always
  asked as "the latest one, if any"; prefer the artefact the practice itself produces (the procedure, the setting,
  the review record) over proof of an event.

Do not write a prompt for a question that is not in the input.

## Output
One JSON object to the file the command names: subcategory id -> question number (as a string) -> evidence prompt.

```json
{"MEASURE 2.8": {"1": "An extract of the AI action log for one agent (identity used, request, approval, result), the list of AI systems and agents it covers, and the log retention setting."}}
```

A script (`record_ai_bank.py evidence`) rejects the whole file on an unknown subcategory or question number, a
question that already has an evidence prompt, or a prompt shorter than 30 or longer than 400 characters.
