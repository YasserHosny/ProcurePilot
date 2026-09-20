# R4.1 Supplier IQ v2 and Negotiation Briefs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Supplier IQ scorecard into a deterministic, evidence-normalized supplier-risk model and add human-prepared, source-linked negotiation briefs while G3 remains explicitly unmet.

**Architecture:** Keep one supplier-risk source of truth by extending `SupplierIqService`, `supplier_scorecard_snapshot`, the existing scorecard endpoint, and the existing scorecard UI. Put pure v2 calculations in focused modules, persist snapshots and briefs through one authenticated PostgreSQL transaction, and expose tenant-wide risk and brief routes from the existing `offers` domain. Preserve v1 JSON snapshots for compatibility while normalized child rows become the v2 audit source.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg/Postgres 17 with forced RLS, Supabase Auth claims, Angular 19 standalone components/signals, Angular Material, ngx-translate, pytest, Jasmine/Karma, Playwright, axe-core.

---

## File map

- `supabase/migrations/20260920000009_supplier_iq_v2.sql`: schema extensions, normalized evidence, brief tables, indexes, forced RLS, append-only privileges.
- `apps/api/src/procurepilot_api/modules/accounting/connector.py`: provider-neutral bill due-date and remaining-balance fields.
- `apps/api/src/procurepilot_api/modules/accounting/{quickbooks_client,xero_client,sync_service,schemas,service}.py`: parse, persist, and project payment evidence.
- `apps/api/src/procurepilot_api/modules/offers/supplier_iq_v2.py`: pure typed risk inputs and deterministic calculations.
- `apps/api/src/procurepilot_api/modules/offers/supplier_iq_repository.py`: transactional evidence loading and snapshot persistence.
- `apps/api/src/procurepilot_api/modules/offers/negotiation_briefs.py`: deterministic talking points and transactional brief actions.
- `apps/api/src/procurepilot_api/modules/offers/{supplier_iq,schemas,router}.py`: orchestration, compatibility schemas, and HTTP routes.
- `apps/web/src/app/features/supplier-risk/`: API client, risk queue, brief detail, and focused scorecard-v2 panel.
- `packages/i18n/{en,ar}.json`: all R4.1 copy.
- `docs/architecture/{api-specification,data-dictionary}.md` and `docs/quality/r4.1-release-evidence.md`: delivered contract and verification record.

---

### Task 1: Add the normalized R4.1 data model and RLS boundary

**Files:**
- Create: `supabase/migrations/20260920000009_supplier_iq_v2.sql`
- Create: `apps/api/tests/integration/test_supplier_iq_v2_isolation.py`
- Modify: `apps/api/tests/integration/test_tenant_isolation.py`

- [ ] **Step 1: Write the failing migration/isolation tests**

Add tests that query `pg_class`, `pg_policies`, and `information_schema.role_table_grants` and assert:

```python
R4_TABLES = (
    "supplier_scorecard_metric",
    "supplier_scorecard_evidence",
    "negotiation_brief",
    "negotiation_brief_item",
    "negotiation_brief_item_evidence",
    "negotiation_brief_action",
)

def test_r4_supplier_tables_force_rls(admin_connection) -> None:
    with admin_connection.cursor() as cur:
        cur.execute(
            "select relname, relrowsecurity, relforcerowsecurity "
            "from pg_class where relname = any(%s)",
            (list(R4_TABLES),),
        )
        assert set(cur.fetchall()) == {(name, True, True) for name in R4_TABLES}

def test_r4_evidence_is_append_only(alpha_connection, seeded_r4_rows) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        alpha_connection.execute(
            "update negotiation_brief set brief_version = 'tampered' where id = %s",
            (seeded_r4_rows.brief_id,),
        )
```

