# AGENTS.md — IS2108 Pair Project

## Working agreement

- Apply to work in this repository and its subdirectories; also read any applicable nested AGENTS.md.
- Complete the requested bounded task. Reviews are read-only unless fixes are requested or already authorised. Do not regenerate the application.
- Follow Graphify navigation below when applicable; inspect relevant current source before editing. Use `rg` for targeted discovery and avoid full-repository scans for small edits.
- Prefer small, explainable diffs. Preserve unrelated work. Ask only when a real ambiguity blocks correctness; otherwise proceed within the agreed scope.
- Follow the course brief and supplied instructor clarifications. These instructions apply to the pair project, not practical examinations.

## Graphify navigation

- When `graphify-out/graph.json` exists and the CLI is available, start architecture, dependency and code-location questions with `graphify query "<question>"` before broad source searches.
- Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused explanations.
- Use `graphify-out/wiki/index.md`, if present, for broad navigation. Read the full `GRAPH_REPORT.md` only when scoped queries are insufficient.
- Treat graphs as navigation aids: verify relevant source, view/template contracts and current behaviour before editing.
- If Graphify is missing, fails or is stale, use targeted `rg` and source reads. Do not block the task, claim graph verification, install tooling or rebuild the graph unnecessarily.

## 1. Authority and human review

- **Course requirements:** Python/Django; relational database through Django ORM; customer storefront; custom employee panel; minimal JavaScript; no default Django admin or full JavaScript frontend framework; at least one trained classification/regression model persisted as joblib and integrated into storefront automation.
- Other rules below are adopted project/engineering safeguards, not necessarily explicit course requirements. Follow the supplied brief and later instructor clarifications; flag unresolved conflicts. Cite a source/page when asserting a course prohibition. Do not invent penalties or guarantee grades.
- The user reports permission to use ChatGPT and other LLMs. Retain human-in-the-loop coding, group understanding and AI disclosure. Do not outright generate the entire application or substitute for essentially the entire report. The brief does not explicitly ban every complete template.
- Synthetic ML data and training/persistence code may use unrestricted AI assistance; application integration still requires understanding. Never fabricate authorship, reviews, results, screenshots or model metrics.
- Record material AI assistance: known tool/model, date, prompt, output/diff, accepted/rejected suggestions, human changes and actual checks. Report processes, evidence and reflection in Section 6; use Appendix B if established, not as an invented course requirement.

## 2. Scope and minimal changes

- Confirm repository owner/name, branch and project root. Never assume similarly named projects share code or schema. Inspect repository instructions and the relevant URL → view → form/model/service → template → CSS chain.
- Current task defines the change; approved stories, report and logical model define scope. Flag discrepancies between documentation and code; do not automatically add/remove features.
- Preserve fields, relationships, IDs, route names, session/context keys, status values, form names and template blocks. Never invent fields such as available_packs, checkout_key or is_active from examples.
- Make the smallest coherent edit. No unrelated cleanup, abstractions, dependencies or feature expansion. **UI-only tasks: no backend, schema, authentication, migrations or ML changes unless concretely necessary, explained and within authorisation.** Report unrelated security defects separately.
- Preserve user work. Commit, push, merge, deploy or transfer repositories only within existing authorisation. Avoid repeated permission requests for already-authorised work.

## 3. Architecture

- Project choice: Python 3.14, Django 5.2.x, native MVT and server-rendered DTL. Verify actual versions/dependencies; Python 3.14 requires Django 5.2.8 or later within that series. Do not upgrade environments automatically.
- Use existing FBVs/CBVs and forms/ModelForms as appropriate. No React/Vue/Angular/Svelte, SPA, client routing, DRF page wrappers, second ORM or flat-file business database.
- Keep routing, validation, carts and business decisions server-side. No fetch/AJAX business workflows or frontend build process. JavaScript only for small optional UI behaviours; do not add it without need.
- Use custom staff views/forms/templates. Never expose admin.site.urls under any URL. Its presence in INSTALLED_APPS alone does not prove exposure; do not blindly remove apps/settings/migrations.

## 4. Security and forms

- Enforce staff permissions and customer ownership server-side. Hidden links, URL IDs and submitted customer IDs are not authorisation. Preserve account conventions; use Django password hashing/authentication.
- GET displays; POST with CSRF performs mutations, including cart changes, checkout, logout, cancellations, delivery, ratings and pantry actions. Enforce methods in handlers. Audit indirect GET writes such as automatic stock updates. Never disable CSRF to fix errors.
- Redirect after successful state-changing POSTs; re-render invalid bound forms with values and field/non-field errors. PRG prevents ordinary refresh resubmission, not duplicate/concurrent POSTs or guaranteed idempotency.
- Validate quantities, amounts, types, dates, statuses and business rules server-side. Do not trust browser validation or submitted prices. Escape user text; no indiscriminate safe/mark_safe. Never expose passwords, secrets or private records in evidence/logs/commits.
- Preserve method, action, enctype, CSRF, hidden fields, names, IDs and submit values. Keep multipart encoding for uploads; do not echo passwords.
- **Respect the form contract:** if views pass rendered HTML from form.render(...), retain {{ form }}. Only loop/include a field-rendering partial when receiving an actual form object. Do not add |safe as a rendering workaround.
- Use associated, human-readable labels and errors without renaming model fields. No reset controls under the current project preference. Provide explicit empty states using {% empty %} or appropriate if/else.

## 5. Transactions, inventory and sessions

