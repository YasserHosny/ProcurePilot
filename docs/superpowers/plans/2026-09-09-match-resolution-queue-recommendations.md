# Match Resolution Queue Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Match Resolution Queue into a grouped, evidence-rich, auditable workflow with an explicit handoff from quotation authorization and sequential match resolution.

**Architecture:** Retain the flat cursor-paginated match-task API and enrich each item with an authoritative quotation summary and backend-computed quoted exposure. Angular groups those items by quotation, while a direct line-task endpoint and quotation-scoped query parameters support reliable detail loading and `Resolve and Next`. Existing append-only decisions remain authoritative; matching transitions additionally use the authenticated audit writer.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Supabase/PostgREST, Angular 19 standalone components and signals, Angular Material/CDK, ngx-translate, pytest, Jasmine/Karma, Playwright, axe-core.

---

## File Map

- Create `apps/api/src/procurepilot_api/modules/matching/quoted_exposure.py`: pure decimal quoted-exposure calculation.
- Modify `apps/api/src/procurepilot_api/modules/matching/schemas.py`: quotation summary, exposure issue, reviewer evidence.
- Modify `apps/api/src/procurepilot_api/modules/matching/service.py`: response enrichment, direct task lookup, routing/automatic audit writes.
- Modify `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`: human-resolution audit write.
- Modify `apps/api/src/procurepilot_api/modules/matching/router.py`: direct line-task endpoint.
- Create `apps/api/tests/unit/test_matching_quoted_exposure.py`: decimal/currency calculation tests.
- Modify `apps/api/tests/unit/test_matching_queue.py`: enriched task and direct lookup tests.
- Modify `apps/api/tests/contract/test_matching_contract.py`: response contract tests.
- Create `apps/api/tests/integration/test_matching_audit.py`: audit-event coverage.
- Modify `apps/api/tests/integration/test_tenant_isolation.py`: enriched/direct endpoint isolation.
- Modify `apps/web/src/app/core/api/models.ts`: enriched matching types.
- Modify `apps/web/src/app/core/api/api.service.ts`: direct lookup and quotation filters.
- Modify `apps/web/src/app/features/matching/resolution-queue/*`: grouped responsive queue.
- Modify `apps/web/src/app/features/matching/match-resolution/*`: direct loading and resolve-next flow.
- Modify `apps/web/src/app/features/quotations/quotation-review/*`: visible matching initialization and continuation.
- Modify `packages/i18n/en.json` and `packages/i18n/ar.json`: all new queue and action strings.
- Modify `apps/web/tests/e2e/match-resolution.spec.ts`: critical workflow coverage.
- Modify `apps/web/tests/e2e/matching-a11y.spec.ts`: grouped queue accessibility coverage.
- Modify `apps/web/tests/e2e/phase-one-rtl.spec.ts`: grouped queue RTL coverage.
- Modify `docs/user/user-documentation.md`: grouped queue and continuation documentation.

### Task 1: Pure Quoted Exposure Contract

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/matching/quoted_exposure.py`
- Modify: `apps/api/src/procurepilot_api/modules/matching/schemas.py`
- Create: `apps/api/tests/unit/test_matching_quoted_exposure.py`
- Modify: `apps/api/tests/contract/test_matching_contract.py`

- [ ] **Step 1: Write failing calculation and contract tests**

Cover quantity times unit price, VAT on subtotal, delivery addition, discount subtraction, decimal
precision, missing quantity/price, and mixed currencies. Assert the public shape:

```python
assert result.total == Money(amount="34.0000", currency="GBP")
assert result.issue is None

mixed = quoted_exposure(
    quantity="10",
    unit_price=Money(amount="2.5000", currency="GBP"),
    vat_rate="0.2000",
    delivery_fee=Money(amount="5.0000", currency="USD"),
    discount=None,
)
assert mixed.total is None
assert mixed.issue == "currency_mismatch"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_matching_quoted_exposure.py apps/api/tests/contract/test_matching_contract.py -q
```

Expected: failure because `quoted_exposure`, `quoted_line_total`, and
`quoted_line_total_issue` do not exist.

- [ ] **Step 3: Implement the pure decimal helper and schema fields**

Use an immutable result and `Decimal`; do not use floats:

```python
QuotedExposureIssue = Literal["currency_mismatch"]

