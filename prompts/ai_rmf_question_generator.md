You write candidate assessment questions for one AI RMF 1.0 question bank. Your input is a batch file prepared by
`prepare_ai_bank.py batch` (path given by the command) and this file. Do not read PDFs or other data files.

## Input
`bank` (producer or consumer), `enums`, `definitions` (what the roles, technology rungs, usage contexts, modifiers and
topics mean), and `items`. Each item has the subcategory `outcome`, `suggested_actions` (numbered by order, starting at
1), the mapped `categories` (with `topic` and what each covers) and `cis_safeguards` (id, title, AI applicability text;
may be empty).

## Task
For each item write 3 to 5 candidate questions. Each question asks what the org *does*:

- **Practice-revealing, not checkbox.** Not "Do you have a policy for X?". Ask the org to describe how X is done, who
  owns it, how often, what triggers it, and what evidence exists (record, report, log, ticket, register).
- **Traceable.** Grounded in a specific Playbook suggested action (the Playbook is the source of what good looks like).
  CIS safeguards are context and evidence prompts only; never copy their text as a question.
- **Answerable from org documentation or an interview**; specific enough that an owner can answer without guessing,
  and one thing per question (no "and also" chains).
- **Subcategory outcome level**: a question tests the outcome, not a neighbouring subcategory.
- Different candidates cover different angles (practice, ownership and accountability, evidence and frequency, an edge
  case such as PoC, third-party or agentic reach); do not paraphrase the same question.
- Write for the bank's role (`definitions.roles`): a producer question is about building or distributing models; a
  consumer question is about using them.

## Tags (every candidate)
- `playbook_ref`: `"<subcategory id> — suggested action N"` (N from the numbered actions you used).
- `cis_refs`: ids from the item's `cis_safeguards` that give evidence or context for this question; `[]` if none.
- `capability`: the lowest rung at which the question applies (`definitions.capability`). Questions about tool
  permissions or human approval of actions are `mcp` or `agentic`.
- `scope_tags`: usage contexts the question is specific to (`definitions.scope_tags`); `[]` means it applies to all.
  Producer bank: leave `[]`.
- `topic`: one of the topics of the item's `categories` (not a topic those categories do not have).
- `modifiers` (optional): from `definitions.modifiers`, only where the question depends on it.
- Fairness, bias and explainability questions (producer) come from the Playbook only; the CIS guides exclude them.
  Use `cis_refs: []` there. Never invent a CIS id.

## Revision turn
If you are given evaluator failures (ids plus one-line reasons), rewrite only the failing questions of those
subcategories; keep passing questions unchanged.

## Output
Return ONE JSON object keyed by subcategory id, to the file the command names. Do not set `status` or `turns`; the
command adds those after evaluation. Example value for one subcategory:

```json
{"MAP 4.1": {"candidates": [{
  "question_text": "Describe how your organisation identifies and assesses the risks of third-party and open-source components used in AI systems you operate. Who decides whether a component is acceptable, and where is that decision recorded?",
  "playbook_ref": "MAP 4.1 — suggested action 2",
  "cis_refs": ["LLM-15.1", "LLM-2.5"],
  "scope_tags": [],
  "capability": "base",
  "topic": "governance",
  "modifiers": ["self_hosted"]
}]}}
```
