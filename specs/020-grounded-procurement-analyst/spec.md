# Feature Specification: R4.2 Grounded Procurement Analyst

**Feature Branch**: `020-grounded-procurement-analyst`
**Created**: 2026-09-23
**Status**: Draft for approval
**Roadmap Release**: R4.2, Phase 4 Predictive Procurement
**Input**: Natural-language question answering over the tenant's own data. Every answer must cite
a source record and show a visible calculation; never ungrounded generation. No autonomous
purchasing — retrieval and explanation only, same G3-unmet posture as R4.0/R4.1.

## Release posture

G3 remains unmet. R4.2 is an implementation exception, not a gate pass or commercial validation.
Every analyst answer carries `release_posture = g3_unmet`. The analyst never places, drafts,
approves, or sends anything; it only answers questions about data that already exists in the
tenant's workspace.

## User stories

### US1 - Ask a grounded question about tenant data (P1)

As any active tenant member, I can type a natural-language question about my own procurement data
(spend, savings, suppliers, risk, orders, quotations) and receive an answer that names the exact
records and calculation behind it, so I can trust the number enough to act on it myself.

**Acceptance scenarios**

1. Given a question with a computable answer from existing tenant data, when the member submits
   it, then the response shows the answer, the source records it drew from, and the calculation
   that produced it.
2. Given a question the analyst cannot ground in any existing record, when it is submitted, then
   the response states plainly that it cannot answer rather than guessing, and cites nothing.
3. Given a question about another tenant's data or an unknown identifier, when it is submitted,
   then the response behaves as if no such data exists in this tenant — it never reveals another
   tenant's existence or data.
4. Given a question outside the supported categories (see FR-002), when it is submitted, then the
   response says so explicitly and does not attempt a partial or approximate answer.

### US2 - Inspect the evidence behind an answer (P1)

As any active tenant member, I can open the source records and see the computation the analyst
used, so a number I'm about to rely on in a supplier conversation or a budget decision is fully
auditable rather than a black box.

**Acceptance scenarios**

1. Given an answer with cited records, when the member opens a citation, then it links to the
   same underlying record shown elsewhere in the product (the order, the quotation line, the
   scorecard, the saving record), not a copy or a summary of it.
2. Given an answer that used a calculation (a sum, an average, a rate, a trend), when the member
   inspects it, then the exact inputs and formula are visible, matching FR-002's per-category
   calculation rules.

### US3 - Ask a follow-up question in context (P2)

As any active tenant member, I can ask a short follow-up ("and last quarter?", "which supplier was
that?") without repeating the full question, so the analyst is usable as a conversation rather than
one isolated lookup at a time.

**Acceptance scenarios**

1. Given a prior question and answer in the same session, when a follow-up question depends on
   that context, then the analyst resolves it using the prior turn's grounded entities (the same
   supplier, the same date range) rather than asking the member to repeat themselves.
2. Given a follow-up that changes the subject entirely, when it is submitted, then the analyst
   treats it as a new grounded question rather than forcing a stale context onto it.

### US4 - Review my own question history (P3)

As any active tenant member, I can see the questions I've asked and the answers given, so I can
revisit a number I looked up earlier without re-asking it.

**Acceptance scenarios**

1. Given prior questions in this tenant, when a member opens their history, then only their own
   conversations are listed, in reverse chronological order, cursor-paginated.
2. Given a past conversation, when it is reopened, then the original answers and citations are
   shown exactly as originally given, not recomputed against current data.

### Edge Cases

- What happens when the same question is asked twice in a row? Each ask is answered fresh against
  current data (no caching that could go stale); the analyst is not idempotent in the mutation
  sense — repeats are not an error, they're just two independent reads.
- How does the system handle a question that is answerable but the underlying data conflicts
  (e.g., two contradictory records)? The answer must surface the conflict and cite both records
  rather than silently picking one.
- What happens when a tenant has no data at all for the asked-about category? The analyst states
  that no records exist for the request rather than returning a zero or an empty calculation as if
  it were a real answer.

## Requirements

### Functional Requirements

- **FR-001**: The analyst MUST answer only from the requesting member's own tenant data, retrieved
  at query time — it MUST NOT be pretrained or fine-tuned on any tenant's data, and MUST NOT answer
  from general knowledge when tenant data is silent on the question.
- **FR-002**: V1 MUST support natural-language questions in these categories only: spend and
  savings (by supplier, product, branch, cost centre, date range), supplier performance and risk
  (drawing on the existing v1/v2 scorecard), order and quotation status and history, and reorder
  forecast status. A question outside these categories MUST receive an explicit
  "can't answer that yet" response, never a best-effort guess.
