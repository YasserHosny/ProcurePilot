# ProcurePilot — Wave 9 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator). This is the first wave against a new spec,
`specs/010-mobile-approvals-receipt/` (R2.3, roadmap §7.2/§12) — the spec, plan, research,
data-model, contracts, and tasks.md for this feature were written and merged to `main` at
`08cceb8` immediately before this plan, planning-only, with zero implementation.

**Orchestration model** (unchanged from Waves 6-8, user-directed): neither the orchestrator role
nor an implementer assignment is fixed to one model. Pool: **Claude (in-house), Codex, Agy** —
OpenCode rejoins 2026-09-14. If a dispatched model hits a limit or fails mid-task, re-dispatch
immediately to another pool member; do not schedule a wait for a specific reset time.

---

## 0. Repo state right now

- `main` @ `08cceb8`. `specs/010-mobile-approvals-receipt/tasks.md` defines 37 tasks (T001-T037)
  across Setup, Foundational, three user stories, and a Cross-cutting phase — see that file for
  the full breakdown; this plan does not repeat it.
- **This wave covers tasks.md's Phase 1 (Setup, T001-T005) and Phase 2 (Foundational, T006-T008)**
  — the schema and shared-plumbing work every later user-story phase depends on. Per tasks.md's
  own Dependencies section, no user-story phase (US1/US2/US3) may start before this wave lands.
- **This entire wave is kept in-house**, not delegated — tasks.md's own Delegation Lanes section
  already names T001-T006 as in-house candidates (tenancy/RLS-bearing migrations and the
  approve-endpoint's status-transition change, matching this project's standing practice of
  keeping correctness-critical write-path and RLS-policy work in-house by default, the same
  reasoning that kept T002/T012/T017/T031/T037/T042 in-house in prior waves). T007-T008 are small,
  independent, and naturally bundled with the rest of this phase rather than justifying a separate
  dispatch round-trip.
- **The one genuinely tricky migration-ordering detail** (already flagged in data-model.md and
  tasks.md T001): `ALTER TYPE purchase_request_status ADD VALUE` must run in its own migration
  file, with no other statement in the same file — referencing a value added by `ADD VALUE` in the
  same transaction block it was added in is a standing PostgreSQL restriction, not specific to
  this project. T001 (enum values) and T002 (columns that will later be populated using those
  values) must land as two separate migration files, in that order.

---

## 1. Non-negotiables (unchanged from Wave 1-8)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied (spec/plan/research/data-model/contracts/
   tasks for 010-mobile-approvals-receipt already committed and merged).
2. **Tenant isolation is enforced in the database.** Both new tables in this wave
   (`delivery_quality_issue`, `delivery_quality_issue_photo`) need `ENABLE`+`FORCE` RLS with a
   derived-visibility policy via `EXISTS` join to their parent `purchase_request` — mirroring
   `purchase_request_line`'s own existing pattern exactly (data-model.md), not a new isolation
   shape.
3. **A cross-tenant read returns "not found," never "forbidden."** Applies to every new table this
   wave adds, same as every prior chunk.
4. **No secrets in the repo.**
5. **Every user-facing string comes from `packages/i18n`.** Not directly exercised by this wave's
   own tasks (Setup/Foundational adds no UI text), but any test fixture data must not hardcode
   copy that later phases will need to look up as a real key.
6. **Every monetary value carries an explicit currency.** Not relevant — neither new table stores
   money.
7. **`audit_event` is append-only.** Not touched by this wave directly; T006's approve-endpoint
   change does not alter its existing audit call, only adds a status transition alongside it.
8. **No autonomous purchasing.** T006's `approved -> ordered` transition is automatic *given an
   already-human-made decision* — it does not itself decide anything; the human authorization gate
   remains exactly where 008-requests-approvals already put it. Constitution Principle III's gate
   for this wave is specifically: confirm T006 adds no new way to reach `approved` that bypasses
   the existing decision check.
9. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Since this wave is entirely in-house, "reviewer" here means: every gate below is actually run
   against a real disposable Postgres before landing, not assumed from reading the diff — the same
   discipline applied to every delegated track in every prior wave.

---

## 2. Wave 9 scope — tasks.md Phase 1 (Setup) + Phase 2 (Foundational)

### Track: in-house (Claude) — T001-T008

