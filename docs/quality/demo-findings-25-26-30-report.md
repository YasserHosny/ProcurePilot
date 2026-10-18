# Demo findings 25, 26, 30 — execution report

Worktree: `~/codex-clones/pp-demo-findings`
Branch: `fix/demo-findings-25-26-30`
Date: 2026-10-18

All implementation and review were performed directly, without agents or implementer CLIs.
The named demo tenant was not read or modified by any test or script. Tests use generated
workspaces. No packages were installed, infrastructure repaired, RLS policies changed, or JWT
verification changed. Existing authenticated database-scoping conventions are retained.

## Finding 25 — retain quotations until a human decision

A blocker-free quotation still in `in_review` keeps an open, low-priority task with reason
`ready_to_authorise`. Review patches use the same rule. Authorisation/refusal closes the task
through the existing paths. Inbox sync also restores missing tasks for previously stranded
quotations, including those with resolved tasks. Recovery excludes archived quotations and
handles another inbox read concurrently creating the same task.

The reason is a Postgres enum: the new migration adds only its value. The enum-only SQL was
applied to `TEST_DATABASE_URL` for execution; deployment must apply the committed migration
before deploying the application. No production migration was run.

Changed files:

- `apps/api/src/procurepilot_api/modules/quotations/service.py`
- `apps/api/src/procurepilot_api/modules/quotations/review_service.py`
- `apps/api/src/procurepilot_api/modules/quotations/schemas.py`
- `supabase/migrations/20261018000001_review_reason_ready_to_authorise.sql`
- `apps/web/src/app/core/api/models.ts`
- `packages/i18n/en.json`, `packages/i18n/ar.json`
- `specs/003-quotation-inbox-extraction/contracts/quotation-inbox.openapi.yaml`
- `apps/api/tests/integration/test_quotation_review.py`
- `apps/api/tests/integration/test_demo_findings.py` (shared regression coverage)

The 12 new cases cover open/resolved/missing tasks, listing/patch sync, and authorise/refuse.
They assert inbox reachability before the human decision and resolution/removal afterwards.
Two existing tests were updated to expect an open task after correction.

## Finding 26 — show refused replies without an unusable action

RFQ comparisons include the linked quotation's current `quotation_status` in the query and
required response schema. A refused response stays visible with English/Arabic status and
explanation; its table and Prepare Request action are omitted. The preparation handler also
rejects a refused card locally. The existing backend refusal guard remains authoritative.

Changed files:

- `apps/api/src/procurepilot_api/modules/rfq/service.py`
- `apps/api/src/procurepilot_api/modules/rfq/schemas.py`
- `apps/web/src/app/features/rfq/rfq-api.ts`
- `apps/web/src/app/features/rfq/compare/compare.component.ts`
- `apps/web/src/app/features/rfq/compare/compare.component.html`
- `apps/web/src/app/features/rfq/compare/compare.component.spec.ts`
- `packages/i18n/en.json`, `packages/i18n/ar.json`
- `specs/021-rfq-sourcing-autonomy/contracts/rfq-responses.openapi.yaml`
- `docs/architecture/api-specification.md`
- `apps/api/tests/integration/test_demo_findings.py`
- `apps/api/tests/integration/test_rfq_service_e2e.py` (unique fixture emails for repeatability)

The API regression exercises HTTP 200 with a refused quotation and no lines, asserting the
response remains present and exposes `quotation_status = refused`. Web coverage checks the
explanation, absent button, guarded handler, and both translation catalogues.

## Finding 30 — withdraw an ordered request before a live PO exists

The requester or workspace owner can withdraw a draft/submitted/ordered request. An ordered
request with any linked PO other than `cancelled` returns HTTP 409 with
`details.reason = purchase_order_exists`. Success sets `withdrawn_at` and records the existing
withdrawal audit action with `previous_status`. The regression checks the audit call and
proves committed spend changes from GBP 100 to zero using the real spend query.

The PO check and withdrawal run in one authenticated database transaction, coordinated with
PO creation/editing using the existing allocation advisory lock. PO creation/editing rechecks
request status after taking that lock, preventing a stale validation from attaching a PO after
withdrawal. The race regression reproduces that interleaving without relying on timing.

