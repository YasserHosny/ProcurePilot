# ProcurePilot — User Stories & Use Cases

> Persona-driven stories mapped to the PRD and roadmap phases.

---

## Personas

- **Omar** — Owner / GM of a small retail chain; economic buyer.
- **Sara** — Buyer / Operations Officer; runs procurement from a laptop.
- **Khaled** — Branch Manager; walks the store floor with a phone.
- **Fatima** — delegated Approver; reviews requests on mobile between meetings.
- **Youssef** — Procurement Analyst / Data Ops; clears the review queue and trains the AI.

---

## Phase 1 — Intelligence MVP

### Document ingestion & extraction

- **US-001** As Sara, I want to upload a supplier quotation (PDF, image, Excel) so that I do not retype line items.
- **US-002** As Sara, I want the system to highlight low-confidence fields so that I know what to correct.
- **US-003** As Youssef, I want to correct extracted fields side-by-side with the original document so that the AI learns from my corrections.
- **US-004** As Sara, I want the system to flag arithmetic mismatches automatically so that I never act on a malformed quotation.

### Matching & comparison

- **US-005** As Sara, I want the system to propose which product each line refers to so that I can compare like-for-like.
- **US-006** As Youssef, I want to confirm, reject, or correct a product match so that repeat mistakes are not made.
- **US-007** As Sara, I want to see the total landed cost per supplier offer so that I compare true cost, not just unit price.
- **US-008** As Sara, I want to see last paid and average paid prices while comparing so that I know whether an offer is actually good.

### Recommendations & savings

- **US-009** As Omar, I want a recommended action with evidence and confidence so that I can trust the system's advice.
- **US-010** As Sara, I want the savings ledger to show how each saving was calculated so that I can defend it to a supplier.
- **US-011** As Omar, I want to export the savings ledger to Excel/PDF so that I can share it with my accountant.

---

## Phase 2 — Workflow & Mobile

### Requests

- **US-012** As Khaled, I want to create a purchase request from my phone when I see a shelf is empty so that ordering is not delayed.
- **US-013** As Khaled, I want to scan a barcode to add a product to my request so that I do not type supplier names.
- **US-014** As Khaled, I want to attach a photo of the shelf/label so that the buyer has context for the request.
- **US-015** As Khaled, I want to submit requests offline and have them sync when I am back online so that poor connectivity does not block me.

### Approvals

- **US-016** As Fatima, I want to see each pending request with amount, branch, budget impact, and recommended supplier so that I can decide in under 30 seconds.
- **US-017** As Fatima, I want to approve, reject, or request changes with a comment from my phone so that I am not tied to a desk.
- **US-018** As Omar, I want approval thresholds and delegation rules per branch so that only large or unusual spend reaches me.
- **US-019** As Sara, I want budget checks at request time so that overspending is blocked before approval.

### Outcome capture

- **US-020** As Khaled, I want to confirm what was delivered and flag shortages from my phone so that supplier reliability data is accurate.
- **US-021** As Sara, I want the system to record the actual purchase price so that the savings ledger reflects real outcomes.

---

## Use Cases

### UC-001 New quotation → trusted recommendation
1. Sara uploads a PDF quotation.
2. Extraction service returns fields and confidence.
3. Sara reviews/corrects low-confidence fields.
4. Matching service links lines to catalogue products.
5. Landed-cost engine normalises every offer.
6. Smart Compare displays ranked offers with historical context.
7. Sara records a purchase decision.
8. Savings ledger updates with verified delta.

### UC-002 Shelf empty → approved order
1. Khaled sees a low-stock shelf and opens the mobile app.
2. He searches the catalogue, scans a barcode, or attaches a photo.
3. He enters quantity and required-by date.
4. Request routes to Fatima based on branch and amount.
5. Fatima reviews on mobile and approves.
6. Sara turns the request into an order with the supplier.
7. Khaled confirms delivery quantity.

### UC-003 Review queue → improved model
1. Youssef opens the review queue.
2. He sees extraction and match tasks prioritised by financial impact.
3. He corrects fields and confirms matches.
4. Every correction writes a `ProductAlias` and labelled example.
5. The next similar document routes with higher confidence.