Also add one read and one insert attempt proving tenant A cannot enumerate or reference tenant B's snapshot, metric, evidence, brief, item, item-evidence, or action rows.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
set -a; source .env; set +a
uv run --project apps/api pytest apps/api/tests/integration/test_supplier_iq_v2_isolation.py -q
```

Expected: FAIL because the six R4.1 tables and v2 snapshot columns do not exist.

- [ ] **Step 3: Write the forward-only migration**

The migration must:

```sql
alter table supplier_scorecard_snapshot
  add column state text,
  add column confidence text,
  add column release_posture text,
  add column valid_from timestamptz,
  add column valid_until timestamptz,
  add column source_fingerprint text,
  add column observed_history_days integer;

alter table synced_bill
  add column due_date date,
  add column remaining_balance_amount numeric(18,4),
  add column remaining_balance_currency text references supported_currency(code);
```

Add checks for v2 state (`ready`, `provisional`, `insufficient_data`), confidence (`high`, `medium`, `low`), `g3_unmet`, validity order, non-negative history, and paired balance/currency. Add a unique partial index on `(tenant_id, source_fingerprint)` where the fingerprint is non-null.

Create the six tables from the approved spec. `supplier_scorecard_metric` must support repeated currency buckets through a non-null `bucket_key` and unique `(tenant_id, snapshot_id, metric_kind, bucket_key)`. `supplier_scorecard_evidence` must have typed nullable composite FKs and a `num_nonnulls(purchase_order_id, delivery_receipt_id, landed_cost_id, three_way_match_id, synced_bill_id, workspace_product_id, delivery_quality_issue_id, supplier_commercial_term_id) = 1` check. `negotiation_brief_action.idempotency_key` must be unique per tenant. Add a deferred constraint trigger that rejects a committed brief item with zero item-evidence links.

Enable and force RLS on all six tables. Add member-select policies and owner/buyer insert policies with tenant checks. Revoke `update`, `delete`, and `truncate` from `authenticated` and `service_role`; grant only `select, insert` needed by each table.

- [ ] **Step 4: Apply the migration and verify GREEN**

Run:

```bash
set -a; source .env; set +a
pnpm db:migrate
uv run --project apps/api pytest apps/api/tests/integration/test_supplier_iq_v2_isolation.py -q
pnpm test:isolation
```

Expected: migration applies once; focused and full isolation tests pass.

- [ ] **Step 5: Commit the database boundary**

```bash
git add supabase/migrations/20260920000009_supplier_iq_v2.sql apps/api/tests/integration/test_supplier_iq_v2_isolation.py apps/api/tests/integration/test_tenant_isolation.py
git commit -m "feat: add supplier iq v2 evidence schema"
```

---

### Task 2: Persist provider due dates and balances

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/accounting/connector.py`
- Modify: `apps/api/src/procurepilot_api/modules/accounting/quickbooks_client.py`
- Modify: `apps/api/src/procurepilot_api/modules/accounting/xero_client.py`
- Modify: `apps/api/src/procurepilot_api/modules/accounting/sync_service.py`
- Modify: `apps/api/src/procurepilot_api/modules/accounting/schemas.py`
- Modify: `apps/api/src/procurepilot_api/modules/accounting/service.py`
- Modify: `apps/api/tests/unit/test_quickbooks_client.py`
- Modify: `apps/api/tests/unit/test_xero_client.py`
- Modify: `apps/api/tests/unit/test_accounting_sync_service.py`

- [ ] **Step 1: Write failing provider and persistence tests**

Extend realistic provider fixtures and assert:

```python
assert bills[0].due_date == date(2026, 7, 31)
assert bills[0].remaining_balance == Decimal("1845.50")
assert bills[1].remaining_balance == Decimal("0")
```

