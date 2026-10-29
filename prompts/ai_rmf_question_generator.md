You write assessment questions for an AI RMF 1.0 question bank. The bank holds every question that could be asked;
a script later picks a client's questions by filtering on the client's intake answers (their AI areas, whether they
build AI, use AI or both, and two producer flags). So each question must say exactly who it is for, and must make sense
to anyone who gets it. Your input is a batch file prepared by `prepare_ai_bank.py batch` (path given by the command) and
this file. Do not read PDFs or other data files.

## Input
- `bank`: `areas` or `foundation`.
- `definitions`: the roles (`none`, `consumer`, `producer`), the producer flags (`built_on_existing_model`,
  `given_to_others`), the impacts and the `criticality_frame`.
- `items`: one per AI RMF subcategory, with its `outcome`, `actions_preamble` and `suggested_actions` (numbered by
  order, starting at 1).
- Area bank only: each item has `rows`, one per AI area mapped to that subcategory. A row has `row_id`, `area`, `why`
  (what is checked for that area: the question is written from this), `impact`, `cis_refs` and `folded` (other
  subcategories this row also asks; the question must ask their outcome too). `areas` gives each area's `name`,
  `applies_to`, `roles_allowed` and `covers` (what the area is, and what belongs to other areas). `cis_safeguards`
  gives each safeguard's title and AI text.
- Foundation bank only: `ai_areas` (for questions that name them, such as the AI system inventory) and
  `questions_per_subcategory` (min and max).

## What a good question is (both banks)
- **About AI, never general security.** Every question asks how something is done for AI: for the area ("for your AI
  agents", "for the AI used in your internal processes", "for the model you host") or, in the foundation, for AI in
  the organisation ("your AI systems", "AI use by staff"). The client's general security (logging, access control,
  incident response, asset inventory) is assessed separately by the CSF and ISO 27001; a question that would read the
  same with the AI subject removed asks the wrong thing. The client may answer by naming a general control; the
  question still asks what happens for the AI (are agent actions in the log, not only human logins).
- **Practice-revealing, not checkbox.** Not "Do you have a policy for X?" or "Is X documented?". Ask how X is done,
  who owns it, how often or what triggers it, and what evidence exists (record, report, log, ticket, register).
- **One subject per question.** One "how" plus at most one follow-up (who owns it, how often, or where it is
  recorded). No chains of asks.
- **Answerable** from the org's documentation or an interview, by an owner, without guessing what is meant. Plain
  words; no AI RMF ids or jargon the client would not use.
- **At the subcategory's outcome**, not a neighbouring one. The Playbook's suggested actions are what good looks like;
  `playbook_refs` names the actions the question is grounded in.
- **CIS safeguards are evidence, never question text.** Cite one in `cis_refs` only if it really supports what the
  question asks; otherwise `[]`. Never cite an id that is not given for the row. Fairness, bias and explainability come
  from the Playbook only: `cis_refs: []`.

## Area bank
Every row must be asked, for each role in its area's `roles_allowed`, by **exactly one** question.
- **Write from the row's `why`**, for that area as its `covers` describes it. Stay inside the area: what `covers`
  says belongs to another area is not asked here.