@dataclass(frozen=True)
class QuotedExposureResult:
    total: Money | None
    issue: QuotedExposureIssue | None = None
```

Quantize the final amount to four decimal places. Treat missing VAT, delivery, and discount as zero.
Return no total when quantity or unit price is absent.

- [ ] **Step 4: Run tests and lint for GREEN**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_matching_quoted_exposure.py apps/api/tests/contract/test_matching_contract.py -q
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/matching/quoted_exposure.py apps/api/src/procurepilot_api/modules/matching/schemas.py apps/api/tests/unit/test_matching_quoted_exposure.py apps/api/tests/contract/test_matching_contract.py
```

- [ ] **Step 5: Orchestrator review and commit**

Review for explicit currency, decimal-only math, and no landed-cost naming. Commit:

```bash
git add apps/api/src/procurepilot_api/modules/matching/quoted_exposure.py apps/api/src/procurepilot_api/modules/matching/schemas.py apps/api/tests/unit/test_matching_quoted_exposure.py apps/api/tests/contract/test_matching_contract.py
git commit -m "Add quoted exposure matching contract"
```

### Task 2: Enriched Queue Data and Direct Task Lookup

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/matching/schemas.py`
- Modify: `apps/api/src/procurepilot_api/modules/matching/service.py`
- Modify: `apps/api/src/procurepilot_api/modules/matching/router.py`
- Modify: `apps/api/tests/unit/test_matching_queue.py`
- Modify: `apps/api/tests/contract/test_matching_contract.py`

- [ ] **Step 1: Write failing enrichment and endpoint tests**

Assert every task includes one summary with authoritative counts and source evidence:

```python
assert task.quotation.id == quotation_id
assert task.quotation.status == "reviewed"
assert task.quotation.source_filename == "supplier-quote.pdf"
assert task.quotation.line_count == 6
assert task.quotation.open_match_task_count == 5
assert task.quotation_line.quoted_line_total.currency == "GBP"
```

Add a router/service test that `GET /quotation-lines/{line_id}/match-task` returns the latest task and
raises `NotFoundError` when the authenticated client cannot read the line.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_matching_queue.py apps/api/tests/contract/test_matching_contract.py -q
```

Expected: schema/endpoint assertions fail because the enrichment and direct lookup are absent.

- [ ] **Step 3: Implement enrichment without weakening tenant boundaries**

Add `QuotationMatchSummary` with exact typed fields. Extend `QUOTATION_COLUMNS` with existing
`document_id`, `issue_date`, `reviewed_at`, and `reviewed_by`. Read the source document through the
same authenticated client. Count lines and open tasks using tenant-scoped tables. Populate exposure by
calling Task 1's pure helper.

Add:

```python
def match_task_for_line(self, *, bearer_token: str, line_id: UUID) -> MatchTask:
    client = authenticated_client(self._settings, bearer_token)
    line = _line_row(client, line_id)
    task = _latest_task_for_line(client, line_id)
    if task is None:
        raise NotFoundError(details={"resource": "match_task"})
    return self._task(client, task, line_row=line)
```

Do not accept tenant IDs from route, query, or header input.

- [ ] **Step 4: Run tests and lint for GREEN**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_matching_queue.py apps/api/tests/contract/test_matching_contract.py -q
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/matching apps/api/tests/unit/test_matching_queue.py apps/api/tests/contract/test_matching_contract.py
```

- [ ] **Step 5: Orchestrator review and commit**

Confirm counts do not depend on cursor-page contents and every lookup uses the authenticated client.
Commit the API slice.

### Task 3: Append-Only Matching Audit Coverage

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/matching/service.py`
- Modify: `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`
- Create: `apps/api/tests/integration/test_matching_audit.py`
- Modify: `apps/api/tests/integration/test_tenant_isolation.py`
- Modify: `apps/api/tests/integration/quotation_helpers.py`