The request list includes ordered requests in its Withdraw action condition, asks for
confirmation, and translates the live-PO conflict. No request-detail action was added: the list
satisfies the brief. Mobile was left unchanged because it has no existing withdrawal action;
its only withdrawal reference is a status filter.

Changed files:

- `apps/api/src/procurepilot_api/modules/requests/service.py`
- `apps/api/src/procurepilot_api/modules/orders/service.py`
- `apps/web/src/app/features/requests/request-list/request-list.component.ts`
- `apps/web/src/app/features/requests/request-list/request-list.component.html`
- `apps/web/src/app/features/requests/request-list/request-list.component.spec.ts`
- `packages/i18n/en.json`, `packages/i18n/ar.json`
- `specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`
- `docs/architecture/api-specification.md`
- `apps/api/tests/integration/test_demo_findings.py`
- `apps/api/tests/integration/test_order_tracking.py`
- `apps/api/tests/unit/test_orders.py` (cursor fixtures accommodate the status recheck)

The five HTTP integration cases cover requester/no PO, owner/no PO, other member (403),
draft PO (409), and cancelled PO (200). Web coverage checks the ordered button condition and
cancelling confirmation without calling the API.

## Execution environment

Every Python command below ran from the clone after:

```bash
cd ~/codex-clones/pp-demo-findings
source ~/codex-clones/pp7-env.sh
```

Database tests actually executed against the hosted test DB; no selected DB test was skipped.
The initial default Chrome launch could not start because this sandbox cannot write Chrome's
home configuration and cannot use its setuid sandbox. No installed tooling was changed.
Subsequent web commands used this temporary executable launcher:

```bash
cat > /tmp/pp-demo-chrome <<'SH'
#!/bin/sh
export XDG_CONFIG_HOME=/tmp/pp-demo-chrome-config
export XDG_CACHE_HOME=/tmp/pp-demo-chrome-cache
exec /opt/google/chrome/chrome --no-sandbox --disable-dev-shm-usage "$@"
SH
chmod +x /tmp/pp-demo-chrome
```

## Tests before the fixes

Original implementation files were restored temporarily from `git show HEAD:<path>` using
saved file contents and `try/finally` restoration, or the tests ran before implementation.
No stashing, resetting, checking out, or cleaning was used. All new regressions failed for the
intended behavior before the fixes. Initial fixture-development errors were corrected before
the valid baseline runs below; those errors are not counted as regression evidence.

Finding 25 (before implementing either sync change):

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_demo_findings.py -k in_review -q
```

```text
12 failed, 6 deselected, 1 warning in 146.55s (0:02:26)
```

All failed because the quotation had no task in the inbox after sync/patch.

Finding 26 (original RFQ service and schemas temporarily restored):

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_demo_findings.py -k refused_rfq -q -o faulthandler_timeout=45
```

```text
1 failed, 17 deselected, 1 warning in 16.61s
```

Failure: `KeyError: 'quotation_status'` on the HTTP response.

Finding 30 (original requests service temporarily restored):

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_demo_findings.py -k ordered_withdrawal -q
```

```text
5 failed, 13 deselected, 1 warning in 20.92s
```

The old implementation returned `already_decided_or_withdrawn` instead of successful
withdrawal, the actor error, or the specific live-PO conflict.

Finding 30 race (both post-lock status checks temporarily removed):

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_order_tracking.py -k concurrent_withdrawal -q
```

```text
1 failed, 12 deselected, 1 warning in 20.95s
```

Failure: PO creation returned 201 instead of 409 after withdrawal.

Findings 26/30 web (before UI and catalogue fixes):

```bash
CHROME_BIN=/tmp/pp-demo-chrome pnpm --filter web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/rfq/compare/compare.component.spec.ts' --include='src/app/features/requests/request-list/request-list.component.spec.ts'
```

```text
TOTAL: 3 FAILED, 27 SUCCESS
```

The failures were the refused card/action, translation keys, and ordered Withdraw button.
The additional confirmation regression was then added and run before implementing confirmation:

```bash
CHROME_BIN=/tmp/pp-demo-chrome pnpm --filter web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/requests/request-list/request-list.component.spec.ts'
```

```text
TOTAL: 2 FAILED, 13 SUCCESS
```

