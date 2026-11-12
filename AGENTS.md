# AGENTS.md - FruitBasket pair project

## Scope and authority

- Applies to this repository and its subdirectories; also read applicable nested `AGENTS.md` files. Complete the requested bounded task. Reviews are read-only unless fixes are authorised; do not regenerate the application or essentially the entire report.
- Inspect the relevant URL, view, form/model/service, template and CSS before editing using targeted `rg` searches. Preserve unrelated work, existing paths, IDs, relationships, routes, session keys, form contracts and status values. Ask only when ambiguity blocks correctness.
- Follow the supplied IS2108 pair-project brief (pp. 1–7) and later instructor clarifications; flag conflicts and cite the source/page when asserting a course prohibition. Course requirements cover Python/Django, a relational database, customer storefront, custom employee panel, minimal JavaScript, no exposed default Django admin or full JavaScript frontend framework, and an integrated trained classification/regression model. Other rules below are team or engineering decisions.
- The user has permission to use LLMs; retain human review and group understanding. Never fabricate authorship, reviews, results, screenshots or model metrics.

## Graphify navigation

- When `graphify-out/graph.json` and the CLI are available, start architecture, dependency and code-location questions with `graphify query`, `graphify path` or `graphify explain` (and `graphify-out/wiki/index.md` for broad navigation) before broad source searches.
- Verify graph findings against current source. If Graphify is missing, fails or is stale, fall back to targeted `rg` and source reads without blocking work, installing tools or rebuilding the graph unnecessarily.

## Architecture and changes

- Use native Django MVT, server-rendered DTL, the Django ORM and the custom staff panel. Do not introduce SPA frameworks, DRF or Flask for the main application, a second ORM or a flat-file business database. Do not expose `admin.site.urls`; its presence in `INSTALLED_APPS` alone does not establish exposure.
- Preserve existing prefixed model field names and authentication/session contracts unless the task requires changing them. Do not rely on session
  flags alone for staff authorisation. Use plain-language form labels and template headings.
- Preserve development media serving (`MEDIA_URL`/`MEDIA_ROOT`) in URL routing and `request.FILES` handling on product image forms.
- Use FBVs or CBVs and forms or ModelForms as appropriate, keeping business decisions, validation, routing and cart state server-side with minimal JavaScript limited to optional UI helpers.
- Make small, understandable changes tied to the current story and acceptance criteria without unrelated refactoring, dependencies or feature expansion. For UI-only work, change backend, schema, authentication or ML only when concretely necessary, explained and authorised; report unrelated security defects separately.
- Commit, push, merge, deploy or transfer only within existing authorisation. Inspect dependency and run instructions before installing or upgrading anything.

## Requests, security and data

- GET must not perform business mutations. State-changing actions require POST, CSRF protection and server-side validation; enforce methods in handlers. Redirect after successful mutations and re-render invalid bound forms with entered values and useful field/non-field errors. PRG does not prevent duplicate or concurrent requests.
- Check current authentication and active staff status for every protected staff operation, and customer ownership for each protected customer record or action. Do not trust hidden controls, submitted customer IDs, session flags alone, browser validation or submitted prices. Use Django password hashing/authentication, never echo passwords, and keep secrets and private records out of evidence and logs.
- Validate quantities, amounts, dates, types, statuses and business rules server-side. Preserve HTML escaping for untrusted content; do not use `safe` or `mark_safe` as a general workaround.
- Preserve existing form and template contracts (including `multipart` upload encoding, CSRF tokens, names, IDs and blocks). If a view supplies rendered HTML from `form.render(...)`, retain `{{ form }}`; loop over fields only when the template receives a form object.
- Use atomic transactions for dependent writes and appropriate repeat-request and concurrency safeguards for sensitive workflows. Verify conditional claims or updates and roll back shortfalls. SQLite `select_for_update()` does not provide row locking; substantiate concurrency claims with tests.
- Keep uncommitted carts in sessions, preserving `request.session['cart']` and its existing ID/quantity conventions. Use serialisable values and save nested changes correctly. Recalculate prices and availability on the server; clear carts only after database success. Do not reserve transient cart stock unless explicitly designed.
- Preserve historical relationships and purchase-price snapshots; prefer deactivation or protected deletion where deletion would damage history. Never invent historical prices. Label simulated payments honestly and remember database transactions do not roll back external effects.

