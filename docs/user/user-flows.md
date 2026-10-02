# ProcurePilot User Flows

> Navigation paths for every user-facing page, with journey visualisations.
> Last updated: 27 Sep 2026.
>
> Covers the web app only. The mobile app uses named routes rather than URLs; see
> [ProcurePilot Mobile App User Documentation](mobile-app-user-documentation.md) for its screens
> and navigation.

---

## Access and Workspace Setup

- `/auth/sign-in` -> sign in -> `/home`
- `/auth/sign-in` -> **Forgot password?** -> `/auth/password-reset` -> email reset link
- `/auth/sign-in` -> **Create workspace** -> `/onboarding/signup` -> invitation token + workspace details -> `/onboarding/plan` -> `/home`
- `/onboarding/accept-invitation?token=...` -> accept member invitation -> `/home`
- Guarded page while signed out -> `/auth/sign-in?returnUrl=...` -> original page after sign-in

```mermaid
journey
    title Sign In and Password Reset
    section Sign In
        Open sign-in: 3: User
        Enter credentials: 3: User
        Land on /home: 5: User
    section Forgot Password
        Click Forgot: 3: User
        Open reset page: 3: User
        Get reset email: 5: User
```

```mermaid
journey
    title Workspace and Invitation
    section Create Workspace
        Click Create: 3: User
        Fill signup form: 3: User
        Enter token: 3: User
        Choose plan: 4: User
        Land on /home: 5: User
    section Accept Invitation
        Open invite link: 3: User
        Accept invite: 4: User
        Land on /home: 5: User
    section Auth Guard
        Hit guarded page: 2: User
        Redirect to login: 3: System
        Sign in: 4: User
        Back to page: 5: User
```

## Catalogue and Supplier Setup

- `/home` -> **Products** -> `/products` -> **New Product** -> `/products/new` -> save -> `/products/:id`
- `/home` -> **Products** -> `/products` -> row edit -> `/products/:id`
- `/home` -> **Products** -> `/products` -> **Import Products** -> `/import?kind=products` -> upload CSV -> preview -> commit -> `/products`
- `/home` -> **Suppliers** -> `/suppliers` -> **New Supplier** -> `/suppliers/new` -> save -> `/suppliers/:id`
- `/home` -> **Suppliers** -> `/suppliers` -> row edit -> `/suppliers/:id`
- `/home` -> **Suppliers** -> `/suppliers` -> **Import Suppliers** -> `/import?kind=suppliers` -> upload CSV -> preview -> commit -> `/suppliers`
- `/home` -> **Import Catalogue** -> `/import` -> choose Products or Suppliers -> upload CSV -> preview -> commit

```mermaid
journey
    title Products
    section Create
        Go to Products: 3: User
        View list: 3: User
        Click New: 4: User
        Fill form: 3: User
        Save: 5: User
        View detail: 5: User
    section Edit
        Go to Products: 3: User
        Click row edit: 4: User
        View detail: 5: User
    section Import
        Go to Products: 3: User
        Click Import: 4: User
        Upload CSV: 3: User
        Preview: 4: User
        Commit: 5: User
        Back to list: 5: User
```

```mermaid
journey
    title Suppliers
    section Create
        Go to Suppliers: 3: User
        View list: 3: User
        Click New: 4: User
        Fill form: 3: User
        Save: 5: User
        View detail: 5: User
    section Edit
        Go to Suppliers: 3: User
        Click row edit: 4: User
        View detail: 5: User
    section Import
        Go to Suppliers: 3: User
        Click Import: 4: User
        Upload CSV: 3: User
        Preview: 4: User
        Commit: 5: User
        Back to list: 5: User
```

```mermaid
journey
    title Import Catalogue
    section Import
        Go to Import: 3: User
        Open /import: 3: User
        Pick type: 4: User
        Upload CSV: 3: User
        Preview: 4: User
        Commit: 5: User
```

## Quotation to Trusted Offer

- `/home` -> **Quotation Inbox** -> `/quotations` -> **Upload Quotation** -> `/quotations/upload` -> select file or sample -> extraction complete -> `/quotations/:id/review`
- `/quotations` -> search/filter/sort -> **Review & Authorize** -> `/quotations/:id/review`
- `/quotations/:id/review` -> inspect source evidence + fields + lines -> save corrections -> confirm and authorize
- `/quotations/:id/review` -> retry extraction, export CSV, archive, or create re-quote
- `/quotations/:id` redirects to `/quotations/:id/review`

