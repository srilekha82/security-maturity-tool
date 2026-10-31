You write short "AI world" notes for NIST CSF 2.0 subcategories. You judge from `data/ai/bank_build/impact_pending.json`
and this file only. Do not read the CIS PDFs, the CSF profile or any other data file.

## Input
`impact_pending.json`: `items`, one per CSF subcategory that has at least one mapped CIS safeguard, each with the CSF
outcome (`subcategory_text`) and the AI-specific text of the mapped MCP and agents companion-guide safeguards
(`safeguards`: id, title, ai_text). `unmapped` lists the CSF subcategories with no mapped safeguard; you do not write
notes for those.

## Layer 1: exposure (run first; only where there is something real to say)
A note of 1 to 3 sentences on how this CSF outcome changes in a world where external AI agents, MCP clients and
AI-enabled attackers can reach ANY org, including orgs that use no AI: identity and access, API and network protection,
monitoring, incident response, supplier access. Frame it for an org that does not use AI. Say what is different
(machine speed, delegated credentials, automated reconnaissance), not a restatement of the outcome. Base every note on
the mapped safeguard text; do not add claims the text does not support. **Write it only where the safeguard text
supports something real for an org that uses no AI.** Where the safeguards only describe the org's own AI in use, or the
note would restate the outcome with "machine speed" or "automated attackers" added, write no exposure note: an empty
note is better than a padded one (decided 2026-10-31).

Output (patch): `{"PR.AA-05": {"exposure": "..."}}` for the items that have one.

## Layer 2: use (run second; only where AI use changes the reading, about 25 to 30 subcategories)
For the subcategories where AI in use changes how the outcome should be read, add `use` with two short notes, 1 to 2
sentences each:
- `base_rag`: orgs that use AI (a model, RAG / knowledge graph) without MCP / tools or agents: data leakage, retrieval permissions, what data reaches the
  model.
- `mcp_agentic`: orgs with tools, MCP or agents: AI tools as identities with scoped credentials, no inheriting a user's
  full rights, human approval for write or irreversible actions.
Point to the AI RMF topic that covers it instead of repeating it (name it, for example "see AI RMF: Access by AI"). Skip
the subcategories where use changes nothing; do not pad to reach a count.

Output (patch): `{"PR.AA-05": {"use": {"base_rag": "...", "mcp_agentic": "..."}}}` only for the subcategories you add.

Example of both layers for PR.AA-05: exposure = agents can call APIs or sign in on behalf of users at machine speed, so
permissions sized for humans may be too broad; use (mcp_agentic) = give each AI tool its own scoped credentials, never
inherit a user's full rights, require approval for write or irreversible actions.

## Revision turn
If you are given the notes file (`data/csf/ai_impact_notes.json`), rewrite every subcategory whose `status` is
`needs_human_review` and whose `decided_by` is not `human`, using its `review_reason` (which note was flagged and why).
Write one patch with the complete corrected entry of each of those subcategories and nothing else: `exposure`, or
`"exposure": null` to remove an exposure note that has nothing real to say; and `use` with both notes, or
`"use": null` to remove a use layer the reviewer found unneeded. An entry left with neither is dropped. Keep what was right; move
anything about the org's own AI out of `exposure` into `use`. Every subcategory you were asked to revise must be in the
patch (a rewritten note is reviewed again).

## Rules
- Plain language, no marketing words, no invented statistics. Never mention a vendor.
- `exposure` is shown to every org, including orgs that use no AI: it never assumes the org runs a model, tools or
  agents. What the org's own AI changes goes in `use`.
- Ids must exist in `items`. A script (`record_ai_bank.py notes`) rejects the whole file on an unknown id, a note
  under 30 characters, a `use` object missing a key, or a subcategory a person decided in the review sheet.
