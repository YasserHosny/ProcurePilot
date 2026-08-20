# Phase 0 Research: Catalogue and Suppliers

**Feature**: 002-catalogue-suppliers | **Date**: 2026-08-20

Chunk 4.1 settled the stack, the tenancy pattern and the audit trail. This document resolves only
what chunk 4.2 genuinely adds.

---

## R1 — Exact arithmetic for normalised quantities

**Decision**: `pack_count integer`, `unit_size numeric(18,6)`, `base_quantity numeric(18,6)` — a
**generated column**, computed by the database as `pack_count * unit_size`.

**Rationale**: Constitution Principle II demands that normalisation be a pure, replayable function.
A generated column makes it one by construction: the value cannot drift from its inputs because
nothing can write it independently, and recomputation is not a separate code path that might one day
disagree with the original.

`numeric`, never `double precision`. Binary floating point cannot represent 0.1, so `3 × 0.33` would
not reliably equal `0.99`, and every landed-cost comparison in chunk 4.4 sits downstream of this
number. Six decimal places accommodates millilitre-scale unit sizes without inviting false precision.

**Alternatives considered**:
- *Compute in the application and store the result* — one more place for the rule to live, and the
  stored value can silently diverge from its inputs after an edit. The database is the only layer
  every writer passes through.
- *Store only the inputs and derive on read* — appealing, but every query that sorts or filters by
  quantity then recomputes, and comparison in chunk 4.5 will do exactly that at volume.
- *Integer minor units, as with money* — correct for currency, wrong here: pack sizes are genuinely
  fractional across incompatible units, and there is no equivalent of "the smallest coin".

---

## R2 — Money as amount plus currency, from the first migration

**Decision**: every monetary value is two columns — `<name>_amount numeric(18,4)` and
`<name>_currency text` referencing `supported_currency(code)` — with a check constraint requiring
both to be present or both absent. No default currency anywhere.

**Rationale**: Principle VII, and the reason it exists. This is the first money in the product, and
retrofitting a currency onto stored amounts means a migration over financial data — the most
expensive kind, and the one most likely to be got wrong under pressure. The `Money` type in
`packages/domain-types` already encodes the matching rule on the client: amount as a decimal string,
never a float, and arithmetic across currencies refused outright.

The check constraint matters more than it looks. Without it, a nullable currency column eventually
holds nulls, and something downstream infers a default — which is how a supplier's £500 minimum
becomes a plausible, wrong ﷼500.

**Alternatives considered**:
- *A single `money` column type* — Postgres's `money` type carries no currency, is locale-dependent
  on input, and is widely advised against for exactly this reason.
- *One workspace currency, applied implicitly* — tempting, and wrong: a workspace legitimately buys
  from suppliers who quote in another currency, and the roadmap's launch region is still open.
- *Storing minor units as integers* — defensible and common, but it needs a currency-specific
  exponent to interpret, and `numeric` already gives exactness without that lookup.

---

## R3 — CSV parsing

**Decision**: Python's standard-library `csv` module, with explicit dialect detection limited to
delimiter and quote character. No new dependency.

**Rationale**: the spec narrows scope to delimited text with a header row. The standard library
handles quoting, embedded newlines and escapes correctly, which is where naive `split(',')` parsers
fail. Adding pandas for this would pull a large numeric stack into the API image to read a few
thousand rows, and would introduce type coercion that actively works against FR-022 — pandas guesses
types, and a guess is precisely what a decimal separator must not be subject to.

**Decimal separators (FR-022)**: numbers are parsed with `decimal.Decimal` after an explicit,
unambiguous normalisation. A value containing both `.` and `,` is resolved by position — the last
separator is the decimal point. A value containing exactly one `,` and no `.` is **refused** rather
than guessed, because `1,234` is 1234 in one convention and 1.234 in another, and the roadmap
explicitly names decimal-separator errors as a known source of silent financial leakage.

**Alternatives considered**:
- *pandas* — heavyweight, and its type inference is a liability here rather than a convenience.
- *A locale-aware parse driven by the workspace's region* — plausible, but a file exported by a
  supplier in another country does not follow the buyer's locale, and the failure is silent.

---

## R4 — All-or-nothing import, in the request

**Decision**: validate the entire file in memory, then write every row in **one database
transaction**. Run it inside the request for now.