In the sync test, inspect the SQL parameters and require `due_date`, `remaining_balance_amount`, and the bill currency as `remaining_balance_currency`. Add a projection test proving those fields are returned by the synced-bill API.

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_quickbooks_client.py apps/api/tests/unit/test_xero_client.py apps/api/tests/unit/test_accounting_sync_service.py -q
```

Expected: FAIL because `RawBill` and synced-bill projections lack due-date/balance fields.

- [ ] **Step 3: Extend the provider-neutral bill type**

Add these fields to `RawBill` and validate non-negative finite balance:

```python
due_date: date | None = None
remaining_balance: Decimal | None = None
```

QuickBooks maps `DueDate` and `Balance`; Xero maps `DueDateString`/`DueDate` and `AmountDue`. Stub bills receive deterministic due dates and balances. `sync_service._upsert_bill` writes and updates the three new columns. `SyncedBill` exposes `due_date` and a paired `remaining_balance: Money | None`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the focused command from Step 2. Expected: all accounting tests pass with provider-missing values represented as `None`.

- [ ] **Step 5: Commit the payment evidence extension**

```bash
git add apps/api/src/procurepilot_api/modules/accounting apps/api/tests/unit/test_quickbooks_client.py apps/api/tests/unit/test_xero_client.py apps/api/tests/unit/test_accounting_sync_service.py
git commit -m "feat: retain supplier bill due evidence"
```

---

### Task 3: Build the pure Supplier IQ v2 calculator

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/offers/supplier_iq_v2.py`
- Create: `apps/api/tests/unit/test_supplier_iq_v2.py`
- Modify: `apps/api/src/procurepilot_api/modules/offers/schemas.py`

- [ ] **Step 1: Write failing calculation tests**

Create table-driven tests for concentration currency buckets, zero-baseline exclusion, median price drift, cumulative partial receipts, expected-date period assignment, reliability decay, alternatives, exactly-three weight renormalization, all three states, score boundaries `0.35`/`0.65`, and deterministic fingerprints.

The public test shape is:

```python
result = calculate_supplier_risk(
    SupplierRiskInput(
        supplier_id=SUPPLIER_ID,
        window_start=date(2026, 3, 24),
        split_date=date(2026, 6, 22),
        window_end=date(2026, 9, 20),
        purchase_orders=orders,
        receipts=receipts,
        prices=prices,
        alternatives=alternatives,
    )
)
assert result.components["price_drift"].risk == Decimal("0.5000")
assert result.score == Decimal("0.4125")
assert result.release_posture == "g3_unmet"
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_supplier_iq_v2.py -q
```

Expected: FAIL with missing `supplier_iq_v2` module.

- [ ] **Step 3: Implement immutable inputs and results**

Use frozen dataclasses for source projections and Pydantic response models for API boundaries.
The module exports `calculate_supplier_risk(payload: SupplierRiskInput) -> SupplierRiskResult`
and `source_fingerprint(payload: SupplierRiskInput) -> str` through this exact public list:

```python
SCORECARD_VERSION = "supplier-scorecard-v2"
RISK_VERSION = "supplier-risk-v2"
__all__ = [
    "RISK_VERSION",
    "SCORECARD_VERSION",
    "SupplierRiskInput",
    "SupplierRiskResult",
    "calculate_supplier_risk",
    "source_fingerprint",
]
```

Implement the approved formulas with `Decimal`, `statistics.median`, stable UUID sorting, explicit excluded counts, no currency conversion, and quantization only in schema serialization. Keep the existing v1 calculator unchanged.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the focused command from Step 2. Expected: every formula and boundary test passes bit-identically.

- [ ] **Step 5: Commit the calculator**

```bash
git add apps/api/src/procurepilot_api/modules/offers/supplier_iq_v2.py apps/api/src/procurepilot_api/modules/offers/schemas.py apps/api/tests/unit/test_supplier_iq_v2.py
git commit -m "feat: calculate supplier risk v2"
```

---

