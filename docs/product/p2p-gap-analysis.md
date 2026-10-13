# ProcurePilot vs Procure-to-Pay — Gap Analysis

| | |
|---|---|
| Reference | [`docs/P2P_Comprehensive_Process_Reference.md`](../P2P_Comprehensive_Process_Reference.md) — 25-step master flow, 14 control points, 9 personas |
| Baseline | `main` @ `45e3778`, 2026-09-29 |
| Layers compared | **Vision:** roadmap, PRD, user stories, constitution, ADRs · **Specs:** `specs/001`–`021` · **Implementation:** `apps/api`, `apps/web`, `apps/mobile`, `supabase/migrations` |
| Status | **Final.** Draft v1 was critiqued independently by Codex (GPT) and Agy (Gemini). Their objections were re-checked against the code, and each was accepted, partly accepted or rejected. The debate record is in §10. |

**Method.** Four independent evidence passes, one per area: vision/scope, steps 1–10, steps 11–18,
and steps 19–25 plus controls. Every load-bearing claim was then re-verified directly against the
code by the author, and again by both reviewers. `tasks.md` checkboxes were not trusted as evidence,
because they have been wrong in this repo before. File references are `path:line` at the baseline commit.

---

## 1. Executive summary

ProcurePilot is not meant to be a P2P suite. Its binding non-goals exclude a "Full enterprise
Source-to-Pay suite" and "ERP replacement" (`docs/roadmap/procurepilot_roadmap.md:121-132`,
constitution §IV). Its thesis chain is **decide → approve → order → receive → verify the saving**. The
connected accounting system (QuickBooks Online / Xero) is the implicit system of record for payables.

Judged on those terms, the product falls into three bands:

| Band | Reference steps | Verdict |
|---|---|---|
| **Decide:** need → requisition (PR) → approval → sourcing/compare | 1–6 | **Strong.** It exceeds the reference in several places (forecast- and low-stock-driven need capture, landed-cost normalisation, RFQ with guarded auto-preparation). Weak spots are thin requisition data, single-level approval, and blocked suppliers not being enforced. |
| **Commit & evidence:** purchase order (PO) → acknowledgement → receipt → invoice → match → exception | 7–18 | **The building blocks exist but are not wired into a chain.** Approving a PR does not create a PO. POs are keyed in by hand, and the web app has no screen to create one. There are two unlinked receipt models. The 3-way match mis-handles the reference's own partial-delivery example, and its tolerances are a hard-coded constant. **This band holds nearly all the actionable gaps.** |
| **Pay:** clear → payment approval → schedule → batch → execute → reconcile | 19–25 | **Absent by design**, delegated to the accounting system; a documented non-goal ("Post-Phase 3, subject to validation", `procurepilot_roadmap.md:264`; "revisit at G3", `:1259`). Only a read-only "due / paid" view is worth adding now. |

**Headline findings** (both reviewers agree with all five, and both agree the chain is load-bearing):

1. **The PR → PO → receipt → invoice chain is not connected (GAP-IN-SCOPE, §5.1).** Approving a PR
   writes `status='ordered'` directly (`apps/api/src/procurepilot_api/modules/requests/service.py:1898`).
   No PO is created, and `purchase_order` has no `purchase_request_id`. The roadmap's Phase 2 DoD,
   "requested, approved, ordered, received, and measured entirely inside ProcurePilot"
   (`procurepilot_roadmap.md:438`), is met only by treating "ordered" as a label. Until the chain
   exists, the savings ledger, 3-way match, budget and mobile receipt each see a different slice of reality.
2. **The 3-way match flags legitimate partial invoices (DEFECT, §5.2).** Take the reference's own
   example: one PO, two deliveries, two invoices. Both invoices land in `needs_review` and stay there.
   The first is flagged even before the second delivery, because invoice quantity is compared
   for equality against the supplier's *full* confirmed quantity.
3. **"Configured tolerances" are a constant (SPEC DRIFT, §5.3).** Quantity 0 and price ±0.01 absolute
   (`accounting/three_way_sync_service.py:29-34`), with no percentage option, per-tenant setting
   or UI. Together with #2, this makes the discrepancy list mostly noise.
4. **Outcome records are mutated in place, which is in tension with constitution §II (CONSTITUTIONAL, §5.4).**
   PO lines can be updated with no version history, and re-evaluation overwrites discrepancy evidence.
   The constitution requires outcome history (purchase, delivery…) to be append-only.
5. **Self-approval and single-person order handling are silent (DECISION NEEDED, §5.6).** An owner can approve their own
   request, and one buyer can create, submit and receive a PO. For micro-businesses this must stay
   possible, but at the moment it is invisible.

---

## 2. Classification used

