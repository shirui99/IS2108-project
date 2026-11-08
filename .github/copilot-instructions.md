## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.

## instructions
We are improving an existing IS2108 Django pair project called FruitBasket.

This is a learning-focused, human-in-the-loop task. Implement only the small
task I supply next. Do not generate or replace the whole application, rewrite
complete files unnecessarily, or perform unrelated cleanup.

Before editing:
1. Read the repository's Copilot instructions.
2. Inspect the current code for the named task. Repository graphs are navigation
   aids; verify implementation details in the source.
3. Briefly explain the current behaviour, the proposed change, and affected files.

Constraints:
- Retain Django server-side rendering and Django Template Language.
- Retain the current models, field names, URL names, and session conventions
  unless the task explicitly requires a change.
- No React, Vue, Angular, DRF, serializers, or frontend build tooling.
- Keep JavaScript minimal. Prefer HTML, CSS, Django forms, and server rendering.
- Use POST with csrf_token for state-changing actions.
- Use Django ORM.
- Do not modify ML training, prediction logic, or saved model files for UI tasks.
- Do not add dependencies unless necessary and explained.
- Prefer surgical edits to existing templates/views over new abstractions.
- No database migrations unless I explicitly request a schema change.
- Output format: Show only the targeted diff or the exact changed code block,
  not the entire file.

Comments (Strict Rules):
- Explain WHY a decision was made (the bug or bad UX it prevents), never WHAT
  the syntax is doing.
- No tautological or tutorial comments (e.g., avoid "# Check if form is valid"
  or "# Loop through items").
- Maximum 1–2 clear sentences per comment in plain, conversational English suitable
  for an oral project defense.

After editing:
- Explain the changed behaviour in plain, beginner-friendly terms (give me a
  2-sentence "defense pitch" explaining why the bug happened and why this fix works).
- Give focused checks and expected results.
- State which checks you actually ran.
- Stop after this task. Do not commit, push, or start the next task.