```mermaid
journey
    title Upload and Review
    section Upload
        Go to Inbox: 3: User
        View list: 3: User
        Click Upload: 4: User
        Select file: 3: User
        Extraction done: 4: System
        Open review: 5: User
    section Browse
        Search or filter: 3: User
        Click Review: 4: User
        Open review: 5: User
```

```mermaid
journey
    title Authorize and Actions
    section Authorize
        Inspect evidence: 3: User
        Save corrections: 4: User
        Confirm: 5: User
    section Side Actions
        Retry extraction: 3: User
        Export CSV: 3: User
        Archive: 3: User
        Create re-quote: 4: User
```

> `/quotations/:id` redirects to `/quotations/:id/review`

## Matching, Comparison, and Savings

- `/home` -> **Match Resolution** -> `/matching` -> search/filter/sort -> **Resolve Match** -> `/matching/:id` -> choose outcome -> confirm
- `/matching/tasks/:id` redirects to `/matching/:id`
- `/home` -> **Smart Compare** -> `/offers/compare` -> select product + quantity -> compare landed costs -> **Record Purchase** -> `/savings/outcome-capture`
- `/offers/compare/:id` opens Smart Compare with a product preselected; `/compare` and `/compare/:id` are aliases
- `/home` -> **Smart Compare** -> `/offers/product-intelligence` -> select product/supplier/time window -> inspect historical prices
- `/offers/product-intelligence/:id` opens Product Price Intelligence with a product preselected
- `/home` -> **Basket Split** -> `/offers/basket-split` -> choose two suppliers + basket lines -> optimise -> `/offers/basket-split/:id`
- `/home` -> **Alerts Inbox** -> `/alerts` -> open alert action -> Smart Compare, supplier detail, or Product Price Intelligence
- `/home` -> **Savings Ledger** -> `/savings` -> **Record Purchase Outcome** -> `/savings/outcome-capture` -> compute saving -> `/savings/:id/evidence`
- `/savings` -> **View Evidence** -> `/savings/:id/evidence`; `/savings/:id` is an alias
- `/savings` -> **Export Savings** -> `/savings/export` -> generate export -> `/savings/export/:id`

```mermaid
journey
    title Matching and Compare
    section Match Resolution
        Go to Matching: 3: User
        Search or filter: 3: User
        Click Resolve: 4: User
        Open match: 4: User
        Choose outcome: 4: User
        Confirm: 5: User
    section Smart Compare
        Go to Compare: 3: User
        Open compare: 3: User
        Select product: 4: User
        Compare costs: 4: User
        Record purchase: 5: User
        Capture outcome: 5: User
```

```mermaid
journey
    title Intel, Basket, Alerts
    section Price Intelligence
        Go to Compare: 3: User
        Open intel page: 3: User
        Select filters: 4: User
        View prices: 5: User
    section Basket Split
        Go to Basket: 3: User
        Open split page: 3: User
        Pick suppliers: 4: User
        Optimise: 4: User
        View result: 5: User
    section Alerts
        Go to Alerts: 3: User
        Open inbox: 3: User
        Open action: 4: User
        Navigate target: 5: User
```

```mermaid
journey
    title Savings Ledger
    section Record
        Go to Savings: 3: User
        Open ledger: 3: User
        Click Record: 4: User
        Capture outcome: 4: User
        Compute saving: 5: User
        View evidence: 5: User
    section View and Export
        Click Evidence: 3: User
        Open evidence: 5: User
        Click Export: 3: User
        Open export: 4: User
        Generate: 4: User
        View result: 5: User
```

> **Redirects:** `/matching/tasks/:id` -> `/matching/:id` | `/offers/compare/:id` -> `/offers/compare` (preselected; `/compare` alias) | `/offers/product-intelligence/:id` -> `/offers/product-intelligence` (preselected) | `/savings/:id` -> `/savings/:id/evidence`

## Requests, Approvals, and Administration

- `/home` -> **Purchase Requests** -> `/requests` -> **Save Draft** -> `/requests/new` -> save draft -> `/requests/:id`
- `/requests/:id` -> submit, withdraw, or return to the queue depending on status
- `/requests/:id` (once routed to an approver) -> view Approval status section -> decision, comment, and timestamp appear once decided
- `/home` -> **Approval Queue** -> `/approvals` -> expand a row's lines -> **Approve** or **Reject** -> confirm (with optional comment) -> back to queue
- `/home` -> **Settings** -> `/settings` -> **+ New Delegation** -> pick delegate + date range -> save -> delegated requests route to the delegate's own Approval Queue
- `/home` -> **Team Management** -> `/team` -> invite member -> pending invitation -> accept invitation flow
- `/home` -> **Settings** -> `/settings` -> manage branches, cost centres, budgets, and approval delegations
- Unknown routes redirect to `/`, then to `/home` for signed-in users.