### Task 4: Load evidence and persist scorecards atomically

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/offers/supplier_iq_repository.py`
- Modify: `apps/api/src/procurepilot_api/modules/offers/supplier_iq.py`
- Create: `apps/api/tests/integration/test_supplier_iq_v2.py`

- [ ] **Step 1: Write failing repository/service tests**

Seed orders, lines, partial receipts, landed costs, three-way matches, quality issues, and bills for two tenants. Assert recomputation creates one header, normalized metric rows, typed evidence links, and no cross-tenant source IDs. Add a forced exception after metric insertion and assert the transaction leaves zero header/child rows.

```python
response = service.recompute_all(member=owner, idempotency_key=KEY)
assert response.generated_snapshots == 1
assert response.release_posture == "g3_unmet"
assert persisted_metric_kinds == {
    "concentration", "price_drift", "reliability", "single_source_exposure"
}
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
set -a; source .env; set +a
uv run --project apps/api pytest apps/api/tests/integration/test_supplier_iq_v2.py -q
```

Expected: FAIL because repository and v2 service methods do not exist.

- [ ] **Step 3: Implement one-transaction persistence**

`SupplierIqRepository` must use the existing authenticated psycopg connection helper and expose
`load_risk_input(conn, supplier_id, window)`, `persist_snapshot(conn, member, result)`, and
`list_latest(conn, cursor, limit)` through this public list:

```python
__all__ = [
    "SupplierIqRepository",
    "load_risk_input",
    "persist_snapshot",
    "list_latest",
]
```

Load only tenant-visible rows under RLS. Insert the compatibility JSON and normalized rows in one transaction, use `source_fingerprint` for replay, and do not catch database errors inside a savepoint that would allow a partial result. Extend `SupplierIqService` with `recompute_all`, `list_risks`, and latest-v2 retrieval while retaining the v1 scorecard response fields.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the focused command from Step 2 plus:

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_supplier_iq_metrics.py apps/api/tests/integration/test_supplier_iq.py -q
```

Expected: v2 integration tests and all v1 compatibility tests pass.

- [ ] **Step 5: Commit repository and orchestration**

```bash
git add apps/api/src/procurepilot_api/modules/offers/supplier_iq.py apps/api/src/procurepilot_api/modules/offers/supplier_iq_repository.py apps/api/tests/integration/test_supplier_iq_v2.py
git commit -m "feat: persist supplier risk evidence"
```

---

### Task 5: Generate immutable negotiation briefs

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/offers/negotiation_briefs.py`
- Create: `apps/api/tests/unit/test_negotiation_briefs.py`
- Create: `apps/api/tests/integration/test_negotiation_briefs.py`
- Modify: `apps/api/src/procurepilot_api/modules/offers/schemas.py`

- [ ] **Step 1: Write failing brief tests**

Cover six categories, service-risk maximum, overdue payment only with due dates, per-currency money, four-order purchase-frequency minimum, stable tie ordering, maximum one item per category, required evidence links, replay, expired/insufficient rejection, acknowledgement, dismissal reason, and append-only action history.

```python
brief = build_negotiation_brief(snapshot, context)
assert [item.kind for item in brief.items] == [
    "price_trajectory",
    "alternatives",
    "service_performance",
    "concentration_volume",
    "payment_context",
    "purchase_pattern",
]
assert all(item.evidence_ids for item in brief.items)
assert brief.release_posture == "g3_unmet"
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_negotiation_briefs.py apps/api/tests/integration/test_negotiation_briefs.py -q
```

Expected: FAIL with missing module and tables unused by application code.

- [ ] **Step 3: Implement deterministic brief creation and actions**

Export `build_negotiation_brief(snapshot, context) -> BriefDraft` and a
`NegotiationBriefService` with `prepare`, `list`, `get`, `acknowledge`, and `dismiss` methods.
Keep the public surface explicit:

```python
BRIEF_VERSION = "negotiation-brief-v1"
__all__ = [
    "BRIEF_VERSION",
    "BriefContext",
    "BriefDraft",
    "NegotiationBriefService",
    "build_negotiation_brief",
]
```

Render no prose in Python. Store typed values plus i18n keys. Derive status from the latest action and make prepare/action persistence transactional with audit append.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the focused command from Step 2. Expected: calculator and database workflow tests pass, including rollback and replay.

- [ ] **Step 5: Commit negotiation briefs**

```bash
git add apps/api/src/procurepilot_api/modules/offers/negotiation_briefs.py apps/api/src/procurepilot_api/modules/offers/schemas.py apps/api/tests/unit/test_negotiation_briefs.py apps/api/tests/integration/test_negotiation_briefs.py
git commit -m "feat: prepare negotiation briefs"
```

---

### Task 6: Expose the Supplier IQ v2 API contract

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/offers/router.py`
- Create: `apps/api/tests/contract/test_supplier_iq_v2_contract.py`
- Modify: `apps/api/tests/integration/test_supplier_iq_rbac.py`
- Modify: `apps/api/tests/integration/test_supplier_iq_audit.py`