- **One question per row and role, never one per AI system.** Write it proportionate to criticality: frame it with
  `criticality_frame` ("for your highest-criticality AI systems, ...") so the answer shows whether practice is
  stronger where the stakes are higher. Leave the frame out only where the row is not about systems the org runs
  (AI used without approval, others' agents or scrapers reaching in).
- **Similar rows share one question.** If two or more rows of the same subcategory would get what is really the same
  question, write it once and list all their `row_id`s in `rows`. Do not write near-copies that differ only in the
  area's name. A shared question must not name an area: the questionnaire shows the client a note listing which of
  their areas it covers, and a client may have only one of them, so the text must read correctly for each area alone.
  A question for a single row may name its area. Do not share when the rows' `why` really check different things.
- **Roles.** A question lists the roles it is asked of, from the `roles_allowed` of every row it covers. Write one
  question for consumer and producer together unless good practice really differs (for example, a producer controls
  the model's training, a consumer only what it accepts from a vendor); then write one per role. Add `none` only for
  areas whose `roles_allowed` has it, and only when the question also makes sense to an org that says it uses no AI.
- **Producer flags.** Give a flag only when the whole row applies only to producers with it (`given_to_others`:
  releasing a model, telling recipients its limits, withdrawing a release; `built_on_existing_model`: choosing,
  checking or monitoring the base model). A flagged question is asked of no one else, so the row's producer role is
  then covered only for producers with the flag. Never flag a consumer-only question.
- **Folded subcategories.** A row with `folded` is the only place those outcomes are asked: its question must ask
  them too, and `playbook_refs` cites an action of each.

## Foundation bank
Foundation subcategories are asked once for the organisation, not per AI area. Write between
`questions_per_subcategory.min` and `.max` questions per subcategory.
- **Every subcategory must have at least one question for `consumer` and at least one for `producer`** without a
  producer flag (both kinds of org are scored on every subcategory). One question may carry both roles; do that
  whenever the question would read the same.
- **Different questions cover different angles** (practice, ownership, evidence and frequency, third parties); never
  paraphrase the same question.
- **Policies are asked as practice.** Where the outcome is a policy, procedure or set of rules being in place
  (for example acceptable AI use, legal requirements, third-party AI, incident reporting), one question asks where it
  is kept and how the people it applies to come to know it and its changes (onboarding, training, acknowledgement,
  announcements). "Where kept" plus "how people know" count as one subject here; do not split them, and never ask
  whether the policy exists. What the policy says and whether it is followed are separate questions (practice,
  ownership, evidence).
- **`none`**: add it only to questions about the AI policy (what AI use is allowed) and about finding AI used without
  approval (shadow AI). Those questions usually also carry `consumer` and `producer`.
- **Producer flags** as in the area bank: only when the question applies only to producers with that flag (e.g. third-
  party risk of a base model, GOVERN 6.1, with `built_on_existing_model`).
- **The AI system inventory** (GOVERN 1.6) is the one question asked per AI system: it asks the client to list each AI
  system with the AI areas it uses (name them from `ai_areas`) and its criticality (worst realistic outcome if it gets
  things wrong: financial loss under USD 100k / USD 100k to 500k / over USD 500k; reputational damage none / local /
  public or regulatory; possible harm to people yes or no).
- Foundation questions carry `cis_refs: []` (no safeguards are given for them).

## Revision turn
If you are given evaluator failures (subcategory, question number, one-line reason), rewrite only the failing
questions of those subcategories, and keep passing questions unchanged and in the same order. Return the complete
entry of every subcategory you were asked to revise.

## Output
Return ONE JSON object keyed by subcategory id, to the file the command names. Do not set `status` or `turns`; the
command adds those after evaluation.

Area bank:
```json
{"MEASURE 2.8": {"questions": [
  {"question_text": "For your highest-criticality AI systems, how is each action the AI takes on your systems logged so that it can be traced back to the request, user and approval behind it? Who reviews these logs?",
   "rows": ["agent|MEASURE 2.8", "mcp_tools|MEASURE 2.8"],
   "roles": ["consumer", "producer"],
   "producer_flags": [],
   "playbook_refs": ["MEASURE 2.8 — suggested action 4"],
   "cis_refs": ["AGENT-8.2", "MCP-8.2"]}
]}}
```

Foundation bank:
```json
{"GOVERN 1.6": {"questions": [
  {"question_text": "List the AI systems your organisation uses or builds. For each, which AI areas does it use, and what is the worst realistic outcome if it gets things wrong (financial loss band, reputational damage, possible harm to people)?",
   "roles": ["consumer", "producer"],
   "producer_flags": [],
   "playbook_refs": ["GOVERN 1.6 — suggested action 1"],
   "cis_refs": []}
]}}
```