| Tag | Meaning | Owner |
|---|---|---|
| **DEFECT** | In scope, specified, implemented, and gives wrong results | Engineering: fix |
| **SPEC DRIFT** | The spec promises it; the code does something weaker | Engineering, or amend the spec |
| **CONSTITUTIONAL** | Current behaviour conflicts with a principle in `.specify/memory/constitution.md` | Engineering (binding) |
| **GAP-IN-SCOPE** | The vision/PRD/DoD puts it in scope; no spec or code delivers it | Product: schedule |
| **COHERENCE GAP** | The vision is silent, but the in-scope flow does not hang together without it | Product: decide, then spec |
| **DECISION NEEDED** | A product-policy choice nobody has recorded | Owner |
| **NON-GOAL** | Deliberately excluded; keep it excluded and say so explicitly | Document only |
| **COVERED** | Matches the reference to a degree that fits the target customer | — |

---

## 3. Step-by-step scorecard (reference §3)

| # | Step | Vision | Spec | Implementation | Tag |
|---|---|---|---|---|---|
| 1 | Business need | P2/P4 | 008, 010, 018 | Manual PR; low-stock reports; forecast reorder proposals; RFQ auto-preparation | **COVERED (+)** |
| 2 | Purchase requisition | R2.1/R2.2 | 008 | Branch, cost centre, required-by date, estimated landed price. Missing: justification, attachments, suggested supplier, PR number, non-catalogue/service lines (`purchase_request_line.workspace_product_id NOT NULL`) | COHERENCE GAP (§5.14) |
| 3 | PR approval | R2.1 | 008 | Threshold rules, branch scope, delegation, owner fallback, audit. Single step only (`approval_step_one_per_request`) | COVERED; see §5.6, §5.11 |
| 4 | Route determination | Silent; policy engine P2 | none | No routing step; no contract entity | COHERENCE GAP (low for SMB) |
| 5 | Sourcing / RFQ | Core | 005, 011, 021 | Outbound RFQ via Mailgun, inbound capture, compare, guardrails. Runs RFQ → draft PR; cannot start from an approved PR; no award record | COVERED; §5.12 |
| 6 | Commercial terms | Partial | 004, 011 | Landed cost plus versioned `supplier_commercial_term` (MOV, delivery fee, quantity tiers). Payment terms are free text on supplier only; no terms are snapshotted onto quotation or PO | COHERENCE GAP (narrow, §5.15) |
| 7 | PO creation | Ambiguous (RM:264 vs R3.3) | 016 FR-001 | Manual `POST /orders` with a hand-typed `order_number`; not generated from PR, RFQ or compare; **no web create UI** | **GAP-IN-SCOPE** (§5.1) |
| 8 | PO approval (#2) | Silent | none | `submit` = draft → submitted, role check only | DECISION NEEDED (§5.7) |
| 9 | PO dispatch | Out through R4.3 | 016, 021 FR-009 | None | DECISION NEEDED (§5.18) |
| 10 | Supplier acknowledgement | R3.3 (manual) | 016 FR-002 | `supplier_confirmation`, append-only, entered by the buyer | COVERED (manual) |
| — | PO change / amendment | Silent | none | PO lines updateable in place; no revision, no re-approval | **CONSTITUTIONAL** (§5.4) |
| — | PO cancel / close | Silent | 016 enum only | `confirmed/received/closed/cancelled` values are never written | GAP-IN-SCOPE (§5.1) |
| 11 | Delivery | External | — | `expected_delivery_date` only | COVERED (minimal) |
| 12 | Receipt / GRN | R2.3 + R3.3 | 010, 016 | PO `delivery_receipt` (append-only, partial, cumulative) **and** a separate PR mobile confirmation, unlinked | GAP-IN-SCOPE (§5.1) |
| 12a | Over-receipt | Silent | none | Computed and shown, never blocked or routed (`orders/validation.py:114-149`) | COHERENCE GAP (§5.9) |
| 13 | Inspection / acceptance | R2.3 | 010 | Quality issue plus photo on the PR; no accepted vs rejected quantity; not linked to receipt or match | COHERENCE GAP (§5.10) |
| 13a | Returns / credit notes | Silent | none | Not modelled | COHERENCE GAP (§5.10) |
| 14 | Supplier invoice | R3.1 (via accounting) | 014 FR-005 | `synced_bill(_line)` from QBO/Xero only; no local invoice entity | DECISION NEEDED (§5.17) |
| 15 | Invoice capture & validation | Partial | none | Quotations get arithmetic and duplicate checks; bills get none | Delegated to the accounting system |
| 16 | 2/3-way match | R3.1 / R3.3 | 014 FR-007, 016 | Line-level engine; runs only during accounting sync; partial-invoice defect | **DEFECT** (§5.2) |
| 17 | Tolerance | R3.3 | 016 FR-007 | Constant | **SPEC DRIFT** (§5.3) |
| 18 | Exceptions | Partial | 014/016 | open/resolved flag plus note; no owner, SLA, metrics or structured resolution; evidence overwritten | **CONSTITUTIONAL** (§5.5) |
| 19–22 | Clear, payment approval (#3), schedule, batch | Silent | none | none | NON-GOAL |
| 23 | Payment execution | Deferred (RM:264, G3) | 016 FR-003 forbids it | none (`billing` = SaaS subscription billing) | NON-GOAL |
| 24 | Payment status | Silent | 014 FR-005 | `provider_status` open/paid/void plus remaining balance, read-only | Delegated; read-only bridge (§5.16) |
| 25 | Reconciliation & close | R3.1/R3.3 | 014, 016 | Two parallel reconciliation paths; PO never closes | GAP-IN-SCOPE (§5.1) |

---

## 4. Control-point scorecard (reference §16)

| # | Control | Current state | Tag |
|---|---|---|---|
| 1 | Budget control | Warn-only, measured against PR estimates. PRD F27 says "Block or warn"; US-019 says "blocked"; spec 008 chose warn | DECISION NEEDED (§5.13) |
| 2 | Delegation of Authority | Full for PR (threshold, branch, delegation); single-level; a currency mismatch with a rule silently falls back to the owner (`requests/routing.py:86`) | COVERED (PR) |
| 3 | Approved-supplier controls | `supplier.status='blocked'` exists but is not enforced on PR, RFQ or PO. PRD F28's policy engine fell between specs (008 deferred it "to R2.4–R2.5", nothing later took it) | **GAP-IN-SCOPE** (§5.8) |
| 4 | Contract / catalogue compliance | No contract entity; commercial terms are advisory | COHERENCE GAP, deferred (RM:460) |
| 5 | Segregation of Duties | None in vision, spec or code | DECISION NEEDED (§5.6) |
| 6 | PO approval before commitment | None; PO not tied to an approved PR | DECISION NEEDED (§5.7), after §5.1 |
| 7 | Receipt evidence | Present twice, unlinked | GAP-IN-SCOPE (§5.1) |
| 8 | Duplicate invoice detection | Left to the accounting system | Delegated |
| 9 | 2/3-way matching | Engine present; partial-invoice defect | **DEFECT** (§5.2) |
| 10 | Tolerances | Constant | **SPEC DRIFT** (§5.3) |
| 11 | Payment authorisation | — | NON-GOAL |
| 12 | Supplier bank-detail changes | No bank data stored | N/A; becomes a day-one must-have if payments ever enter scope |
| 13 | Audit trail | Append-only mechanism is solid; savings ledger and verification not audited | GAP (§5.8) |
| 14 | Reconciliation | Bill↔purchase and PO↔GRN↔bill run as parallel paths | GAP-IN-SCOPE (§5.1) |
| — | Tenant isolation on P2P tables | Verified: `ENABLE` + `FORCE` RLS on `purchase_order(_line)`, `supplier_confirmation(_line)`, `delivery_receipt(_line)`, `three_way_match`; every insert/update policy carries `WITH CHECK` (`20260919000005_purchase_order.sql:90-113`, `…06:115-143`, `…07:91-92`) | **COVERED** |

---

## 5. Findings

Each finding gives **evidence**, **impact**, and **changes needed** by layer (vision / spec / implementation).

### 5.1 GAP-IN-SCOPE — the PR → PO → GRN → invoice → paid chain is not connected

- **Evidence:**
  - Approving a PR writes `ordered` directly. The code comment cites 010 research R1: "there is no separate 'place the order' human action this release" (`requests/service.py:1889-1898`).
  - `purchase_order` has no FK to `purchase_request` (`supabase/migrations/20260919000005_purchase_order.sql:10-42`), and the `orders` module never references requests.
  - The only persisted PO status change is draft → submitted (`orders/service.py:205`); `confirmed`, `partially_received`, `received`, `closed` and `cancelled` are unreachable.
  - Receipts are accepted on `draft` POs.
  - The web app has no create-order call (`apps/web/src/app/features/orders/orders-api.ts`).
  - There are two receipt models: `purchase_request_line.quantity_received` (mobile, 010) and `delivery_receipt` (016).
  - There are two reconciliation paths: `purchase_record`↔bill (014) and PO↔GRN↔bill (016).
- **Why this is GAP-IN-SCOPE, not a nice-to-have:** the Phase 2 DoD promises request → approval →
  order → receipt inside the product (`procurepilot_roadmap.md:436-440`), and Phase 3 is
  "Connected Procurement".
- **Impact:**
  - Nobody can answer "what did this approved request actually cost, and has it been received and paid?"
  - Every later control depends on this chain: PO re-approval, SoD between requester and receiver, savings attribution, budget-vs-actual.
- **Changes needed:**
  - **Vision:** record roadmap open decision #3 (RM:1248), "Does ordering happen in-platform?", as
    answered by what R3.3 already built: *a PO is an internal commitment record generated from an
    approved PR; it is not transmitted to the supplier* (dispatch is §5.18).
  - **Spec:** a new chunk, "Order chain unification":
    - an approved PR produces one **draft** PO per supplier, with `purchase_order.purchase_request_id` and line-level links;
    - generation **never** submits or transmits; a human submits (constitution §III);
    - the mobile delivery confirmation writes a `delivery_receipt` against the PO;
    - explicit cancel and close transitions;
    - `purchase_record` derived from the PO rather than keyed in separately;
    - a PO create/edit screen.
  - **Implementation:** as specified. **Size:** L.

### 5.2 DEFECT — the 3-way match cannot handle more than one invoice per PO

- **Evidence:**
  - `accounting/three_way_match_service.py:480-513` compares each `invoice_line.quantity` against
    the *cumulative* received quantity (`abs(invoiced − received) > tolerance` → `quantity_variance`)
    and against the *latest supplier confirmation's* full quantity.
  - There is no invoiced-to-date or received-not-yet-invoiced allocation.
  - `_load_bills` (`three_way_sync_service.py:185-200`) has no status filter, so void and paid bills are re-evaluated on every sync.
- **Walking the reference §12 example** (PO 100, confirmed 100):
  - GRN-7001 is 60. INV-9001 (60) is flagged immediately (60 ≠ confirmed 100).
  - After GRN-7002, INV-9001 is flagged again (60 ≠ received 100).
  - INV-9002 (40) behaves the same way.
  - Neither invoice ever reaches `matched`.
- **Why it wasn't caught:** 016's plan names integration tests `test_order_tracking.py` and
  `test_three_way_match.py`. Neither exists; only unit tests do.
- **Changes needed:**
  - **Implementation:**
    - allocate receipts to bills in bill-date order, and compare each bill with received-minus-already-invoiced quantity per PO line;
    - treat the confirmation as an over-billing *ceiling*, not an equality check;
    - skip `void` bills;
    - for `paid` bills, stop raising *new* discrepancies. Do this **by appending a final assessment, not by mutating or suppressing earlier evidence** (constitution §II; §5.4).
  - **Spec:** add the §12 scenario to 016 as an acceptance scenario.
  - **Tests:** write the two missing integration tests.
- **Size:** S–M.

### 5.3 SPEC DRIFT — tolerances are hard-coded

- **Evidence:** `THREE_WAY_RULESET` (`three_way_sync_service.py:29-34`) sets quantity 0 and unit price 0.01;
  the price tolerance is re-denominated into the bill's currency (`:262-268`). Spec 016 FR-007 promises
  "explicit, versioned tolerance ruleset … within configured tolerances".
- **Impact:** rounding, price precision, and VAT-inclusive vs exclusive pricing all create discrepancies.
  Reference §7 assumes percentage tolerances.
- **Changes needed:**
  - **Implementation:** a per-tenant, versioned tolerance setting (quantity absolute/%, price
    absolute/%), owner-only, reusing the guardrail-settings UI pattern (T037/T038). The version is
    already stamped on each match.
  - **Spec:** amend 016 to state the defaults.
- **Size:** M.

### 5.4 CONSTITUTIONAL — outcome records are changed in place

*Found while adjudicating the debate. Neither reviewer raised it.*

- **Evidence:**
  - Constitution §II: "Outcome history — recommendation, action, purchase, delivery, quality,
    saving — MUST be an append-only event stream. Destructive updates to outcome records are
    prohibited."
  - `purchase_order` and `purchase_order_line` grant `update` to owner/buyer, with no revision
    table (`20260919000005_purchase_order.sql:100-116`).
  - `reconciliation_discrepancy.evidence` is documented as "Re-evaluation may replace the current snapshot"
    (`20260919000007_three_way_match_discrepancy.sql:147-149`).
  - By contrast, receipts and confirmations *are* append-only (`…06:145-153`).
- **Impact:**
  - After a PO is amended, the system cannot answer "what did we commit to, and when?"
  - Discrepancy history loses the evidence that a human resolved against.
  - This also covers the **PO change/amendment control** gap that both reviewers raised independently.
- **Changes needed:**
  - **Spec:** PO revisions as append-only versions: a submitted PO changes only by creating a new
    revision with a reason, re-evaluated against the approval rules (see §5.7).
  - **Spec:** discrepancy evidence history kept as rows, with the current snapshot as a view.
- **Size:** M.

### 5.5 CONSTITUTIONAL — exceptions are flags, not a review queue

- **Evidence:**
  - `reconciliation_discrepancy.status` is only `open|resolved` (`20260918000006:21`).
  - Resolving means any owner or buyer adds a note (`accounting/router.py:265-286`).
  - There is no assignee, no owner-by-type, no SLA, no ageing metric and no structured resolution
    (credit note, PO revision, dispute, accepted variance).
  - Constitution §III: "the review queue has its own state machine, SLAs, and metrics".
- **Changes needed:**
  - **Spec:**
    - resolution types;
    - a responsible role by type (price → buyer; quantity/receipt → branch manager of the receiving branch; data → owner);
    - SLA and ageing, with notifications through the existing alerts module;
    - first-pass match rate and exception ageing as queue metrics.
  - **Also state plainly:** ProcurePilot cannot *hold* a payment, because the accounting integration is read-only (014 FR-013). The product must not imply otherwise.
- **Size:** M.

### 5.6 DECISION NEEDED — segregation of duties (SoD)

- **Evidence:**
  - `_require_assigned_approver_or_owner` (`requests/service.py:2045-2052`) lets any owner decide any step, including on their own request.
  - `resolve_approver` (`requests/routing.py:38-69`) is never told who the requester is, so a threshold rule, or the owner fallback, can route a request to its own requester.
  - Orders `WRITE_ROLES` (owner, buyer) covers create, submit, confirmation and receipt (`orders/router.py:22-35`).
  - No spec or doc mentions SoD.
- **Debate outcome:** both reviewers moved this from COHERENCE GAP to DECISION NEEDED. Agy argued
  that strict SoD is an enterprise control that would stop a two-person business from placing an
  emergency order. **Accepted for strict SoD, rejected for visibility.** Flagging self-approval
  blocks nobody, and it restores the meaning of the audit trail that Principle I relies on.
- **Recommendation:**
  - **Tier 1:** record `self_approved` on the approval step and surface it in the queue and reports.
    Also flag a receipt recorded by the person who created the PO. No blocking.
  - **Tier 3:** route around the requester when another eligible approver exists, and offer an
    optional strict mode for multi-user tenants.

### 5.7 DECISION NEEDED — PO approval (the reference's "Approval #2")

- **Evidence:** `orders/service.py:184-215`; submit is a role check only.
- **Recommendation (after §5.1):**
  - A PO generated from an approved PR inherits that approval.
  - Re-approval is needed only when:
    - the PO or a revision exceeds the approved amount by more than a tenant threshold;
    - the supplier changes; or
    - the PO has no source PR (routed through the existing threshold rules).
  - This reuses `approval_step`. Approving every PO a second time would be unjustified friction for the SMB wedge.
- **Size:** M.

### 5.8 GAP — Phase 2 controls that fell between specs, and audit holes

- **Blocked suppliers:**
  - `supplier.status='blocked'` is filtered only in Supplier IQ and commercial terms (`offers/supplier_terms.py:147`, `offers/supplier_iq.py:141`).
  - It is not checked on PR lines, RFQ recipients (`rfq/service.py:241`) or POs.
  - PRD F28 put this in Phase 2, spec 008 deferred it, and no later spec picked it up.
  - **Fix:** reject blocked suppliers on those three paths. **Size:** S.
- **Audit:** the savings module writes no audit events:
  - recording a purchase (`savings/service.py:66`);
  - creating a saving (`:129`);
  - `POST /savings/{id}/verify` (`savings/router.py:88`).

  RM:411 promises a "full audit log on every request, approval, and override". Saving verification
  is the commercial proof point. Also add per-discrepancy lifecycle events.
  **Size:** S.
  *(Draft v1 also listed "budget update/delete". **Withdrawn:** those endpoints do not exist;
  the organisation module has only `create_budget`/`list_budgets`, `organisation/service.py:345,386`.
  Agy caught this.)*

### 5.9 COHERENCE GAP — over-receipt is not controlled

- **Evidence:** `over_received_quantity` is derived and displayed but never blocked, routed or flagged
  as a discrepancy (`orders/validation.py:114-149`).
- **Change needed:** raise an `over_received` discrepancy, with an optional tenant tolerance.
- **Size:** S.

### 5.10 COHERENCE GAP — acceptance, returns and credit notes

- **Evidence:**
  - `delivery_receipt_line` holds only `received_quantity`.
  - `delivery_quality_issue` hangs off the PR, has no status, and feeds only Supplier IQ (`20260913000003_delivery_quality_issue.sql:18-33`).
  - Returns to supplier and credit notes are not modelled. The 3-way match cannot net a credit note against a bill.
- **Change needed:**
  - Add `accepted_quantity` and a rejection reason alongside `received_quantity`. **Both stay as separate evidence**, so a supplier shortfall is never hidden.
  - The matcher uses accepted quantity only under an explicit rule.
  - Link quality issues to the receipt line.
  - Credit notes, synced read-only from the accounting system like bills, net against the original bill.
- **Size:** M.

### 5.11 Known limitation — approval routing is single-level

- **Evidence:** `approval_step_one_per_request` is unique (`20260823000044_approval_step.sql:30-38`).
- **Assessment:** fine for the wedge today. Multi-level approval (e.g. branch manager, then owner above X)
  is the most likely next request from growing customers. Record it; don't build it yet.

### 5.12 COHERENCE GAP — sourcing runs in reverse

- **Evidence:**
  - `rfq` has no `purchase_request_id` (`20260924203650_rfq_sourcing.sql:4-17`).
  - An RFQ response becomes a draft PR (`rfq/service.py:573-651`).
  - There is no award record.
- **Assessment:** "RFQ first, then request" suits recurring consumables. One-off purchases need the
  reference order: an approved need, then an RFQ.
- **Change needed:** a "Request quotes" action on an approved PR, with the award (chosen response
  and reason) recorded when the PO is generated.
- **Size:** S–M, after §5.1.

### 5.13 DECISION NEEDED — budget: warn or block

- **Evidence:** PRD F27 says "Block or warn"; US-019 says "overspending is blocked"; spec 008 says
  "not a hard block" (`specs/008-requests-approvals/spec.md:9-11`).
- **Recommendation:** pick one and amend the other document. If blocking is allowed, it needs an
  **explicit, audited human override path**, so it never becomes silent automated enforcement.
- **Debate outcome:** draft v1 also recommended moving budget consumption from estimates to POs
  and then actual bills. **Withdrawn.** Agy's objection is accepted: encumbrance accounting is
  ERP territory. Budgets keep using request estimates.

### 5.14 COHERENCE GAP — the requisition record is thin

- **Missing:**
  - justification;
  - attachments;
  - suggested supplier;
  - a human-readable PR number;
  - non-catalogue and service lines. `workspace_product_id NOT NULL` (`20260823000043_purchase_request_line.sql:10-35`) means services cannot be requested at all.
- **Size:** M.

### 5.15 COHERENCE GAP (narrow) — payment terms are not structured or snapshotted

- **Debate correction:** v1 overstated this. Codex pointed out that supplier commercial terms are
  already structured and versioned (`20260914000001_supplier_commercial_term.sql:9-51`).
- **The real gap:**
  - `supplier.payment_terms` is free text;
  - no terms are snapshotted onto quotations or POs, so a PO does not record the terms it was placed under.
- Incoterms and warranty are low priority for domestic consumables.
- **Tier:** 3.

### 5.16 NON-GOAL (keep) — the pay half, with a read-only bridge

- **Evidence:**
  - RM:121-132, RM:264, RM:1259.
  - 014 FR-013 and 016 FR-003 forbid writes and payments.
  - No payment entity exists.
- **Keep excluded**, and say explicitly in the vision: "payables and payment are owned by the
  connected accounting system".
- **Bridge:** show due date, remaining balance and paid/void per PO and supplier. The data is
  already synced (`20260920000009_supplier_iq_v2.sql:38-45`) but only negotiation briefs read it.
  **Size:** S.
- **Guard:** if payments ever enter scope, supplier bank-detail change control and payment SoD
  are **day-one** requirements, not follow-ups.

### 5.17 DECISION NEEDED — invoice capture without an accounting connection

- **Evidence:**
  - Invoices exist only as `synced_bill` (QBO/Xero).
  - Document ingestion is quotation-only: `document` has no kind column, and every extraction becomes a `quotation`.
  - A tenant with no accounting connection therefore gets no 3-way match at all.
- **Options:**
  - (a) Keep this delegated, and state that 3-way match requires an accounting connection.
  - (b) Route `document.kind = invoice` through the existing extraction pipeline into a local
    `supplier_invoice` that feeds the matcher.
- **Debate outcome:** Agy argued for NON-GOAL on the grounds that (b) "violates the architectural
  boundary". **Partly rejected:** (b) never writes to the accounting system, so it does not breach
  the read-only rule. It does duplicate the accounting system's job, which is a strong reason not to
  do it *now*.
- **Recommendation:** (a) now, stated in the product docs. Put (b) on the G3 list, sized by the
  share of tenants without an accounting connection.

### 5.18 DECISION NEEDED — sending the PO to the supplier

- **Evidence:** excluded by 016 ("internal evidence only") and by 021 FR-009 through R4.3;
  RM:264 defers it. The Mailgun outbound pipeline already exists for RFQs (ADR-018).
- **Assessment:** a *human-triggered* "Send PO" email with a PDF is compatible with constitution §III,
  because a human authorises it. It would also give suppliers a channel to acknowledge.
- **Recommendation:** a G3 decision; do not build before §5.1.

### 5.19 Known limitation — cross-currency matching

- **Evidence:** a bill in a different currency from its PO produces `currency_mismatch`
  (`three_way_match_service.py:517-541`). This is consistent with the project-wide rule of
  "exclude, never silently convert" (compare/basket split, PR #47).
- **Debate outcome:** Agy raised this as an omission. **Accepted as a documented limitation, not a
  defect.** Currency conversion in matching would need a rate source and a rate-date policy, which
  is a G3-level decision.

### 5.20 GAP — P2P process metrics

- **Evidence:** the reporting reader functions cover savings and requests
  (`20260915000005_reporting_reader_functions.sql:120-150`).
- **Missing:** PR-to-PO cycle time, first-pass match rate, exception ageing, receipt-to-invoice lag.
- First-pass match rate and ageing double as the review-queue metrics that §5.5 needs.
- **Tier:** 2.

### 5.21 Spec hygiene

- `specs/016-order-tracking-three-way-match/` has only `spec.md` and `plan.md`: no `tasks.md`,
  `data-model.md` or contracts. Its planned integration tests were never written, so its delivery
  cannot be checked task by task.
- Contradictions to settle in the vision docs:
  - RM:438 DoD ("ordered … inside ProcurePilot") vs RM:264 / PRD:110 ("ordering remains external");
  - three receipt concepts (010, 016, 006 `delivery_result`), which 010 itself notes at `spec.md:258-268`.

---

## 6. Personas and roles

| Reference persona | ProcurePilot | Gap |
|---|---|---|
| Requester | Any member, branch-scoped | — |
| Manager / Budget owner | `approver`, `branch_manager`, `owner` | The cost-centre "budget owner" is a data field, not used in routing |
| Buyer | `buyer` | Also handles PO, receipt and reconciliation (§5.6) |
| PO approver | — | §5.7 |
| Supplier | External; email only | No acknowledgement channel (§5.18) |
| Receiving | Branch member (PR, mobile) or owner/buyer (PO) | **Branch managers cannot record PO receipts** (`orders/router.py:22`), so the natural receiver is locked out of the PO path. Resolved by §5.1 |
| Accounts Payable | — | Delegated to the accounting system; owner/buyer resolve discrepancies |
| Finance / Treasury | — | NON-GOAL |
| System | ProcurePilot = decision and evidence layer; accounting system = ledger | State this in the vision (§5.16) |

## 7. Where ProcurePilot exceeds the reference

- **Need identification:** forecasting and reorder proposals (018), plus low-stock reports from mobile (010).
- **Sourcing depth:** quotation extraction, product matching, landed-cost normalisation, Smart Compare, basket optimiser, Supplier IQ, risk and negotiation briefs.
- **Guarded automation:** RFQ auto-preparation, evaluated at match-decision time (ADR-019), always stops at a draft PR for a human.
- **Outcome proof:** a verified-savings ledger that ties recommendations to realised prices.
- **Database-enforced tenancy and append-only audit**, verified on the P2P tables (§4).

---

## 8. Recommended roadmap additions

| Tier | Item | Layer | Size | § |
|---|---|---|---|---|
| **0: the load-bearing fixes** | Record decision #3 ("PO = internal record generated from an approved PR, not transmitted") | Vision | XS | 5.1 |
| 0 | **Order chain unification:** PR → draft PO (per supplier, never auto-submitted), PR↔PO links, cancel/close, mobile receipt → `delivery_receipt`, PO create/edit UI | Spec + impl | L | 5.1 |
| 0 | 3-way match allocation (received-minus-invoiced), void skip, append-only final assessment for paid bills; write the missing 016 integration tests | Impl + tests | S–M | 5.2 |
| 0 | Per-tenant, versioned tolerance settings | Spec amend + impl | M | 5.3 |
| 0 | Audit events: savings ledger, saving verification, discrepancy lifecycle | Impl | S | 5.8 |
| **1: controls and constitution** | Append-only PO revisions and discrepancy evidence history | Spec + impl | M | 5.4 |
| 1 | Exception review queue: resolution types, owner by type, SLA/ageing, notifications | Spec + impl | M | 5.5 |
| 1 | Enforce `blocked` suppliers on PR, RFQ and PO | Impl | S | 5.8 |
| 1 | Self-approval and self-receipt flags (visibility only) | Spec + impl | S | 5.6 |
| 1 | Over-receipt discrepancy | Impl | S | 5.9 |
| **2: deepen** | Conditional PO re-approval (variance, supplier change, PO with no source PR) | Spec + impl | M | 5.7 |
| 2 | Accepted vs received quantity; returns; credit-note netting | Spec + impl | M | 5.10 |
| 2 | Read-only due/paid/remaining per PO and supplier | Impl | S | 5.16 |
| 2 | "Request quotes" from an approved PR, plus an award record | Spec + impl | S–M | 5.12 |
| 2 | P2P process metrics | Impl | S–M | 5.20 |
| 2 | Requisition enrichment (justification, attachments, number, non-catalogue/service lines) | Spec + impl | M | 5.14 |
| **3: G3 decisions** | Budget warn vs block (with audited override) | Vision | — | 5.13 |
| 3 | Routing around the requester, and strict SoD mode | Decision | S–M | 5.6 |
| 3 | Structured and snapshotted payment terms | Spec + impl | M | 5.15 |
| 3 | Human-triggered PO email dispatch plus acknowledgement parsing | Decision | M | 5.18 |
| 3 | Local invoice capture | Decision | L | 5.17 |
| 3 | Multi-level approval chains | Decision | M | 5.11 |
| 3 | Cross-currency matching | Decision | M | 5.19 |
| 3 | Payments (and with them bank-detail control and payment SoD); stays a NON-GOAL unless validated | Decision | XL | 5.16 |

**Sequencing note:** tier 0 items 3–5 are independent and small, so they can ship before the chain
work. Everything in tiers 1–2 that touches POs assumes §5.1 has landed.

## 9. Decisions requested from the owner

1. **Ordering model (decision #3):** do you confirm "PO = internal commitment record generated from an approved PR; not transmitted"?
2. **SoD:** do you confirm flag-only visibility by default, with strict routing deferred to G3?
3. **Budget:** warn, block with an audited override, or a tenant setting?
4. **Invoices:** is "3-way match requires an accounting connection" acceptable as the stated position until G3?
5. **PO dispatch:** is human-triggered PO email a G3 candidate?

---

## 10. Debate record

Draft v1 was sent to Codex (GPT, `codex exec`, read-only sandbox) and Agy (Google Antigravity).
Each received the same adversarial brief, and neither saw the other's critique. Both verified claims
against the code at `45e3778`. Every disputed factual claim below was then re-checked by the author
before a ruling was made.

### 10.1 Factual verdicts

| Finding | Codex | Agy | Ruling |
|---|---|---|---|
| 3-way match partial invoices (now §5.2) | VERIFIED | VERIFIED | Stands |
| PR→PO chain (now §5.1) | VERIFIED | VERIFIED | Stands |
| Hard-coded tolerances (§5.3) | VERIFIED | VERIFIED | Stands |
| No SoD (§5.6) | VERIFIED | VERIFIED | Stands (re-tagged, see 10.2) |
| Savings not audited (§5.8) | VERIFIED | **OVERSTATED**: budget update/delete endpoints don't exist | **Agy correct.** Only `create_budget`/`list_budgets` exist. Budget item withdrawn |
| Commercial terms unstructured (§5.15) | **OVERSTATED**: `supplier_commercial_term` is structured | — | **Codex correct.** Narrowed to payment terms plus snapshotting |
| All other v1 findings | VERIFIED | not checked | Stand |

### 10.2 Classification disputes

| Item | v1 tag | Codex | Agy | Ruling |
|---|---|---|---|---|
| PR→PO chain | GAP | GAP-IN-SCOPE (Phase 2 DoD) | — | **Accepted** |
| SoD | COHERENCE GAP | DECISION NEEDED (silent behaviour is the defect) | DECISION NEEDED / NON-GOAL (SMB headcount) | **DECISION NEEDED.** Visibility flag kept (Tier 1); strict mode to Tier 3 |
| PO approval | COHERENCE GAP | DECISION NEEDED | — | **Accepted** |
| Local invoice capture | DECISION NEEDED | (verified, no dispute) | NON-GOAL (ERP boundary) | **Kept as DECISION NEEDED.** It does not write to the accounting system, so it does not breach the read-only rule. Recommendation stays "not now" |
| Budget encumbrance | Vision/spec conflict | Needs an audited override if blocking | NON-GOAL (ERP territory) | **Agy accepted:** encumbrance withdrawn. Codex's override condition added to §5.13 |
| Pay half | NON-GOAL | NON-GOAL plus read-only bridge | — | Already the v1 position |

### 10.3 Omissions raised, and how they were handled

| Raised by | Omission | Ruling |
|---|---|---|
| Codex **and** Agy | PO change/amendment control | **Added**, and strengthened into §5.4 once the author found the constitution §II conflict |
| Codex | Cancel/close unreachable | Folded into §5.1 (Tier 0) |
| Codex | Over-receipt not controlled | **Added** as §5.9 |
| Codex **and** Agy | Returns / credit notes / accepted quantity | **Added** to §5.10 |
| Codex | Exception SLAs and metrics are required by constitution §III | **Accepted**; §5.5 re-tagged CONSTITUTIONAL |
| Codex | P2P KPIs | **Added** as §5.20 |
| Codex | RLS on P2P tables: "select policies lack `WITH CHECK`" | **Rejected on the fact, accepted on the gap.** Postgres does not allow `WITH CHECK` on `FOR SELECT` policies. Every insert/update policy has it, and `ENABLE` + `FORCE` are present. The draft had not assessed RLS; it now does (§4, COVERED) |
| Agy | Cross-currency matching | **Added** as a documented limitation (§5.19), consistent with the project's exclude-not-convert rule |
| Author (during adjudication) | Discrepancy evidence overwritten; PO lines mutable | **Added** as §5.4 (CONSTITUTIONAL) |

### 10.4 Prioritisation changes

| Item | v1 | Codex | Agy | Final |
|---|---|---|---|---|
| Order-chain unification | Tier 1 | Tier 0 | Tier 0 | **Tier 0.** Both reviewers' main objection: the chain is load-bearing |
| Tolerance settings | Tier 1 | — | Tier 0 (useless noise otherwise) | **Tier 0** |
| Blocked-supplier enforcement | Tier 0 | Tier 1 | — | **Tier 1.** Cheap, but subordinate to the chain |
| SoD | Tier 1 | — | Tier 3 | **Split:** flag in Tier 1, strict routing in Tier 3 |
| Paid/due bridge | Tier 1 | Tier 2 | — | **Tier 2** |
| Payment terms | Tier 2 | Tier 3 | — | **Tier 3** |
| RLS review | — | Tier 0 | — | **Done** during adjudication; no work item |

### 10.5 Risky recommendations corrected

| Raised by | v1 recommendation | Correction applied |
|---|---|---|
| Codex | "Generate draft POs" | Explicit: generation never submits or transmits; a human submits (§5.1) |
| Codex | "Freeze paid match results" | Replaced with "append a final assessment; never mutate or suppress evidence" (§5.2) |
| Codex | Budget block as a tenant setting | Requires an audited human override path (§5.13) |
| Codex | "Matcher uses accepted instead of received" | Both quantities kept as separate evidence; an explicit rule governs which one the match uses (§5.10) |
| Agy | Budget encumbrance | Withdrawn (§5.13) |
| Agy | Audit budget update/delete | Withdrawn; the endpoints don't exist (§5.8) |

### 10.6 Where the reviewers disagreed with each other

- **SoD:** Codex treats the *silent* self-approval as a defect; Agy treats SoD as enterprise
  overreach. Both concerns are met by keeping it non-blocking but visible.
- **Local invoice capture:** Agy says NON-GOAL; Codex verified it without dispute. The ruling keeps
  the decision open but recommends against building it now.

Neither reviewer disputed the core diagnosis: **the decide half is strong, the pay half is correctly
out of scope, and the commit-and-evidence half needs its chain connected and its matcher corrected
before any further controls are layered on.**