## FruitBasket stock policy

- Sellable stock requires an active product and an item with warehouse status `available`. A dated item is sellable when its recorded date is on or after today + `Pexpirydays`; an undated available item is sellable.
- Apply the shared sellability rule consistently to purchase eligibility, checkout allocation, customer restock screening and staff advice. Replenishment is `max(target - sellable stock, 0)`; an unset target produces no suggestion.
- Keep parent order status and allocated item lifecycle states consistent across checkout, staff fulfilment, pantry display and ML qualifying-order queries.
- Exclusion from sale does not automatically change stored status. Write-offs require an explicit staff action and recorded reason; if that workflow is missing, report the gap rather than silently inventing one. Preserve existing records and purchase history.
- Clearly disclose data limitations. For example, quantities selected by order date and current order status are not verified deliveries during that period when delivery timestamps are unavailable. Do not imply that an untyped recorded date is a confirmed use-by date.

## Templates and UI

- Reuse shared layouts, navigation, messages and existing styles; namespace new templates and static assets where appropriate. Preserve the approved FruitBasket identity and existing functionality. Use real data and honest placeholders; do not invent discounts, stock, reviews or delivery promises.
- Maintain semantic HTML (useful titles, headings, associated labels/errors, alt text), visible keyboard focus, sensible tab order, adequate contrast, textual statuses, responsive layouts (including scrollable dense tables on mobile) and helpful empty states.
- Keep navigation working without a JavaScript hamburger, avoid reset controls per project preference, and check relevant template, form and CSS contracts before editing.

## Machine learning

- Keep preprocessing and estimator together in a persisted `.joblib` pipeline. Fit preprocessing on training data; use prediction-time features and held-out evaluation without target or future leakage. Document feature schema, data assumptions, dependencies, artifact versions and reproducibility.
- Run cached inference server-side and connect predictions to a concrete storefront workflow. Avoid eager artifact loading at module startup so missing or incompatible artifacts do not break management commands; deliberately handle those failures and invalid predictions. Caching alone is not error handling.
- Provide clearly labelled deterministic fallbacks for insufficient history or unavailable/invalid output, using approved fallback logic. Validate finite and range-safe results and relevant ownership, product and stock inputs. Keep model predictions distinct from rule-based stock calculations; do not describe heuristics as trained ML or synthetic accuracy as real-world effectiveness.
- Preserve approved artifacts and logic during unrelated work. Unrestricted AI assistance is permitted for synthetic training data and training/persistence code; application integration still requires team understanding and disclosure.

## Verification and AI assistance

- Before substantial edits, briefly state current behaviour, intended change and affected files. Add short plain-language comments only for non-obvious contracts or business rules; avoid long tutorial comments.
- Use the project virtual environment to run `manage.py check`, focused tests (covering validation, permissions, regressions, and `Client(enforce_csrf_checks=True)` for CSRF) and migration checks from the directory containing `manage.py`. For sensitive workflows, test ownership, stock shortage, repeat requests and rollback. Never reset application data for verification.
- For UI changes, inspect rendered desktop and mobile pages with Playwright where available (covering signed-in/out, empty, error and long-content states, routes, form submissions, retained values, focus and navigation). Check static discovery and caching if the browser displays an unexpected CSS version.
- Report what was actually tested, failures, blockers and unverified cases, distinguishing source inspection from automated and browser verification. Do not commit temporary previews, secrets or test data.
- Record material AI assistance and actual verification by task or user story (tool/model, date, prompt, output/diff, accepted/rejected suggestions, human changes and checks) in Section 6 (and Appendix B if established), keeping changes understandable so both teammates can explain and defend them.