# Design rules for caizin-csf-tool

Read this when you change the design: add or change a script, prompt, command or data file, or add a track or stage. It is
not needed to run the flows (`CLAUDE.md` covers that). `README.md` explains the flow and the file layout.

## Design rules (apply to every script, prompt and command)
1. **Scripts never decide.** They parse, join, look up, validate, format, hash and write. A script that cannot settle an
   item writes a `pending_*.json` and exits 2; it never guesses. Judgement goes to an agent.
2. **Agents see only the pending items,** as compact JSON a script prepared. Never hand an agent a PDF, a full bank or a
   crosswalk. Parse sources into JSON first.
3. **Agents return patches, not full lists.** Output tokens are the expensive ones. The agent returns only the entries it
   changed (or only new entries); a script validates and merges them.
4. **A recording script is the only door for agent output.** The agent hands in a file; the script validates the WHOLE
   file, rejects it if anything is wrong (exit 1, nothing stored), otherwise stores it and writes a write-once record
   (model, prompt hash, input hash, output snapshot). The contract lives once, in `audit.record_agent_output`; a recording
   script supplies only its validator and its store. CSF: `record_judgements.py`. AI RMF: `record_ai_bank.py`
   (mapping, questions, notes), and `record_judgements.py log --base --patch` for patch steps.
5. **Everything is audited.** Every script calls `scripts/audit.py` (`begin`, then `finish` / `fail` / `pending`), which
   appends to the folder's `audit.jsonl`. Do not invent another logging scheme. Use `audit.write_once_record` for
   write-once records.
6. **Policy and content live in data files, not code.** Max questions per type, scope rules, categories, definitions,
   evidence hints, expected counts: `data/csf/*.json`, `data/ai/*.json`; facts both tracks share (intake menus, domains,
   certifications, question types) in `data/common/intake_options.json`. Changing a rule means editing JSON. Keep each
   constant in one place only: scripts import shared facts from `scripts/options.py` (which reads those files) and
   paths from `scripts/paths.py`; a script never defines its own copy of a domain list, function order or bank name.
7. **Evaluators run in a fresh context** (a subagent) with only the files they need, and return only the failing ids with
   a one-line reason. Fail when unsure. This includes the questionnaire assessors (`/assess-questionnaire` starts one
   subagent per draft); an assessor is never the same conversation that generated the draft.
8. **Few scripts, small files, one job each.** Reuse by importing a shared helper when the logic is the same; do not
   copy it, and do not merge scripts that do different jobs. Add a script only for a genuinely new deterministic job, and
   do not split one job across scripts unless a step can pause for an agent. Add a command only for a repeated step.
9. **Handoff by files.** Each stage reads and writes a validated file and passes paths, not content. Print one summary
   line on success; keep detail in a file read only on failure. The intake is saved by `scripts/intake.py` as
   `intake.json` and `ai_usage.json` in the run folder; later steps read those files and never ask or pass the answers
   again. The intake is asked as numbered choices; the script, not the agent, turns numbers into values.
10. **Prompts and docs stand alone.** A prompt carries its own rules; it does not point to a design document. Shared
    definitions (AI areas in `data/ai/ai_areas.json`; roles, producer flags and impacts in `data/ai/question_rules.json`)
    reach agents through the files scripts prepare.

## AI RMF track: rules that outlast any design note
- **Scope is how AI is used, not sector or certifications.** Sector never changes which questions are asked. It sets a
  severity floor for the priority of findings (healthcare and manufacturing / OT: loss of life is possible) and
  decorates the report. The model (AI areas -> attack areas -> AI RMF function -> subcategory) is in
  `AI_RMF_Mapping_Sheet_Design.md`; the AI areas are decided by a person in `data/ai/authoring/ai_areas.xlsx`. The
  usage profile is: AI in use (`none` / `some` / `unsure`), role (`consumer` / `producer` / `both`, asked), for a
  producer whether the model is built on an existing model and given to others, the client's AI areas (ticked in two intake menus, plus
  the automatic ones in `scope_rules.json` `ai_area_rules`), and engagement flags (CSF assessment done, ISO 27001 held,
  ISO 42001 held). Captured once per engagement by
  `intake.py` in `runs/<Org>_<date>/ai_usage.json` (with `intake.json` for org, domain and certifications); CSF steps, AI
  RMF steps and the XLS writer all read those files. `iso27001_held` is derived from the certifications, never typed twice.