- [ ] **Step 1: Write failing event tests**

Exercise routing, automatic acceptance, and human resolution. Query `audit_event` and assert action,
actor, quotation target, and line-level metadata. Required actions:

```python
assert actions == {
    "matching.task_routed",
    "matching.auto_accepted",
    "matching.resolved",
}
```

For each event assert the appropriate subset of task/decision/candidate/product IDs, routing reason,
score, threshold, scoring version, and outcome. Add a tenant-B read asserting no tenant-A event or
enriched task can be enumerated.

- [ ] **Step 2: Run tests and verify RED**

```bash
TEST_DATABASE_URL="$DATABASE_URL" uv run --project apps/api pytest apps/api/tests/integration/test_matching_audit.py apps/api/tests/integration/test_tenant_isolation.py -q
```

Expected: missing matching audit actions.

- [ ] **Step 3: Implement authenticated audit writes**

Pass the bearer token through matching pipeline helpers. Record events only after the corresponding
database write returns its real ID. Use:

```python
AuditEventCreate(
    tenant_id=member.tenant_id,
    actor_membership_id=member.membership_id,
    actor_email=member.email,
    action="matching.resolved",
    target={
        "quotation_id": str(line["quotation_id"]),
        "quotation_line_id": str(line_id),
        "decision_id": str(decision.id),
        "outcome": decision.outcome,
        "matched_product_id": str(decision.matched_product.id),
    },
    outcome="success",
    trace_id=get_trace_id(),
)
```

Include candidate and scoring metadata when present. Do not update or delete decisions or audit events.

- [ ] **Step 4: Run matching, audit, isolation, and lint gates**

```bash
TEST_DATABASE_URL="$DATABASE_URL" uv run --project apps/api pytest apps/api/tests/integration/test_matching_audit.py apps/api/tests/integration/test_match_alias_learning.py apps/api/tests/integration/test_tenant_isolation.py -q
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/matching apps/api/tests/integration/test_matching_audit.py
```

- [ ] **Step 5: Orchestrator review and commit**

Verify the event target lets the existing quotation audit query find matching actions, and document
the known non-atomic cross-request limitation in review notes. Commit the audit slice.

### Task 4: Web Contract and Quotation-Scoped Queue State

**Files:**
- Modify: `apps/web/src/app/core/api/models.ts`
- Modify: `apps/web/src/app/core/api/api.service.ts`
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.ts`
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts`

- [ ] **Step 1: Write failing Angular tests**

Provide `ActivatedRoute` query parameters and assert `quotation_id` reaches every initial/load-more API
call. Add two cursor pages containing the same quotation and assert one computed group with merged tasks
and API-supplied counts.

```typescript
expect(apiService.getMatchTasks).toHaveBeenCalledWith(
  jasmine.objectContaining({ quotation_id: 'q-101' }),
);
expect(component.groups().length).toBe(1);
expect(component.groups()[0].tasks.length).toBe(2);
expect(component.groups()[0].openTaskCount).toBe(5);
```

- [ ] **Step 2: Run test and verify RED**

```bash
pnpm --filter web test -- --include src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts --watch=false
```

- [ ] **Step 3: Add strict models, direct API method, and grouping state**

Add `QuotationMatchSummary`, quoted exposure fields, reviewer evidence, and:

```typescript
getMatchTaskForLine(lineId: string): Observable<MatchTask> {
  return this.http.get<MatchTask>(`${this.base}/quotation-lines/${lineId}/match-task`);
}
```

Read `quotation_id` from `ActivatedRoute.snapshot.queryParamMap`, preserve it in queue requests, and
group appended tasks by quotation ID with a computed signal.

- [ ] **Step 4: Run tests and lint for GREEN**