**T001** — New migration file adding `'ordered'` and `'delivered'` to the `purchase_request_status`
enum type. No other statement in this file (see §0's migration-ordering note).

**T002** — New migration file (landing after T001) adding `delivered_at`,
`delivery_confirmed_by_membership_id`, `has_delivery_discrepancy` to `purchase_request`, and
`quantity_received` to `purchase_request_line`, with the `quantity_received >= 0`-or-null check
constraint (data-model.md).

**T003** — New migration creating `delivery_quality_issue`: tenant-scoped, FK to `purchase_request`
`(tenant_id, id)` with `on delete cascade`, `check (char_length(description) > 0)`, `ENABLE`+
`FORCE` RLS, a derived-visibility RESTRICTIVE policy via `EXISTS` join to the parent request
(mirroring `purchase_request_line`'s own policy shape — read that migration first, copy its
pattern, don't reinvent it), insert-only grant to `authenticated` (no `UPDATE`/`DELETE` this
release — mirrors `low_stock_report`'s own insert-only posture after its review-fix migration).

**T004** — New migration creating `delivery_quality_issue_photo`: same shape as T003, FK to
`delivery_quality_issue` `(tenant_id, id)`.

**T005** — New migration creating the `quality-issue-photos` Storage bucket and its
tenant-isolation-by-object-path policy — read
`supabase/migrations/20260819000020_quotation_storage.sql` in full first and copy its policy
structure exactly (same `storage.foldername(name)` tenant-segment check), substituting the new
bucket id.

**T006** — Wire the `approved -> ordered` automatic transition into
`RequestsService.approve_request()` (`apps/api/src/procurepilot_api/modules/requests/service.py`).
The existing pre-decision checks, authorization, and audit call are unchanged; the only change is
that the same write that sets `status = 'approved'` also sets it to `'ordered'` in the same
statement (there is no intermediate `'approved'`-only state observable after this change — a
decision that approves a request lands it directly on `'ordered'`). `reject_request()` is
untouched. **This is the highest-scrutiny task in this wave** (Constitution Principle III,
non-negotiable 8 above) — verify directly against a real disposable Postgres that a rejected
request never reaches `ordered`, and that `ordered` is reachable only through this one code path,
not through any other write.

**T007** — Add the new `PurchaseRequest`/`PurchaseRequestLine` fields (data-model.md) to
`apps/mobile/lib/core/api/models.dart`.

**T008** — Define the injectable camera abstraction in `apps/mobile/lib/core/camera/` (interface +
real implementation + test fake), mirroring `apps/mobile/lib/core/auth/biometric_gate.dart`'s exact
shape (research.md R4). Do not add a concrete camera/image-picker package to `pubspec.yaml` unless
genuinely needed to compile the real implementation — if a stand-in (matching the
`StandInNotificationPermission` precedent from Wave 6) is sufficient for this task's own scope,
prefer it and leave the real plugin selection to whichever wave builds T030 (the screen that
actually needs to capture a photo).

**Land as**: two commits directly on `main` (backend migrations+T006 as one, mobile T007-T008 as
another) — or one, if that proves cleaner once the actual diff is in hand; no fixed rule, use
judgment matching how prior in-house tracks landed.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T001-T008 | Claude (in-house) | independent read-only pass by another pool member (Codex, or Agy if Codex is unavailable) before landing — same precedent as every prior in-house track (T031, T037, T042) |

T006 in particular should be the reviewer's primary focus, per §2's own note — force the specific
scenario of a rejected request and confirm it never reaches `ordered`, not just read the diff and
agree it looks reasonable.

---

## 4. What comes after

Once T001-T008 land and are independently reviewed, tasks.md's own Dependencies section unblocks
all three user-story phases (US1/US2/US3) to proceed in any order, with the standard "don't run
two implementer dispatches at once" resource-contention sequencing still applying. The natural next
wave (Wave 10) covers Phase 3 (US1 — decide on a pending request from mobile, T009-T016), tasks.md's
own suggested MVP scope. Waves 11 (US2, T017-T023), 12 (US3, T024-T032), and 13 (Cross-cutting,
T033-T037) follow the same one-phase-per-wave pattern used throughout this feature's predecessor,
009-mobile-app-mvp.

---

## 5. Cautions

- **Don't let T006 become a second decision path.** The gate is specifically that `ordered` is
  reachable ONLY as a side effect of the existing, unchanged approval check — not a new
  status-setting endpoint, not a default, not something a client can set directly.
- **Don't skip the migration-ordering split for T001/T002.** A single migration file that both adds
  enum values and immediately uses them will fail outright — this is not a style preference.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.