- **One questionnaire for the client.** `/generate-questions` asks the intake once, runs the CSF track and the AI RMF
  track from the same answers and writes ONE `questionnaire.xlsx` with two sheets (CSF, AI RMF). The two tracks are
  internal; the client does not see a separate AI deliverable. In Stage 2 the answers from the two sheets become two
  profile XLS files (CSF profile, AI RMF profile), which feed the two HTML reports.
- **`unsure` is asked as a consumer and as an org with no AI** (`scope_rules.json` `client_roles`: the questions discover
  what AI is used). **`none` gets only the questions tagged `none`** (AI policy, shadow-AI discovery) and the invisible
  AI usage area. The AI RMF XLS is always the 72-subcategory schema.
- **Two banks, foundation and areas, hold every possible question; selection is a filter.** The foundation bank holds
  questions per foundation subcategory (GOVERN and `mapping_rules.json` `foundation.subcategories`), the area bank
  questions per mapping row (a question may stand for several rows of the same subcategory, and then names no area).
  Every question carries the roles it is asked of (`none` / `consumer` / `producer`) and any producer flags
  (`question_rules.json`); `record_ai_bank.py questions` checks that every row is asked exactly once per role its area
  allows. `build_ai_questions.py` picks a client's questions by role, producer flags and AI areas only; it never
  ranks or rewrites. Area questions are asked once, proportionate to criticality, never per AI system. Question types
  are assigned at engagement time; every AI question is `full_discovery` until the per-row gap rule (a row's CIS
  safeguards mapped to CSF subcategories the client was assessed on) is built. ISO 42001 coverage is not used until
  its crosswalk is verified.
- **Question content:** practice-revealing (how, who, how often, what evidence), never checkbox ("do you have a policy").
  The Playbook's suggested actions are the source of what good looks like. CIS companion guides give the safeguards a
  question may cite as evidence, never question text. A policy is asked as practice: where it is kept and how people
  come to know it. Fairness, bias and explainability come from the Playbook only.
- **Sources for the banks:** the Playbook and the three CIS companion guides only. The CIS to CSF mapping is used only for
  the CSF AI impact notes and (to build) the per-row gap rule. OWASP LLM Top 10 is not a source.
- **CIS safeguard ids are read as text.** The CIS xlsx files store them as numbers, so 4.10, 8.10 and 16.10 collapse into
  4.1, 8.1 and 16.1. The guide tables also drop IDs: rebuild from control number and row order.
- **Rebuild only when a source changed.** A bank (CSF or AI) is rebuilt only if it is missing or incomplete, or a source file
  it was built from changed (CSF: the CSET migration SQL; AI: the Playbook, the CIS guides, the CIS to CSF mapping). Editing a
  prompt or `question_rules.json` never starts a rebuild by itself; it only marks the stage stale in the report.
- **Freshness gate:** `check_freshness.py --ai-bank` compares the SHA-256 of the current AI source files with the hashes
  each output records about its own inputs (parse, banks, notes); a bank must also be complete (the area bank written
  for the mapping rows as they are now). A stage is current only if it
  exists, was built from these exact sources and is complete; if every stage is current, skip regeneration. There is no
  separate stamp to update. The pilot is the one human gate: `ai_pilot.py accept` stores the hashes of the generator
  and evaluator prompts, and only while they match may a missing or incomplete bank be rebuilt without asking. At the
  start of an engagement `check_freshness.py --all` reports CSF and AI together (the CSF bank is stale when the CSET
  migration SQL changed upstream; it runs `git fetch` and reports a failure instead of hiding it); it states facts and the
  calling command decides what to rebuild.
- **AI impact notes** (`data/csf/ai_impact_notes.json`, keyed per CSF subcategory) have two layers: `exposure`, shown to
  every org, and `use`, shown only when AI is in use (`mcp_agentic` when the client has MCP / tools or agents, else `base_rag`). Notes are written only
  for CSF subcategories that have a mapped CIS safeguard; unmapped ones are listed, never invented. They are written to
  the CSF profile's Considerations column by the Stage 2 XLS writer (not built yet).
- **Profile XLS schemas are fixed by downstream skills** (AI RMF: 11 columns; CSF: 19 columns on "Current and Target
  Profile"). Do not change them without updating the skills.