- **FR-003**: Every answer MUST cite at least one typed, tenant-pinned source record (purchase
  order, quotation line, landed cost, saving record, supplier scorecard/risk snapshot, delivery
  receipt, or reorder proposal) that a member can open and independently verify.
- **FR-004**: Every answer involving a number (a sum, an average, a rate, a trend, a comparison)
  MUST show the calculation: the exact records included, the formula applied, and the result —
  using the same `Decimal` arithmetic and explicit currency handling as R4.0/R4.1. No currency
  conversion or cross-currency aggregation.
- **FR-005**: Question understanding (mapping the member's free-text question to a supported
  category, entities, and date range) MAY use a language model, but the model MUST NOT generate
  the answer's factual content, numbers, or citations — those come only from deterministic
  retrieval and calculation against tenant records. This is retrieval-augmented question routing,
  not open generation.
- **FR-006**: When no tenant record grounds an answer, the analyst MUST say so explicitly and MUST
  NOT fabricate a plausible-sounding number, record, or supplier name.
- **FR-007**: Cross-tenant and unknown identifiers referenced in a question MUST be treated
  identically to "no such data exists" — the response MUST NOT reveal whether the identifier
  belongs to another tenant.
- **FR-008**: A conversation MUST persist as an ordered sequence of question/answer turns scoped
  to the tenant and the asking member. A follow-up turn MAY resolve pronouns and omitted entities
  from the immediately preceding turn's grounded entities only, not the full conversation history.
- **FR-009**: Conversations and their turns MUST be tenant-scoped and creator-scoped for read
  access — a member sees only their own conversations; owners and buyers additionally MAY list
  all conversations in the tenant for oversight, since these are business records, not private
  messages.
- **FR-010**: An answer already given MUST be immutable once returned. Reopening a past
  conversation MUST replay the original stored answer and citations, not recompute them against
  current data.
- **FR-011**: Every analyst response MUST expose `release_posture = g3_unmet`. The analyst MUST
  NOT create, submit, approve, or send a purchase request, purchase order, or supplier message
  under any circumstance, regardless of how the question is phrased.
- **FR-012**: Every question and answer MUST be recorded as an immutable, append-only audit event,
  consistent with the existing `audit_event` convention.
- **FR-013**: Every new tenant-scoped table MUST carry `tenant_id`, composite tenant foreign keys,
  forced RLS, `USING`/`WITH CHECK` policies, and automated cross-tenant isolation tests.
- **FR-014**: All user-facing strings MUST come from shared English and Arabic catalogues; the UI
  MUST support RTL, keyboard operation, and WCAG 2.1 AA.
- **FR-015**: Asking a question MUST be rate-limited per member to bound language-model spend and
  prevent abuse, consistent with the project's existing rate-limiting conventions elsewhere in
  the API.

### Key Entities

- **AnalystConversation**: A tenant- and member-scoped thread of question/answer turns. Has a
  creation timestamp and belongs to exactly one member.
- **AnalystTurn**: One question and its answer within a conversation. Immutable once created.
  Holds the member's question text, the resolved category and entities, the generated answer
  text, and its citations.
- **AnalystCitation**: A typed, tenant-pinned link from a turn to exactly one source record
  (purchase order, quotation line, landed cost, saving record, scorecard/risk snapshot, delivery
  receipt, or reorder proposal), mirroring the existing evidence-reference pattern from R4.1.

## Success Criteria

### Measurable Outcomes

- **SC-001**: For every supported question category (FR-002), a member can get a cited, calculated
  answer in a single question without needing to already know which report or screen holds it.
- **SC-002**: 100% of answers that include a number also include the calculation and record
  citations behind it — verified automatically, not by spot check.
- **SC-003**: 0% of answers reveal the existence of another tenant's data, under automated
  cross-tenant adversarial testing.
- **SC-004**: 0% of answers state a fact that isn't traceable to an actual tenant record, under a
  fixture-based grounding test suite covering each supported category.
- **SC-005**: A follow-up question that depends on the prior turn resolves correctly without the
  member repeating the full original question, in automated conversation-flow tests.
- **SC-006**: Full API tests, Angular tests, production build, migration verification, and
  physical API consumption pass while G3 remains recorded as unmet.

## Out of scope

- Any autonomous action: drafting, sending, or approving a purchase request, purchase order, or
  supplier message.
- Answering from general knowledge, the public internet, or any source outside the tenant's own
  workspace data.
- Cross-tenant benchmarking or comparison ("how do I compare to similar businesses").
- Voice input/output and any channel other than the existing web app.
- Proactive/unprompted analyst messages — R4.2 is question-answering only, not alerting (the
  existing Alerts Inbox already owns proactive notification).