- Use transaction.atomic() for dependent database writes; rollback incomplete orders/allocations. Atomicity alone does not prevent races. SQLite select_for_update() provides no row locking.
- Match concurrency control to the existing model: conditional decrement for quantity counters, or conditional claims of eligible items/batches. Verify affected counts and rollback shortfalls. Do not redesign inventory to fit an example.
- Consider idempotency constraints/tokens only when required; propose schema changes explicitly. Neither a session flag nor PRG eliminates all duplicate-request races.
- Preserve request.session['cart'] if used, including ID/quantity conventions. Use serialisable values; reassign nested changes or mark session.modified. Recalculate prices/totals and recheck active status/stock at checkout.
- Do not reserve stock in transient carts unless explicitly designed. Clear carts only after database success; sessions/external effects are not automatically rolled back with database writes.
- Preserve historical relationships using existing deactivation flags or protected-deletion handling. No silent cascading history loss. Label simulated payments honestly; database atomicity does not cover external gateways.

## 6. Visual design

- Reuse inheritance/partials and existing CSS paths. Prefer local Bootstrap CSS followed by one app-namespaced shared stylesheet; no required custom.css filename or CDN. Explain static discovery when changed: installed-app assets are project-wide; namespaces avoid collisions.
- Include doctype, language, charset, viewport, useful titles and heading hierarchy. Use readable typography, consistent spacing, restrained grocery colours and neutral surfaces. Avoid giant repeated banners, unnecessary cards/slogans, animations and icon libraries.
- Use natural labels such as Shop, Cart and My pantry; distinguish staff access. Preserve public browsing/login policy. Wrapping/stacking navigation must work without a JS hamburger; show active routes, including detail variants.
- Provide keyboard focus, sensible tab order, associated labels, alt text, contrast and textual alert/badge states. Use responsive product grids and scrollable dense tables where appropriate; retain essential mobile information.
- Use real data and honest image placeholders. No invented discounts, stock, reviews or delivery promises. Match availability queries to actual relations; avoid per-card query growth.

## 7. ML integration

- Connect real inputs → trained prediction → an identifiable storefront decision/workflow. Document algorithm, data and automation; displaying isolated predictions is insufficient. Model mathematics may remain a black box under the brief.
- Preserve approved logic/artifacts during unrelated tasks. Fit preprocessing on training data and reproduce it at inference; prefer a Pipeline when needed. Prevent future/target leakage; use appropriate held-out evaluation and a useful baseline. Never call heuristics trained ML.
- Serve inference server-side using a trusted joblib artifact and cached loading. Handle missing/incompatible artifacts; avoid repeated loading or eager startup failures that break management commands.
- Use the approved, honestly labelled deterministic fallback for insufficient history/invalid predictions; do not invent universal thresholds. Validate finite/range-safe outputs, dates, ownership, active products and stock.
- Document feature schema, synthetic assumptions, artifact/dependency versions and reproducibility. Demonstrate live-model and fallback paths; synthetic accuracy does not establish real-world effectiveness.

## 8. Verification and communication

From the actual directory containing `manage.py`, use the existing project environment:

```sh
python manage.py check
python manage.py test <relevant_app_or_test>
python manage.py findstatic store/css/site.css --verbosity 2
```

Select commands relevant to the task; the static path is an example, not an assumed repository layout. Inspect dependency/run instructions before installing anything. For authorised model changes, inspect migration status and run the relevant migration checks without resetting data.


- Before edits, briefly state existing behaviour, intended change and affected files. Comment only non-obvious reasons/contracts in short plain language.
- Run proportionate checks: manage.py check, focused tests and migration checks when relevant. For UI, render actual Django pages and inspect desktop/mobile, customer/staff, signed-in/out, empty/error and long-content cases.
- Verify fields render, errors retain values, routes resolve, forms submit and navigation/focus work. For sensitive workflows, test ownership, invalid input, stock shortage, duplicate submission and rollback; substantiate concurrency claims with concurrency tests.
- Confirm the latest CSS response loaded: inspect URL/body, cache and findstatic. Do not redesign around stale CSS.
- Distinguish source checks, rendering, screenshots and functional tests. Static mockups do not verify Django/session/database behaviour. Report exact environment blockers and outstanding checks; do not claim unperformed verification or commit temporary previews/secrets/test data.
- Finish with outcome, targeted diff/files, backend/behaviour changes, checks/results, limitations and a short oral-review explanation. Avoid full-file dumps, repetitive commentary and grade predictions.

## 9. Delivery checks — apply only when requested

- Implement agreed stories for both panels; keep report, logical model, ML and code consistent. No invented minimum story count; UML diagrams are optional, logical modelling is required.
- Report: cover/group details, contents, business model, stories (ID/title, role-goal-benefit, notes, wireframes/screenshots), ML and AI reflection/evidence; optional appendices. A4 portrait, 1-inch margins, double spacing, Times New Roman 12 pt main text, ≤50 inclusive pages; PPXX.docx, not PDF.
- ZIP: docs/report and source/project parent/main folder per brief p. 3; exclude .git/venv; include requirements.txt and readme.txt with required member/leader contacts, run instructions and YouTube link. Never invent personal details.
- Demo: ≤15 minutes, both members, real storefront/staff stories; slides unnecessary. Both members must complete code review satisfactorily and explain application code.

Source: IS2108 AY2627S1 Pair Project brief, pp. 1–7. Version pins, SSR/DRF choices, POST/PRG, concurrency recipes, cart keys, no-reset policy, CSS paths, Pipelines and fallback cutoffs are project/engineering rules, not universal verbatim course mandates. These instructions support, but cannot certify, compliance.

## UI verification

For changes affecting rendered pages, use Playwright to inspect the
affected pages at desktop and mobile widths. Review screenshots and
report what was checked.

Use the project's Python virtual environment. If the app or browser
cannot be launched, report the exact blocker rather than claiming
visual verification was completed.