```bash
pnpm --filter web test -- --include src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts --watch=false
pnpm --filter web lint
```

- [ ] **Step 5: Orchestrator review and commit**

Review strict typing, stale-response handling, and cursor group merging. Commit the web contract slice.

### Task 5: Grouped Responsive Queue UI

**Files:**
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.html`
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.scss`
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.ts`
- Modify: `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts`
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`

- [ ] **Step 1: Write failing rendering and accessibility tests**

Assert group headers, `Quotation reviewed`, `Matching Status`, `Low Match Score`, source filename,
quoted exposure, top candidate score, no-candidate action, full wording disclosure, decision evidence,
and absence of clickable `<tr>` elements. Assert expand buttons have translated accessible labels.

- [ ] **Step 2: Run test and verify RED**

```bash
pnpm --filter web test -- --include src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts --watch=false
```

- [ ] **Step 3: Build the selected grouped layout**

Use unframed quotation groups within the queue surface. Keep one card boundary for the queue tool; do
not nest cards. Use Material icons and buttons. Show rank-1 candidate and score, with visible failed
signal summary. Use a disclosure element/dialog for complete wording; do not make hover the only path.
Use CSS grid and logical properties, with a mobile layout that keeps the action visible.

- [ ] **Step 4: Complete English and Arabic catalogue entries**

Add matching keys symmetrically. Validate JSON:

```bash
node -e "JSON.parse(require('fs').readFileSync('packages/i18n/en.json')); JSON.parse(require('fs').readFileSync('packages/i18n/ar.json'))"
```

- [ ] **Step 5: Run component tests and lint for GREEN**

```bash
pnpm --filter web test -- --include src/app/features/matching/resolution-queue/resolution-queue.component.spec.ts --watch=false
pnpm --filter web lint
```

- [ ] **Step 6: Antigravity read-only UX review**

Dispatch a bounded read-only review of only the grouped queue diff. Require checks for evidence
hierarchy, mobile action visibility, keyboard targets, RTL logical properties, and hardcoded strings.
If Antigravity again fails its runtime preflight, record the failure and continue with local gates.

- [ ] **Step 7: Orchestrator review and commit**

Inspect every UI diff and apply only verified review feedback. Commit the grouped queue slice.

### Task 6: Visible Authorization-to-Matching Handoff

**Files:**
- Modify: `apps/web/src/app/features/quotations/quotation-review/quotation-review.component.ts`
- Modify: `apps/web/src/app/features/quotations/quotation-review/quotation-review.component.html`
- Modify: `apps/web/src/app/features/quotations/quotation-review/quotation-review.component.scss`
- Modify: `apps/web/src/app/features/quotations/quotation-review/quotation-review.component.spec.ts`
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`

- [ ] **Step 1: Write failing success and failure-state tests**

Assert matching initialization no longer swallows errors, success shows a continuation link to
`/matching?quotation_id=<id>`, failure shows retry, and the quotation remains reviewed.

- [ ] **Step 2: Run test and verify RED**

```bash
pnpm --filter web test -- --include src/app/features/quotations/quotation-review/quotation-review.component.spec.ts --watch=false
```

- [ ] **Step 3: Implement explicit initialization state**

Use a typed signal:

```typescript
type MatchingSetupState = 'idle' | 'loading' | 'ready' | 'failed';
readonly matchingSetupState = signal<MatchingSetupState>('idle');
```

Set state around `getQuotationMatches`, expose retry, and render a compact continuation action after
authorization. Do not automatically navigate.

- [ ] **Step 4: Run tests and lint for GREEN**

```bash
pnpm --filter web test -- --include src/app/features/quotations/quotation-review/quotation-review.component.spec.ts --watch=false
pnpm --filter web lint
```

- [ ] **Step 5: Orchestrator review and commit**

Confirm authorization success is not rolled back by matching failure and every string is translated.
Commit the handoff slice.

### Task 7: Direct Resolution Loading and Resolve Next

**Files:**
- Modify: `apps/web/src/app/features/matching/match-resolution/match-resolution.component.ts`
- Modify: `apps/web/src/app/features/matching/match-resolution/match-resolution.component.html`
- Modify: `apps/web/src/app/features/matching/match-resolution/match-resolution.component.scss`
- Modify: `apps/web/src/app/features/matching/match-resolution/match-resolution.component.spec.ts`
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`