- [ ] **Step 1: Write failing route and OpenAPI tests**

Assert all eight approved endpoints, bearer authentication, list limit bounds, owner/buyer mutations, member reads, `Idempotency-Key` requirements, standard 404 for cross-tenant IDs, standard 422 for stale/insufficient briefs, and unchanged existing scorecard top-level fields.

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run --project apps/api pytest apps/api/tests/contract/test_supplier_iq_v2_contract.py apps/api/tests/integration/test_supplier_iq_rbac.py apps/api/tests/integration/test_supplier_iq_audit.py -q
```

Expected: FAIL because the new paths are absent.

- [ ] **Step 3: Add typed routes**

Add routes under the existing offers router with `Annotated` dependencies. Use `require_role(owner, buyer)` for recompute, prepare, acknowledge, and dismiss. Use `current_member` for reads. Require UUID `Idempotency-Key` headers on mutations and apply the existing mutation rate limiter.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the focused command from Step 2 and inspect `create_app().openapi()` for exact paths and schemas. Expected: contract, RBAC, and audit tests pass.

- [ ] **Step 5: Commit the API**

```bash
git add apps/api/src/procurepilot_api/modules/offers/router.py apps/api/tests/contract/test_supplier_iq_v2_contract.py apps/api/tests/integration/test_supplier_iq_rbac.py apps/api/tests/integration/test_supplier_iq_audit.py
git commit -m "feat: expose supplier risk and brief api"
```

---

### Task 7: Add the typed Angular API client

**Files:**
- Create: `apps/web/src/app/features/supplier-risk/supplier-risk-api.ts`
- Create: `apps/web/src/app/features/supplier-risk/supplier-risk-api.spec.ts`

- [ ] **Step 1: Write failing HTTP client tests**

Use `HttpTestingController` to assert paths, query parameters, payloads, and UUID idempotency headers for risk list/recompute and brief prepare/get/list/acknowledge/dismiss.

```typescript
api.listRisks(undefined, 50).subscribe();
const request = http.expectOne('/api/v1/supplier-iq/risks?limit=50');
expect(request.request.method).toBe('GET');
```

- [ ] **Step 2: Run the focused test and verify RED**

```bash
pnpm --filter web test:unit -- --include='**/supplier-risk-api.spec.ts'
```

Expected: FAIL because the API client does not exist.

- [ ] **Step 3: Implement strict API types and methods**

Define literal unions for state, confidence, risk level, release posture, brief item kind, and status. Represent every amount as `{ amount: string; currency: string }`. Implement methods with `HttpClient`, capped limits, cursor parameters, and `crypto.randomUUID()` idempotency keys supplied once per user action.

- [ ] **Step 4: Run the test and verify GREEN**

Run the focused command from Step 2. Expected: all client tests pass without `any`.

- [ ] **Step 5: Commit the web client**

```bash
git add apps/web/src/app/features/supplier-risk/supplier-risk-api.ts apps/web/src/app/features/supplier-risk/supplier-risk-api.spec.ts
git commit -m "feat: add supplier risk web client"
```

---

### Task 8: Build the Supplier Risk queue

**Delegation:** Dispatch changes under `apps/web/src/**` to Agy when practical, with a narrow file scope and independent diff review before commit. If Agy is unavailable or quota-blocked, execute this task inline under the same tests.

**Files:**
- Create: `apps/web/src/app/features/supplier-risk/risk-queue/risk-queue.component.ts`
- Create: `apps/web/src/app/features/supplier-risk/risk-queue/risk-queue.component.html`
- Create: `apps/web/src/app/features/supplier-risk/risk-queue/risk-queue.component.scss`
- Create: `apps/web/src/app/features/supplier-risk/risk-queue/risk-queue.component.spec.ts`
- Modify: `apps/web/src/app/app.routes.ts`
- Modify: `apps/web/src/app/layout/shell/shell.component.html`

- [ ] **Step 1: Write failing queue tests**

Test loading/error/empty states, latest supplier rows, low/medium/high/insufficient states, confidence, G3 posture, stale validity, keyboard-accessible scorecard links, owner/buyer recompute, requester read-only behavior, and cursor loading.

- [ ] **Step 2: Run the focused test and verify RED**

```bash
pnpm --filter web test:unit -- --include='**/risk-queue.component.spec.ts'
```

Expected: FAIL because the component and route are absent.

- [ ] **Step 3: Implement the queue**

Use standalone Angular components, signals for local state, RxJS for API calls, Angular Material table/chips/progress/button/icon controls, and a stable responsive grid. Route `/supplier-risk` is readable by all members; only recompute is role-gated. Add a `shield` Material icon navigation item and translated tooltip/label.

- [ ] **Step 4: Run the test and verify GREEN**

Run the focused command from Step 2. Expected: all queue states pass without hardcoded user-facing text.

- [ ] **Step 5: Review and commit**

Review the delegated or inline diff for strict typing, logical CSS properties, no nested cards, stable dimensions, and route ordering, then:

```bash
git add apps/web/src/app/features/supplier-risk/risk-queue apps/web/src/app/app.routes.ts apps/web/src/app/layout/shell/shell.component.html
git commit -m "feat: add supplier risk queue"
```

---

### Task 9: Extend the scorecard and add brief detail

**Delegation:** Dispatch these frontend files to Agy when practical, then independently review the diff and rerun focused tests before commit.

**Files:**
- Create: `apps/web/src/app/features/supplier-risk/scorecard-v2-panel/scorecard-v2-panel.component.ts`
- Create: `apps/web/src/app/features/supplier-risk/scorecard-v2-panel/scorecard-v2-panel.component.html`
- Create: `apps/web/src/app/features/supplier-risk/scorecard-v2-panel/scorecard-v2-panel.component.scss`
- Create: `apps/web/src/app/features/supplier-risk/scorecard-v2-panel/scorecard-v2-panel.component.spec.ts`
- Create: `apps/web/src/app/features/supplier-risk/brief-detail/brief-detail.component.ts`
- Create: `apps/web/src/app/features/supplier-risk/brief-detail/brief-detail.component.html`
- Create: `apps/web/src/app/features/supplier-risk/brief-detail/brief-detail.component.scss`
- Create: `apps/web/src/app/features/supplier-risk/brief-detail/brief-detail.component.spec.ts`
- Modify: `apps/web/src/app/features/catalogue/supplier-scorecard/supplier-scorecard.component.ts`
- Modify: `apps/web/src/app/features/catalogue/supplier-scorecard/supplier-scorecard.component.spec.ts`
- Modify: `apps/web/src/app/app.routes.ts`

- [ ] **Step 1: Write failing component tests**

Cover four components and currency buckets, calculations/source links, excluded counts, provisional/insufficient/stale/G3 states, prepare-button eligibility, one brief item per category, localized question keys, acknowledgement, required dismissal reason, replay-safe disabled states, and read-only requester behavior.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
pnpm --filter web test:unit -- --include='**/scorecard-v2-panel.component.spec.ts' --include='**/brief-detail.component.spec.ts' --include='**/supplier-scorecard.component.spec.ts'
```