The ordered button and cancelled-confirmation regressions failed as expected.

## Tests with the final implementation

All three findings, final hosted regression and existing quotation-review tests:

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_demo_findings.py apps/api/tests/integration/test_quotation_review.py -q -o faulthandler_timeout=45
```

```text
36 passed, 1 warning in 149.33s (0:02:29)
```

Finding 25: 12 new cases plus 18 existing quotation tests. Finding 26: one API case.
Finding 30: five API/budget/actor cases. Zero skips.

Related orders, RFQ, budget, unit and contract checks (including the new PO race regression):

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/unit/test_orders.py apps/api/tests/unit/test_quotation_review_gate.py apps/api/tests/integration/test_request_budget_status.py apps/api/tests/contract/test_quotation_review_contract.py apps/api/tests/contract/test_requests_contract.py apps/api/tests/contract/test_requests_openapi_drift.py apps/api/tests/integration/test_order_tracking.py apps/api/tests/integration/test_rfq_isolation.py apps/api/tests/integration/test_rfq_service_e2e.py -q
```

```text
5 failed, 112 passed, 1 warning in 384.18s (0:06:24)
```

All five failures occurred before exercising application behavior: the existing RFQ E2E
fixture used fixed email addresses already present in the shared test database. Its generated
email now includes the fixture's user UUID; no existing records were deleted or changed.
Only the five affected tests were rerun:

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_rfq_service_e2e.py -q
```

```text
5 passed, 1 warning in 28.18s
```

The other 112 tests passed in the original related run, including every order, contract,
budget, and RFQ isolation test. Zero selected tests skipped in either run.

The first related unit run reported `7 failed, 51 passed, 1 warning in 5.32s` because cursor
fixtures did not supply the newly added status query; those fixtures were updated. The broad
run above passed all of those tests and the real database PO tests.

Additional quotation/review-task/request/PO isolation:

```bash
PYTHONPATH=$PWD/apps/api/src "/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/python" -m pytest apps/api/tests/integration/test_tenant_isolation.py -k 'quotation or review_task or purchase_request or purchase_order' -q
```

```text
11 passed, 106 deselected in 103.43s (0:01:43)
```

Final web specs for findings 26/30:

```bash
CHROME_BIN=/tmp/pp-demo-chrome pnpm --filter web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/rfq/compare/compare.component.spec.ts' --include='src/app/features/requests/request-list/request-list.component.spec.ts'
```

```text
TOTAL: 31 SUCCESS
```

Lint and formatting on every changed Python file:

```bash
"/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/ruff" check apps/api/src/procurepilot_api/modules/quotations/{service,schemas,review_service}.py apps/api/src/procurepilot_api/modules/rfq/{service,schemas}.py apps/api/src/procurepilot_api/modules/requests/service.py apps/api/src/procurepilot_api/modules/orders/service.py apps/api/tests/integration/{test_demo_findings,test_quotation_review,test_order_tracking,test_rfq_service_e2e}.py apps/api/tests/unit/test_orders.py
"/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/api/.venv/bin/ruff" format --check apps/api/src/procurepilot_api/modules/quotations/{service,schemas,review_service}.py apps/api/src/procurepilot_api/modules/rfq/{service,schemas}.py apps/api/src/procurepilot_api/modules/requests/service.py apps/api/src/procurepilot_api/modules/orders/service.py apps/api/tests/integration/{test_demo_findings,test_quotation_review,test_order_tracking,test_rfq_service_e2e}.py apps/api/tests/unit/test_orders.py
```

```text
All checks passed!
12 files already formatted
```

`git diff --check` also passed with no output.


## Limits

Final successful selections total 164 Python tests and 31 web specs, with zero skips.
All requested targeted checks were executed. The complete repository suite, browser E2E suite,
and mobile suite were not run; they are outside this focused change. No manual walkthrough was
performed against the named demo tenant. The only new migration is the enum addition above;
production application of it is a deployment step, not part of this branch-only task.

## Commits

- `f68e43c` — fix(quotations): retain review tasks until authorisation
- `bc99def` — fix(rfq): explain refused replies and remove prepare action
- `06ee90a` — fix(requests): withdraw ordered requests before purchase orders
- `docs: record demo findings execution evidence` — this report.

No commits were pushed.
