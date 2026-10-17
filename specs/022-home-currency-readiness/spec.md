# Feature Specification: Home Currency Readiness for the Egypt Pilot

**Feature Branch**: `022-home-currency-readiness`
**Created**: 2026-10-14
**Status**: Draft (amended 2026-10-14 after planning research: the home currency is the existing `tenant.currency`; see plan.md)
**Tracking**: Jira PP-1 (gap C1), PP-2 (gap C3), PP-3 fix part (gap C2) — see
`docs/gtm/first-customer-gtm-plan.md` § "Currency gaps — Egypt" and
`docs/gtm/gtm-execution-plan.md` (P-1..P-3)
**Input**: Each tenant has a home currency; web money forms default to it instead of USD;
quotation extraction falls back to it instead of GBP and recognises Egyptian currency markers and
Arabic-Indic digits, flagging any fallback for review; landed cost stops defaulting to GBP; the
mobile app shows money locale-aware with each currency's own minor units, in English and Arabic.

## Why now

The first pilot customer is a multi-branch F&B business in Egypt that prices in EGP. Today:

- a buyer must switch USD → EGP on every purchase order and guardrail setting; one miss puts a
  USD document against an EGP budget;
- a quote whose currency the extractor cannot determine is silently stored as **GBP**;
- the mobile approval screen — the closing shot of the demo video — shows `EGP 12500.000000`.

Constitution Principle VII (every monetary value carries an explicit currency) is already met in
storage; this feature makes the *defaults* and *display* honour the tenant's real currency.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Set a home currency and have forms default to it (Priority: P1)

An owner sets their organisation's home currency to EGP once. From then on, every web form that
creates or edits a monetary amount opens with EGP pre-selected. A buyer can still pick a different
currency on an individual document (e.g. an imported item quoted in USD).

**Why this priority**: removes a daily, error-prone manual step and is the prerequisite for the
extraction fallback (US2) and the demo tenant.

**Independent Test**: set home currency to EGP on a tenant; open each money form (purchase order
create, guardrail settings, quotation review with a currency-less quote, supplier minimum order /
delivery fee); confirm EGP is pre-selected; change one document to USD and confirm it saves as USD.

**Acceptance Scenarios**:

1. **Given** a tenant whose home currency is EGP, **When** a buyer opens "create purchase order",
   **Then** the currency field is EGP and the totals are labelled EGP.
2. **Given** a tenant whose home currency is EGP, **When** an owner opens guardrail settings with
   no value set yet, **Then** the maximum-value currency is EGP.
3. **Given** a purchase order created in EGP by default, **When** the buyer explicitly selects USD
   before saving, **Then** the order is saved in USD and the home currency is unchanged.
4. **Given** an existing document already saved in USD, **When** the home currency is changed to
   EGP, **Then** that document stays in USD (no retroactive change to stored amounts).
5. **Given** a member who is not an owner, **When** they view organisation settings, **Then** they
   can see the home currency but cannot change it.
6. **Given** the tenant record is not yet loaded in the session, **When** a money form opens,
   **Then** it falls back to today's default and nothing breaks.

---

### User Story 2 - Quotes with unclear currency fall back to home currency, flagged (Priority: P1)

A supplier sends a quote showing prices as `1,250 ج.م` or `١٢٥٠ جنيه`, or with no currency
marker at all. The system recognises Egyptian markers and Arabic-Indic digits; when it genuinely
cannot tell the currency, it uses the tenant's home currency **and flags the field for human
review** instead of silently storing GBP.

**Why this priority**: a wrong currency on a stored quote corrupts comparison and savings — the
product's core claim. Real Egyptian quotes are the pilot's daily input.

**Independent Test**: submit sample quotes (EGP marked with ج.م / جنيه / LE / L.E. / EGP; one
with Arabic-Indic digits; one with no currency marker) to a tenant with home currency EGP;
confirm the first set extract as EGP with correct amounts, and the unmarked one stores no currency
and is routed to review (`currency_unresolved`) with EGP offered as a suggestion.