- [ ] **Step 1: Write failing direct-load and navigation tests**

Assert initialization calls `getMatchTaskForLine` instead of listing all tasks. After resolution,
assert `Resolve and Next` queries open tasks for the same quotation and navigates to the next line. If
none remains, assert navigation to `/matching?quotation_id=<id>`.

- [ ] **Step 2: Run test and verify RED**

```bash
pnpm --filter web test -- --include src/app/features/matching/match-resolution/match-resolution.component.spec.ts --watch=false
```

- [ ] **Step 3: Implement direct loading and sequential actions**

Preserve quotation context in query parameters. Keep `Save Decision` and `Resolve and Next` as explicit
human commands. Refresh on a stale/concurrently resolved next task. Do not mutate an existing decision.

- [ ] **Step 4: Run tests and lint for GREEN**

```bash
pnpm --filter web test -- --include src/app/features/matching/match-resolution/match-resolution.component.spec.ts --watch=false
pnpm --filter web lint
```

- [ ] **Step 5: Orchestrator review and commit**

Check keyboard behavior, final-task behavior, and no autonomous confirmation. Commit the resolution
navigation slice.

### Task 8: Documentation, E2E, Accessibility, and Integrated Verification

**Files:**
- Modify: `docs/user/user-documentation.md`
- Modify: `apps/web/tests/e2e/match-resolution.spec.ts`
- Modify: `apps/web/tests/e2e/matching-a11y.spec.ts`
- Modify: `apps/web/tests/e2e/phase-one-rtl.spec.ts`
- Modify: `docs/quality/match-resolution-queue-critique.md` only to mark implemented recommendations.

- [ ] **Step 1: Update user and quality documentation**

Document the two lifecycle states, grouped queue, quoted exposure versus landed cost, continuation/retry,
candidate evidence, and resolve-next flow. Preserve any concurrent user documentation wording changes.

- [ ] **Step 2: Add the critical Playwright workflow test**

Cover authorize, matching-ready action, quotation-filtered group, evidence visibility, resolution,
next-line navigation, completed group, and matching audit history. Add desktop/mobile and LTR/RTL visual
assertions without brittle pixel-perfect snapshots.

- [ ] **Step 3: Run complete verification**

```bash
uv run --project apps/api pytest apps/api/tests/unit apps/api/tests/contract -q
TEST_DATABASE_URL="$DATABASE_URL" uv run --project apps/api pytest apps/api/tests/integration/test_matching_audit.py apps/api/tests/integration/test_match_alias_learning.py apps/api/tests/integration/test_tenant_isolation.py -q
pnpm --filter web test -- --watch=false
pnpm lint
pnpm test:a11y
pnpm --filter web test:e2e -- tests/e2e/match-resolution.spec.ts tests/e2e/matching-a11y.spec.ts tests/e2e/phase-one-rtl.spec.ts
git diff --check
```

- [ ] **Step 4: Rebuild and verify the remote-database app path**

Confirm `.env` points to hosted Supabase, then run:

```bash
docker-compose -f docker-compose.yml -f docker-compose.remote.yml up -d --build redis api web
curl -I http://localhost:4200/
curl http://localhost:8000/api/v1/health
```

Verify a fresh web `Last-Modified`, healthy containers, and `{"status":"ok"}`.

- [ ] **Step 5: Orchestrator final diff review and commit**

Review tests before trusting gates, inspect all generated code for scope creep and hardcoded strings,
confirm no secrets or tenant IDs were introduced, then commit the integrated documentation/E2E slice.