**Rationale**: FR-017 requires all-or-nothing, and a transaction is exactly that guarantee, enforced
by the database rather than by application care. For the file sizes this chunk targets — hundreds to
low thousands of rows — a single transaction completes well inside SC-002's 60 seconds.

Chunk 4.1 deliberately deferred Redis (research R7 there) because nothing needed a queue. That is
still true: adding one now to avoid a two-second request would be introducing infrastructure to
solve a problem the product does not yet have.

**Revisit when**: an import exceeds roughly 5,000 rows, or SC-002 is missed on real customer files,
or the transaction starts holding locks long enough to affect other users. Recorded so the deferral
is a decision with a trigger rather than an omission.

**Alternatives considered**:
- *Row-by-row commit with a rollback log* — simpler to write, and it cannot satisfy FR-017: a crash
  mid-file leaves a catalogue that is neither the old one nor the new one.
- *Background job with polling* — the eventual answer at volume, and premature now. It also makes
  the confirm-before-save flow harder, since the preview and the commit would span two requests
  against a file the server must then retain.

---

## R5 — Where the canonical spine lives, and why it breaks the pattern

**Decision**: `canonical_product` is **shared across workspaces** and carries no `tenant_id`. It is
readable by any authenticated user and writable only through the application's own insert path.
`workspace_product` holds everything workspace-specific and is tenant-scoped in the usual way.

**Rationale**: roadmap §10.1 calls for a shared canonical spine so that cross-tenant benchmarking
becomes possible later without a migration over every customer's catalogue. The split keeps the
shared layer free of anything identifying: brand, name, variant, GTIN, base unit — no workspace's
naming, preferences, substitutes or suppliers.

This is the one place in the schema where Principle V's uniform pattern does not apply, so it is
called out in the plan's Complexity Tracking rather than left for a reviewer to notice. **A reviewer
should check this table first** if workspace data ever appears somewhere it should not.

**Alternatives considered**:
- *Per-workspace product rows only* — uniform, safer to reason about, and it forfeits the year-3
  benchmarking asset the roadmap names as a defensible moat.
- *Canonical products owned by a system tenant* — preserves the uniform pattern at the cost of a
  fictional workspace that every policy must special-case anyway.

---

## R6 — Whether anything here needs a SECURITY DEFINER function

**Decision**: **no**. Every operation in this chunk is performed by an authenticated member acting
inside their own workspace, which is exactly what RLS expresses.

**Rationale**: chunk 4.1 accumulated four SECURITY DEFINER functions (migrations 0007–0010), each
because an operation genuinely crossed or preceded the tenancy boundary — writing an audit event
before authentication, listing workspaces from outside one, accepting an invitation into a workspace
you are not yet in, resolving that invitation. None of those shapes appears here.

Stated explicitly because the pattern is now familiar enough to reach for by habit. Every such
function is an RLS bypass that has to be reasoned about individually; adding one where a plain policy
suffices spends that budget for nothing. If a fifth becomes necessary in this chunk, it needs the
same justification the first four carry.

---

## R7 — Archiving rather than deleting

**Decision**: products and suppliers carry a `status` including an archived state. No destructive
delete is exposed. Deleting a supplier that is referenced is refused, with archiving offered.

**Rationale**: consistent with `membership.status` in chunk 4.1, and required by the audit
obligations — a savings claim in chunk 4.6 must remain explicable, which means the records it
references must still resolve. A deleted supplier turns a historical comparison into an unanswerable
question.

**Consequence**: every list query filters by status by default, and every foreign key resolves
regardless of status. Both are easy to forget, so both are covered by tests.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| R1 | Normalised quantity | `numeric(18,6)` generated column, `pack_count * unit_size` |
| R2 | Money | Amount + currency columns, check-constrained together, no default, no conversion |
| R3 | CSV parsing | Standard-library `csv` + `Decimal`; ambiguous separators refused, not guessed |
| R4 | Import atomicity | One transaction, in-request; revisit above ~5,000 rows |
| R5 | Canonical spine | Shared, no `tenant_id`, no workspace-identifying data — the one pattern exception |
| R6 | SECURITY DEFINER | None needed; plain RLS covers every operation here |
| R7 | Deletion | Archive instead; refuse deleting referenced records |

**No NEEDS CLARIFICATION items remain.**