**Acceptance Scenarios**:

1. **Given** a quote whose totals read `ج.م 1,250.00`, **When** it is extracted, **Then** the
   currency is EGP and is not flagged as a fallback.
2. **Given** a quote with amounts in Arabic-Indic digits (e.g. `١٢٥٠٫٥٠`), **When** it is
   extracted, **Then** the stored amounts equal the Western-digit values (1250.50).
3. **Given** a quote with no recognisable currency, **When** it is extracted for a tenant whose
   home currency is EGP, **Then** **no currency is stored**, the quotation is routed to review with
   reason `currency_unresolved`, and EGP is offered to the reviewer only as a suggestion.
4. **Given** a quote with mixed currency markers (e.g. USD and EGP lines), **When** it is
   extracted, **Then** the same no-currency, `currency_unresolved` outcome applies — mixed markers
   are never silently resolved.
5. **Given** a landed-cost calculation over a line missing its currency, **When** it runs, **Then**
   it uses the quote's currency, else reports the currency as missing — never the tenant currency
   and never a hard-coded GBP.

---

### User Story 3 - Money reads correctly on mobile (Priority: P2)

An approver opens the approval queue on their phone and sees `EGP 12,500.00` (or the Arabic
equivalent when the app is in Arabic), not `EGP 12500.000000`. A Kuwaiti dinar amount shows three
decimals.

**Why this priority**: it is the demo's closing screen and the first thing an approver sees, but
it does not change any stored value, so it ranks after US1/US2.

**Independent Test**: load the approval queue and a request detail with amounts in EGP, SAR, AED,
KWD, BHD and OMR, in English and Arabic; confirm grouping, decimal places and currency labelling.

**Acceptance Scenarios**:

1. **Given** an amount of 12500 EGP, **When** shown in English, **Then** it reads with digit
   grouping and exactly 2 decimals (e.g. `EGP 12,500.00`).
2. **Given** the same amount, **When** the app language is Arabic, **Then** it is formatted per
   Arabic locale conventions and reads correctly right-to-left.
3. **Given** an amount of 12.5 KWD, **When** shown, **Then** it has exactly 3 decimals.
4. **Given** an amount with more stored precision than the currency's minor units (e.g. a unit
   price of 1.23456 EGP), **When** shown, **Then** it is rounded for display only; the stored value
   is unchanged.

### Edge Cases

- Home currency changed after documents exist → existing documents keep their own currency (US1-4).
- Every tenant already has a currency (`tenant.currency`, set at signup) → no migration and no "unset" state.
- A quote mixes markers (e.g. `$` on one line, `ج.م` on the total) → treated as unclear: flagged
  for review, not silently resolved.
- `LE` appearing inside ordinary words or product names must not be read as a currency marker.
- Arabic decimal separator `٫` and thousands separator `٬` in amounts.
- Unknown or unsupported currency code on mobile → show the code with the amount, with sensible
  default 2 decimals, never crash.
- Negative amounts (credits/discounts) format correctly in both languages.

## Requirements *(mandatory)*

### Functional Requirements

**Home currency (US1)**

- **FR-001**: The tenant's existing currency (`tenant.currency`) IS the home currency; it MUST be
  restricted to the currencies the product already supports (no new storage).
- **FR-002**: Only an owner MUST be able to set or change the home currency; every member MUST be
  able to see it.
- **FR-003**: Setting or changing the home currency MUST be recorded in the audit trail with the
  old and new value.
- **FR-004**: Every web form that creates or edits a monetary amount — purchase order create/edit,
  guardrail settings, quotation review currency fallbacks, supplier minimum order and delivery fee
  — MUST default its currency to the tenant home currency when one is set and the document has no
  currency yet.
- **FR-005**: A user MUST still be able to choose a different currency per document; the home
  currency is a default, never a constraint.