```mermaid
journey
    title Requests and Approvals
    section Create Request
        Go to Requests: 3: User
        View list: 3: User
        Click Save Draft: 4: User
        Fill form: 3: User
        Save draft: 5: User
        View detail: 5: User
    section Manage
        Open request: 3: User
        Submit: 4: User
        Withdraw: 3: User
        Back to queue: 3: User
    section Approvals
        Go to Approvals: 3: User
        Open queue: 3: User
        Expand lines: 4: User
        Approve or reject: 4: User
        Confirm with comment: 5: User
```

```mermaid
journey
    title Team and Settings
    section Team
        Go to Team: 3: User
        Open /team: 3: User
        Invite member: 4: User
        Invite sent: 4: System
        Member accepts: 5: User
    section Settings
        Go to Settings: 3: User
        Open /settings: 3: User
        Manage branches: 4: User
        Manage cost centres: 4: User
        Manage budgets: 4: User
        Manage delegations: 4: User
    section Unknown Routes
        Visit unknown URL: 2: User
        Redirect to /: 3: System
        Redirect to /home: 5: System
```

---

## Reporting and Automated Ingestion

- `/home` -> **Reports** -> `/reports` -> **Artifacts** tab -> filter by kind/status -> **Download**
- `/reports` -> **Schedules** tab -> **+ New Schedule** -> `/reports/schedule-form` -> pick kind, format, filters, delivery day, locale -> save -> back to `/reports`
- `/savings/export` -> **Schedule as Weekly Report** -> `/reports/schedule-form` (pre-populated with the export's kind/format/filters)
- `/home` -> **Reports** -> `/reports` -> **Weekly Procurement Digest** button -> `/reports/digest-settings` -> choose channel + locale -> browse the latest in-app digest -> follow a deep link into the relevant screen
- `/home` -> **Ingestion** -> `/ingestion` -> open a channel card -> **Email Forwarding** (`/ingestion/email-config`), **Email Log** (`/ingestion/email-log`), **Capture** (`/ingestion/capture`), **Catalogue Import** (`/ingestion/catalogue-import`), or **Refresh Schedules** (`/ingestion/refresh-schedules`)
- `/ingestion/capture` -> upload or take a photo -> quotation created -> **View Quotation** -> `/quotations/:id/review`
- `/ingestion/catalogue-import` -> pick supplier -> upload spreadsheet -> import results + error details
- `/ingestion/refresh-schedules` -> pick product + supplier + cadence -> **Add schedule** -> assign a source catalogue import inline

```mermaid
journey
    title Reports and Digest
    section Reports Center
        Go to Reports: 3: User
        View artifacts: 3: User
        Download artifact: 4: User
    section Schedules
        New schedule: 3: User
        Configure kind and format: 4: User
        Save schedule: 5: User
    section Digest
        Open digest settings: 3: User
        Choose channel: 4: User
        Read latest digest: 4: User
        Follow deep link: 5: User
```

```mermaid
journey
    title Automated Ingestion
    section Dashboard
        Go to Ingestion: 3: User
        Check stats and coverage: 3: User
    section Channels
        Open Email Config: 3: User
        Open Email Log: 3: User
        Open Capture: 3: User
        Open Catalogue Import: 3: User
        Open Refresh Schedules: 3: User
    section Capture Flow
        Upload or photo: 3: User
        Quotation created: 4: System
        Open review: 5: User
```

---

## Connected Operations (Orders, Accounting, POS)

- `/home` -> **Order Tracking** -> `/orders` -> open a row -> `/orders/:id` -> **Record confirmation** or **Record delivery** -> evidence timeline updates
- `/orders` -> **Create Order** (Owner/Buyer) -> `/orders/new` -> fill supplier, dates, currency, lines -> **Create Purchase Order** -> `/orders/:id`
- `/requests` -> **Create Order** action on an `approved` request (Owner/Buyer) -> `/orders/new?source_request_id=...` -> form pre-filled from the request, quantity capped at what's still unallocated, estimated price shown as a reference-only badge -> **Create Purchase Order** -> `/orders/:id`
- `/orders/:id` (Draft only) -> **Submit order** -> status becomes Submitted
- `/orders/:id` (Draft only) -> **Edit Draft** -> `/orders/:id/edit` -> same form, pre-filled from the order -> save
- `/orders/:id` (Draft only) -> **Cancel Order** -> confirmation dialog -> status becomes Cancelled
- `/home` -> **Accounting** -> `/accounting` -> **Connect** (Owner) -> provider OAuth -> back to `/accounting` -> **View Synced Bills** -> `/accounting/bills` -> **Sync now** -> filter by match status
- `/accounting/discrepancies` (direct URL only — no in-app link reaches it yet) -> filter Open/Resolved -> **Resolve** with an optional note
- `/home` -> **POS** -> `/pos` -> **Connect** (Owner) -> Square OAuth -> back to `/pos` -> **View Synced Signals** -> `/pos/signals` -> **Sync now** -> match an unmatched signal to a catalogue product

```mermaid
journey
    title Order Tracking
    section Create
        Create order (manual or from request): 3: User
        Edit draft: 3: User
        Cancel draft: 2: User
    section View
        Go to Orders: 3: User
        Open order: 4: User
    section Evidence
        Record confirmation: 4: User
        Record delivery: 4: User
        View timeline: 5: User
```

```mermaid
journey
    title Accounting and POS Integration
    section Accounting
        Connect provider: 3: User
        View synced bills: 3: User
        Sync now: 4: User
        Review discrepancies: 4: User
        Resolve discrepancy: 5: User
    section POS
        Connect Square: 3: User
        View synced signals: 3: User
        Match signal to product: 4: User
```

> **Note:** Order Tracking now has an in-app **Create Order** flow — manual, or pre-filled from an approved request — plus **Edit Draft** and **Cancel Order** (§11 of the user documentation). ProcurePilot still never sends, confirms, or cancels an order with the supplier through any integration; every one of these writes is an internal evidence record. Accounting and POS have no connect/provider-choice flow beyond what's listed above — the accounting provider (QuickBooks or Xero) is fixed by workspace configuration, not chosen in the UI.

---

## Predictive Procurement and Sourcing

- `/home` -> **Reorder Forecasts** -> `/forecasting` -> pick branch + required-by date -> **Prepare draft request** -> draft appears in `/requests`
- `/home` -> **Supplier Risk** -> `/supplier-risk` -> **View scorecard** -> `/suppliers/:id/scorecard` -> **Prepare negotiation brief** -> `/negotiation-briefs/:id` -> acknowledge or dismiss
- `/home` -> **Procurement Analyst** -> `/analyst` -> ask a question -> follow a next-step link, or **Question History** -> `/analyst/history` -> reopen a conversation -> `/analyst/:conversationId`
- `/home` -> **RFQ History** -> `/rfq/history` -> **Create RFQ** -> `/rfq/create` -> add lines + pick suppliers -> **Save Draft** -> **Send RFQ** -> supplier replies captured automatically
- `/home` -> **RFQ History** -> `/rfq/history` -> open a row -> `/rfq/compare/:id` -> review each response's guardrail-outcome panel -> **Prepare Request** -> draft appears in `/requests`; a `Converted` row instead opens `/requests/:id` directly
- `/rfq/history` -> **Guardrails** (Owner only) -> `/rfq/guardrails` -> create or edit a guardrail -> save -> guardrail can now auto-prepare a matching RFQ response

```mermaid
journey
    title Reorder Forecasts and Supplier Risk
    section Reorder Forecasts
        Go to Forecasting: 3: User
        Review proposal: 3: User
        Prepare draft request: 4: User
        View in Requests: 5: User
    section Supplier Risk
        Go to Supplier Risk: 3: User
        Open scorecard: 4: User
        Prepare negotiation brief: 4: User
        Acknowledge or dismiss: 5: User
```

```mermaid
journey
    title Analyst and RFQ Sourcing
    section Procurement Analyst
        Ask a question: 3: User
        Read cited answer: 4: User
        Follow next-step link: 5: User
    section RFQ Sourcing
        Go to RFQ History: 3: User
        Create RFQ: 3: User
        Open RFQ: 3: User
        Compare responses: 4: User
        Prepare request: 5: User
    section Guardrails
        Open Guardrails: 3: User
        Configure guardrail: 4: User
        Save guardrail: 5: User
```

---

For screen-by-screen details and screenshots, see [ProcurePilot User Documentation](user-documentation.md).