Expected: FAIL because v2 panel and brief detail do not exist.

- [ ] **Step 3: Implement focused components**

Embed `ScorecardV2PanelComponent` in the existing scorecard rather than expanding its already-large inline template. Use a semantic metric table and source-link list. `BriefDetailComponent` renders typed i18n templates, calculations, money, confidence, risk, validity, and source links; it offers acknowledge/dismiss only to owner/buyer. Add `/negotiation-briefs/:id` before any generic route.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all scorecard and brief tests pass.

- [ ] **Step 5: Review and commit**

```bash
git add apps/web/src/app/features/supplier-risk apps/web/src/app/features/catalogue/supplier-scorecard apps/web/src/app/app.routes.ts
git commit -m "feat: show supplier risk evidence and briefs"
```

---

### Task 10: Complete i18n, RTL, accessibility, and E2E coverage

**Files:**
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`
- Create: `apps/web/tests/e2e/supplier-risk.spec.ts`
- Modify: `apps/web/src/app/features/supplier-risk/**/*.spec.ts`

- [ ] **Step 1: Write failing translation and E2E assertions**

Assert every `supplierRisk.*` and `negotiationBrief.*` key exists in both catalogues with identical key sets. In Playwright, mock or seed the API and verify queue-to-scorecard-to-brief navigation, Arabic `dir=rtl`, keyboard focus order, no overlapping text at desktop/mobile widths, and zero axe violations.

- [ ] **Step 2: Run focused checks and verify RED**

```bash
pnpm --filter web test:unit -- --include='**/supplier-risk/**/*.spec.ts'
pnpm --filter web exec playwright test tests/e2e/supplier-risk.spec.ts --project=chrome
```

Expected: FAIL on missing translations and unimplemented E2E expectations.

- [ ] **Step 3: Add English and Arabic copy and finish accessibility behavior**

Add labels, states, metric explanations, question templates, action labels, errors, and source-link accessible names to both catalogues. Use logical CSS, visible focus, native headings/tables/lists, and `aria-live` only for asynchronous status changes.

- [ ] **Step 4: Run checks and verify GREEN**

Run the commands from Step 2 plus `pnpm test:a11y`. Expected: focused tests, E2E, RTL assertions, and axe checks pass.

- [ ] **Step 5: Commit localization and E2E coverage**

```bash
git add packages/i18n/en.json packages/i18n/ar.json apps/web/tests/e2e/supplier-risk.spec.ts apps/web/src/app/features/supplier-risk
git commit -m "test: cover supplier risk user journey"
```

---

### Task 11: Document the delivered contract and verify the release

**Files:**
- Modify: `docs/architecture/api-specification.md`
- Modify: `docs/architecture/data-dictionary.md`
- Create: `docs/quality/r4.1-release-evidence.md`
- Modify: `docs/quality/r3.4-release-evidence.md`

- [ ] **Step 1: Document API, data, and gate posture**

Record all endpoints, roles, idempotency, formulas, tables, typed evidence links, append-only actions, and `g3_unmet` behavior. In the R3.4 evidence file, add only a pointer to the R4.1 exception record; do not alter G3 measurements or mark the gate passed.

- [ ] **Step 2: Run static and focused backend gates**

```bash
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/offers apps/api/src/procurepilot_api/modules/accounting
uv run --project apps/api pytest apps/api/tests/unit/test_supplier_iq_v2.py apps/api/tests/unit/test_negotiation_briefs.py apps/api/tests/contract/test_supplier_iq_v2_contract.py apps/api/tests/integration/test_supplier_iq_v2.py apps/api/tests/integration/test_negotiation_briefs.py apps/api/tests/integration/test_supplier_iq_v2_isolation.py -q
```

Expected: ruff clean and all focused tests pass.

- [ ] **Step 3: Run full regression gates**

```bash
set -a; source .env; set +a
uv run --project apps/api pytest apps/api/tests -q
pnpm --filter web test:unit
pnpm --filter web build
pnpm test:isolation
pnpm test:a11y
git diff --check
```

Expected: all API and Angular tests pass, production build succeeds, tenant isolation and accessibility remain green, and the diff has no whitespace errors.

- [ ] **Step 4: Physically consume the API**

Start the API against hosted Supabase on an unused local port, then verify OpenAPI contains all eight routes. Consume unauthenticated risk list and confirm HTTP 401 with the standard envelope. With a valid test token, recompute a synthetic tenant, list risk, prepare a brief, fetch it, replay preparation, acknowledge or dismiss it, and confirm zero external supplier messages and no purchase-request/order mutations.

- [ ] **Step 5: Inspect the UI at desktop and mobile sizes**

Run the Angular build through the existing local web path. Capture desktop and mobile screenshots for English and Arabic, verify no overlap or clipping, verify evidence links and actions remain usable, and confirm the served assets are current.

- [ ] **Step 6: Commit release evidence**

```bash
git add docs/architecture/api-specification.md docs/architecture/data-dictionary.md docs/quality/r4.1-release-evidence.md docs/quality/r3.4-release-evidence.md
git commit -m "docs: record r4.1 release evidence"
```

---

## Requirement coverage

- FR-001: Tasks 3, 4, and 9 extend the existing Supplier IQ domain and UI.
- FR-002: Tasks 3 and 4 pin versions, windows, fingerprints, and decimal arithmetic.
- FR-003: Tasks 3 and 4 calculate and persist currency-bucketed concentration.
- FR-004: Task 3 covers price drift, record time, medians, and zero baselines.
- FR-005: Tasks 3 and 4 cover cumulative receipts, exclusions, period assignment, and decay.
- FR-006: Tasks 3 and 4 calculate single-source exposure from compatible alternatives.
- FR-007: Task 3 covers weights, exactly-three renormalization, and score suppression.
- FR-008: Task 3 tests the exact low, medium, and high boundaries.
- FR-009: Task 3 tests count, product-coverage, and confidence thresholds.
- FR-010: Tasks 3 and 4 implement ready, provisional, and insufficient states.
- FR-011: Tasks 2 and 5 supply and rank every roadmap talking-point category.
- FR-011A: Task 5 enforces category uniqueness and service/payment risk formulas.
- FR-011B: Task 5 enforces deterministic ordering and purchase-frequency sufficiency.
- FR-012: Tasks 2 and 5 use provider due dates and prohibit inferred paid dates.
- FR-013: Tasks 5, 9, and 10 use typed data and English/Arabic templates without generated prose.
- FR-014: Tasks 1, 4, 5, and 9 expose calculation, confidence, risk, validity, money, and sources.
- FR-015: Tasks 1, 3, 4, and 6 retain readable v1 snapshots and normalized immutable v2 rows.
- FR-016: Tasks 1 and 5 make briefs/items immutable and decisions append-only.
- FR-017: Tasks 6, 8, and 9 enforce mutation RBAC and tenant-member reads.
- FR-018: Tasks 1, 4, 5, and 6 enforce idempotency, transactions, rollback, and audit.
- FR-019: Task 1 provides tenant keys, forced RLS, policy checks, and isolation tests.
- FR-020: Tasks 4-6 cover standard not-found behavior for every tenant-scoped identifier.
- FR-021: Tasks 4, 6, 7, and 8 implement bounded cursor pagination and latest snapshots.
- FR-022: Tasks 3-6 and 11 preserve `g3_unmet` without changing gate evidence.
- FR-023: Tasks 8-10 provide English/Arabic, RTL, keyboard, responsive, and WCAG coverage.
- FR-024: Tasks 5, 6, and 11 prove no messaging or purchasing side effects.

## Complexity tracking

- The existing JSON snapshot remains only for response compatibility. Normalized rows are added
  because the constitution requires first-class provenance and negotiation items need relational
  evidence links; creating a second snapshot header is explicitly prohibited.
- Payment due date and balance are added to the provider-neutral accounting boundary because
  `updated_at` cannot truthfully represent payment timing. Paid-lateness remains unavailable until
  a provider supplies a paid date.
- Brief actions use an append-only event table instead of mutating a status column because they
  are recommendation outcomes and must retain history.
- No worker, external model, currency converter, messaging service, or new deployable is added.