- **FR-006**: Changing the home currency MUST NOT change any stored amount or currency.
- **FR-007**: Until the session's tenant record is loaded, forms MUST behave as they do today.
- **FR-008**: The home currency MUST be tenant-isolated like all other tenant data; no tenant can
  read or infer another tenant's setting.

**Extraction and landed cost (US2)**

- **FR-009**: Quotation extraction MUST recognise EGP from the markers `ج.م`, `جنيه`, `جنيه مصري`,
  `LE`, `L.E.`, `EGP` (as currency markers adjacent to amounts, not inside words).
- **FR-010**: Extraction MUST convert Arabic-Indic digits and Arabic decimal/thousands separators
  in amounts to their exact decimal values.
- **FR-011**: When extraction cannot determine a quote's currency (none found, or mixed
  markers), it MUST store **no currency** — not the tenant home currency, not GBP/USD — and MUST
  route the quotation to review with reason `currency_unresolved`. The tenant home currency MAY be
  recorded only as a *suggestion* shown to the reviewer; it is never stored as the quote's
  currency until a human confirms it. (Amended 2026-10-14 after review: silently defaulting to the
  tenant currency would misprice a foreign-currency quote.)
- **FR-012**: No extraction path MUST store GBP, USD, or any other hard-coded currency as a
  confident value when the currency was not actually found in the document.
- **FR-013**: Landed-cost calculations MUST NOT default to a hard-coded currency; a missing line
  currency MUST resolve to the quote's currency, else be reported as
  missing.

**Mobile display (US3)**

- **FR-014**: The mobile approval queue and request detail screens MUST show money with digit
  grouping and the currency's own number of decimal places (2 for EGP/SAR/AED/USD/EUR/GBP, 3 for
  KWD/BHD/OMR, 0 for zero-decimal currencies).
- **FR-015**: Mobile money display MUST follow the app's current language (English or Arabic),
  including right-to-left presentation in Arabic.
- **FR-016**: Display rounding MUST NOT alter stored amounts.

### Key Entities

- **Tenant home currency**: the existing `tenant.currency`; set at signup, changed by an owner; used only as a
  default for new money entries and as the reviewer's currency *suggestion* in extraction review (never
  stored as an extracted quote's currency). Changes are audited.
- **Unresolved currency**: an extracted quote whose currency was not evidenced by the document. It
  has no stored currency, a `currency_unresolved` review task, and a `suggested_currency` extraction
  field (tenant home currency, confidence 0) for the reviewer. Resolved when a reviewer sets it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a tenant with home currency EGP, 100% of the listed web money forms open with
  EGP pre-selected — a buyer creates an EGP purchase order with zero currency changes.
- **SC-002**: Of 5 real Egyptian supplier quotes (PP-3 test set), every one that shows an EGP
  marker extracts as EGP with correct amounts, including any written in Arabic-Indic digits.
- **SC-003**: 0 quotes are stored with a hard-coded GBP/USD currency that did not appear in the
  document; every defaulted currency is visibly flagged for review.
- **SC-004**: On mobile, amounts in EGP, SAR, AED, KWD, BHD and OMR display with the correct
  decimals and grouping in both English and Arabic (verified on screenshots).
- **SC-005**: Existing tenants see no behaviour change unless their currency differs from the old hard-coded default, and no errors.

## Assumptions

- The supported currency list is unchanged; unifying the two web lists and adding missing GCC
  codes is backlog item G1, out of scope here.
- Only the two named mobile screens are in scope for formatting; other mobile money displays
  follow later if any exist.
- No schema change: the pilot and demo tenants just set `tenant.currency` to EGP.
- The existing quotation-review flow already supports per-field "needs review" marking; the
  fallback flag reuses it.

## Out of Scope

- Currency conversion / exchange rates (gap C4).
- VAT model (gap C5).
- GCC readiness items G1–G5 beyond what mobile formatting needs (3-decimal display on mobile is in
  scope; 3-decimal handling on web is G2, out of scope).
- Changing any already-stored amounts or currencies.
