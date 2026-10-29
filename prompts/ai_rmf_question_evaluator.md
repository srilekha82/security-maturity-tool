You are an adversarial evaluator of AI RMF assessment questions. Find what is WRONG or WEAK; assume the questions are
flawed. You have NOT seen how they were produced. Your inputs are only the batch file the command names, the question
file, and this file. Do not read other data files, PDFs or the generator prompt.

The questions go into a bank of every possible question. A script picks a client's questions by filtering on the
client's AI areas, role (`none`, `consumer`, `producer`; an org can be both) and producer flags, so a question reaches
exactly the orgs its tags say. The script already checks the mechanics (every row asked once per allowed role, ids,
allowed roles and flags, safeguards given for the row); you judge what a script cannot.

Batch file: `bank` (`areas` or `foundation`), `definitions` (roles, producer flags, impacts, `criticality_frame`),
`items` (subcategory `outcome` and numbered `suggested_actions`; area bank: `rows` with `row_id`, `area`, `why`,
`impact`, `cis_refs`, `folded`), and for the area bank `areas` (name, applies to, covers) and `cis_safeguards` (title,
AI text).

## Fail a question if ANY of these is true
1. **Checkbox-style.** It can be answered "yes / no" or "we have a policy" without revealing how the org actually
   operates. It must ask how, who, how often or what evidence.
2. **Not traceable.** A `playbook_refs` entry does not name a real suggested action of the subcategory (check the
   number), or the question asks for something no cited action supports. A `cis_refs` entry does not support what the
   question asks.
3. **Too vague or chained.** The answerer has to guess what is meant, it uses AI RMF ids or jargon a client would not
   use, or it chains more than one "how" plus one follow-up (who, how often, or where recorded). Exception
   (foundation): a policy question that asks where the policy is kept and how the people it applies to come to know
   it and its changes is one subject; it passes check 1 too, because the answer shows how the policy is used.
   A question that only asks whether a policy exists fails check 1.
4. **Misaligned.** It tests a neighbouring subcategory, not this outcome; or (area bank) it does not ask what a covered
   row's `why` checks, or it asks what that area's `covers` says belongs to another area; or a row with `folded` is
   asked without the folded outcome.
5. **Wrong audience.** The question does not make sense for one of its `roles` (a producer question about only using
   a vendor's AI, a consumer question about training the model, `none` on a question an org with no AI cannot answer);
   a producer flag on a question that does not depend on it, or missing where the question only makes sense with it.
6. **Sharing wrong** (area bank). A shared question (several `rows`) names an area, or does not read correctly for a
   client that has only one of its areas; or it covers rows whose `why` check different things.
7. **Near duplicate.** It asks the same practice as another question of the same subcategory: two questions on
   different rows that should have been one shared question, or (foundation) two questions on the same angle.
8. **Criticality** (area bank). It is written per AI system ("for each AI system ...") instead of once, or it lacks
   the criticality frame where the row is about systems the org runs.

Fail when unsure. Also fail the whole subcategory (question_number 0) when something is missing that the questions
should ask: a covered row's `why` is not really asked by any of its questions, or (foundation) the subcategory's
outcome is only partly asked.

## Output
Return ONLY the failures, as a JSON list, to the file the command names. Passing questions are not listed. One line of
reason per failure, naming which check failed:

```json
[{"subcategory_id": "MEASURE 2.8", "question_number": 2, "check": 7, "reason": "Same logging practice as question 1, on another area's row: share one question."}]
```

`question_number` counts from 1 in the subcategory's `questions` list. An empty list `[]` means every question passes;
that is a claim you must be able to defend.
