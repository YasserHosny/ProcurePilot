# ProcurePilot — Ingestion Wave 6 Execution Plan (Testing & Quality)

**Written**: 2026-09-17, following Wave 5's completion and merge onto `013-automated-ingestion`
(commit `3af0498`), while a live browser walkthrough of Wave 5's UI runs in parallel via Agy
(dispatched directly by the user, not through this plan).

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 7, Tasks T030–T036.

**Mode**: unlike every prior wave, this one is *not* "implement N independent things in
parallel" — grounding pass (§0 below) found that four of the seven tasks (T030–T033) are
**already substantially covered** by tests written alongside their own backend tasks in Waves
1–4. What's actually new here is narrow and precisely scoped per task in §2. T034 (tenant
isolation) follows this feature's standing exception: **not delegated**, done in-house, same as
every other tenancy-boundary task on this feature. T030–T033's real remaining gaps route to
OpenCode (the test lane). T035 (E2E)/T036 (a11y) need the whole stack running and should not
start until T030–T034 land — see §3.

---

## 0. Grounding pass — what already exists (read before assigning anything)

Every backend task in Phases 1–4 shipped with its own tests (visible directly in
`specs/013-automated-ingestion/tasks.md`'s own entries for T009–T021). Phase 7's tasks.md
wording was written when the plan was drafted, before those tests existed, and still describes
scenario lists that substantially overlap what Waves 1–4 already built. Re-verified directly
against the actual test files (not the task list's one-line summaries) on 2026-09-17:

| File | Tests | Covers of T030–T034's literal scenario lists |
|---|---|---|
| `tests/unit/test_email_parser.py` | 7 | from/subject/body, thread headers, single + multiple attachments, **content-type mismatch** (a real MIME edge case), missing message-id, missing from-address |
| `tests/integration/test_ingestion_matcher.py` | 5 | **domain match, address-history match (beats domain), thread match, no-match, cross-tenant isolation** — all four of T030's named matcher scenarios, already done |
| `tests/integration/test_ingestion_webhook.py` | 5 | valid/invalid secret, unknown recipient (202, no leak), **disabled tenant → bounce**, **daily limit reached** (T031's "rate limit test") |
| `tests/integration/test_ingestion_orchestrator.py` | 4 | matched, **unmatched → review task**, no-attachment/body-as-document, **duplicate message-id** (T031's "deduplication test") |
| `tests/integration/test_capture_service.py` | 5 | happy path (PDF only — see gap below), no-supplier, oversized rejection, unsupported MIME rejection, cross-tenant/unknown supplier |
| `tests/integration/test_catalogue_import.py` | 5 | one line per row + matching invoked, per-row bad-currency, all-rows-bad-currency, unmappable column → failed import, cross-tenant supplier |
| `tests/integration/test_ingestion_email_config.py` | 5 | get-before-exists, owner create+read, **non-owner cannot update (RBAC)**, enable/disable, forwarding-address uniqueness — **no cross-tenant test** |
| `tests/integration/test_ingestion_email_log_listing.py` (T019) | 9 | includes cross-tenant isolation |
| `tests/integration/test_catalogue_import_history.py` (T020) | 5 | includes cross-tenant supplier → 404 |
| `tests/integration/test_ingestion_stats.py` (T021) | 6 | includes cross-tenant isolation |

**Consequence**: T030–T033 are not "write these test suites" — they are "close these five
specific, real gaps." Do not re-derive or duplicate the scenarios in the table above; a session
handed the literal tasks.md wording without this table would very likely reinvent tests that
already exist and pass. This grounding table is the actual spec for T030–T033; tasks.md's own
wording under Phase 7 is stale relative to it.

## 1. Non-negotiables

Unchanged from every prior wave. Specifically relevant to a testing-only wave: no test may use a
service-role client to *prove* isolation — proving RLS means proving the authenticated,
tenant-scoped path returns nothing, not that a service-role bypass exists (it does, by design,
for workers; that's not what's under test here). `audit_event` assertions, if any test touches
it, must never assert an `UPDATE`/`DELETE` path succeeds — only that it's rejected.

## 2. Task scope — the actual remaining gaps

### T030 — Email parser: real remaining gaps only

The matcher side of T030 is **done** (see §0) — do not touch `test_ingestion_matcher.py` unless
you find an actual bug while reading it. The parser side has real gaps, all in
`tests/unit/test_email_parser.py`:

- **Body-only / no-attachment email at the parser level.** `test_ingestion_orchestrator.py` has
  `test_no_attachment_email_stores_body_text_as_the_document`, which proves the *orchestrator*
  handles this correctly, but nothing at the *parser* unit-test level directly asserts
  `parse_email()`'s own output shape for a body-only message (empty `attachments`, `body_text`
  populated). Add it — cheap, and pins the contract the orchestrator depends on independently of
  the orchestrator's own test.
- **`multipart/alternative` (text/plain + text/html parts in the same message).** Real-world
  mail clients routinely send both. Nothing today proves `parse_email()` picks the plain-text
  part and doesn't, say, concatenate both or pick html. Add one test.
- **Non-ASCII subject via RFC 2047 encoded-word** (`=?UTF-8?B?...?=`) and a **non-UTF-8 body
  charset** (e.g. `iso-8859-1` or `windows-1256` — real for Arabic-market mail gateways given
  this product's own ar locale). Confirm `parse_email()` decodes both without raising or
  mangling text. This is a genuine, unexercised edge case for a product with a real Arabic user
  base.
- **Malformed/truncated raw bytes that aren't a valid email at all.** Confirm `parse_email()`
  raises `EmailParseError` (not an unrelated exception) rather than crashing the worker.
- **Fixture format — a real decision, not a default.** `_build_email()` (the existing
  programmatic `EmailMessage` builder in the test file) is arguably *better* practice than
  on-disk `.eml` fixtures (no binary fixture drift, self-documenting inline), but it doesn't
  match tasks.md's literal "sample .eml files" wording. Recommendation: **keep the builder
  pattern**, extend it for the new cases above — real `.eml` files add fixture-maintenance
  weight for no real benefit here since every case above is expressible in a few lines of
  `EmailMessage` construction. Whoever picks this up should say explicitly in the PR why (or
  override this recommendation with a reason), not silently do one or the other.

### T031 — Email ingestion end-to-end: one real gap

Deduplication, the unmatched→review-task path, and the daily-rate-limit path are **already
tested** (see §0 table) — do not re-add them. The one real gap: **nothing exercises the actual
worker** (`workers/email_ingestion_worker.py`)'s `FOR UPDATE SKIP LOCKED` claim loop end-to-end.
Every existing test calls `process_inbound_email` (the orchestrator function) or the webhook
handler directly — T012's own tasks.md entry says so plainly ("No dedicated worker-level test
file; covered indirectly via the orchestrator tests").

Add `tests/integration/test_email_ingestion_worker.py`: insert a real `ingestion_jobs` row
(`status='pending'`), run the worker's claim function against the disposable Postgres instance,
assert it: (a) claims exactly one job under `FOR UPDATE SKIP LOCKED` (a concurrent second
claimant gets nothing — two connections racing for the same row, assert only one wins), (b) on
success marks the job `completed` and the expected `document`/`quotation`/`extraction_job` rows
exist, (c) on a forced failure (e.g. malformed payload) retries up to `max_attempts` (3) then
goes terminal `failed`, (d) `tenant_id` used for the actual processing comes from the **claimed
job row**, never re-derived from any payload field — this is the specific untrusted-payload
discipline T012's own entry calls out, and it deserves its own explicit assertion, not just
implicit correctness.

No existing worker test in this codebase (`test_export_worker.py`, the closest precedent) tests
the actual claim-loop under concurrency either — it only tests payload shape and queue
configuration. This gap isn't unique negligence in this feature; still worth closing here since
it's the one piece of Wave 6 genuinely un-tested anywhere.

### T032 — Capture endpoint: one narrow gap

Four of `test_capture_service.py`'s five tests match T032's scenarios exactly. The one gap: the
happy-path test (`test_capture_creates_pending_quotation_and_queues_extraction`) only exercises
a PDF (`delivery-note.pdf`, `application/pdf`). T032 explicitly asks for **both** "upload image →
..." and "upload PDF → same flow" as separate scenarios. Add a second happy-path test (or
parametrize the existing one) for an `image/jpeg` upload, asserting the same
document+quotation+extraction_job creation. Don't duplicate the oversized/unsupported-type/
cross-tenant cases — those are already generic across file type and already covered.

### T033 — Catalogue import: the design changed under this task; test the *real* design

Read T017's own tasks.md entry in full before touching this — the original acceptance-scenario
language ("offers created", "pending_review", "no duplicate offers") describes a design that
was **explicitly abandoned during implementation** in favor of "one reviewed `quotation` per
import, routed through the real `MatchingService.quotation_matches()` pipeline exactly as a
human-reviewed quotation would be." `test_catalogue_import.py`'s existing five tests are written
against the real, current design and are good — don't touch them.

The one scenario from T033's original list that still has a real, meaningful analog under the
new design and is **not** currently tested: **importing the same file twice.** The new design
creates a brand-new `quotation` + `quotation_line` rows and re-invokes the full matching
pipeline on *every* import call — there's no import-level dedup concept built in. Add a test
that calls `import_catalogue` twice with the identical file for the same supplier and asserts
the actual (not assumed) behavior: does it produce two independent `quotation` rows each
matched separately (most likely, given the design), and if so, does anything downstream (the
matching pipeline, `landed_cost` creation) break, silently duplicate, or behave unexpectedly on
the second call? This is a genuine unknown worth an explicit test and a written-down answer, not
an assumption either way.

### T034 — Tenant isolation: not delegated, done in-house per standing practice

One real gap identified in §0: `test_ingestion_email_config.py` has **no cross-tenant test** —
a second tenant's ability (or, correctly, inability) to read tenant A's `tenant_email_config` row
is never proven. Every other ingestion table already has cross-tenant coverage somewhere (see
§0 table) — email config is the one hole.

This codebase has two conventions for isolation tests, and both are legitimate for different
reasons (read `tests/integration/test_reporting_isolation.py`'s own top-of-file comment for why
it's separate — it was written test-first, ahead of the reporting module existing, for a
specific TDD-staging reason that does not apply here since every ingestion table is already
built and merged). The master `tests/integration/test_tenant_isolation.py` (1100+ lines,
`test_another_workspaces_<table>_are_invisible` pattern, shared `Workspace` fixture) is the
better fit for a feature whose implementation is already complete — add
`test_another_workspaces_tenant_email_config_is_invisible` (and, while in there, confirm
`ingestion_email_log`, `ingestion_jobs`, and `catalogue_imports` genuinely have entries too,
not just incidental coverage in their own per-endpoint test files — the master file existing
as the canonical, discoverable isolation surface for the whole product is the actual point of
non-negotiable #1, and scattered per-endpoint coverage doesn't fully satisfy that even where the
underlying behavior is correct).

I'll do this one myself directly rather than delegating, per this feature's standing tenancy
carve-out.

### T035 — E2E tests (Playwright): genuinely new, not started

Nothing here exists yet — Wave 5's frontend tests are all Karma/Jasmine with
`HttpTestingController` mocks, not real Playwright browser runs. Four flows per tasks.md: email
config setup, capture upload, catalogue import, dashboard stats display. Model on this
codebase's existing Playwright specs under `apps/web/e2e/` (or wherever `pnpm test:e2e` points —
read `playwright.config.ts` first) for the auth/tenant-seeding harness already in place; don't
reinvent login flow.

**Do not start this until T030–T034 are merged and, ideally, until Agy's live walkthrough
results are in** — if Agy's manual pass finds a real UI bug, writing E2E specs against the
current (buggy) behavior locks in the bug as "expected." Sequence this after both.

### T036 — a11y (axe-core): genuinely new, not started

`pnpm test:a11y` per CLAUDE.md's command list — zero violations is the bar, matching every other
feature. Scan all five Wave 5 components (`dashboard`, `email-config`, `email-log`, `capture`,
`catalogue-import`). Specific items tasks.md calls out: keyboard navigation for the file-upload
components (capture, catalogue-import — can a keyboard-only user reach and activate the file
input, the drag-drop zone's equivalent action, and the remove-file button?), RTL layout
verification (already partially self-checked during Wave 5's own review — grep for physical
`margin-left`/`padding-right`/etc. came back clean on all five — but a real axe-core + visual RTL
pass is still owed, that grep only proves no *known* anti-pattern, not that the RTL layout is
actually correct end to end).

Same sequencing note as T035 — after T030–T034, and ideally after Agy's findings.

## 3. Delegation mechanics

Lane map current as of 2026-09-17 (see memory `delegate-heavily-to-codex` for the live version —
do not reuse this snapshot in a future wave without checking it first): Agy used intensively as
the default for substantial work; Cursor (`auto`) for mid-complexity; OpenCode
(`opencode-go/muse-spark-1.2-contributor-free`) for trivial/mechanical only; Codex paused until
2026-09-19 12:09; Claude-in-house minimized to the tenancy carve-out and genuinely-too-small
tasks. `opencode-go/kimi-k2.7-code`/`kimi-k3` are gone — never propose them.

Four independent tasks, no file overlap (`test_email_parser.py`; a new
`test_email_ingestion_worker.py`; `test_capture_service.py`; `test_catalogue_import.py`), so
genuinely parallel, not sequential, regardless of which lane each lands on:

- **T030** (parser edge cases — charset/encoding judgment calls, e.g. what "correct" RFC 2047
  and non-UTF-8 decoding looks like) → **Agy**.
- **T031** (worker concurrent-claim test — the one task in this wave with real correctness
  stakes: proving `FOR UPDATE SKIP LOCKED` exclusivity under genuine concurrency, not a
  sleep-based fake) → **Agy**.
- **T032** (add one `image/jpeg` happy-path test, essentially copy-adapt of the existing PDF
  happy-path test) → **OpenCode**, trivial lane.
- **T033** (repeat-import test — needs to actually run it twice and characterize real,
  unknown-in-advance behavior, not just transcribe a known expectation) → **Cursor**, mid lane.
  No packaged `cursor-delegate` skill exists yet; dispatch by hand (brief → `cursor-agent` →
  verify gates myself → commit myself) or run `/delegate-setup` first to formalize the lane.

- **T034**: done in-house, not delegated (standing tenancy carve-out — this is the one thing
  "minimize self-work" does not reach into).
- **T035, T036**: held. Do not dispatch until T030–T034 are merged and the backend+frontend
  suites are both green, and ideally not until Agy's live walkthrough (running now, dispatched
  directly by the user, outside this plan) has reported back — its findings may change what
  T035's specs should actually assert.

## 4. Review protocol

1. Re-run every touched test file myself against a fresh disposable Postgres before merging any
   of T030–T033 — same "never trust a self-report" discipline as every prior wave.
2. For T031's new worker test specifically: verify the concurrent-claim assertion actually
   exercises two real connections racing (not a single-threaded fake that trivially "proves"
   exclusivity) — this is the one new test in the whole wave with real concurrency-correctness
   stakes.
3. For T034: confirm the new isolation assertions actually fail if the RLS policy is temporarily
   disabled (a manual sanity check — comment out `FORCE ROW LEVEL SECURITY` locally, confirm the
   new test goes red, then restore it) before trusting it proves anything. This is the standard
   this project already holds tenancy tests to; apply it here too since it's new coverage, not a
   copy of an already-proven pattern.
4. Full backend suite green after T030–T034 all merge together (baseeline: ~1049+ passed as of
   Wave 4, growing wave over wave — get the exact current number from a real run at merge time,
   not from grep).

## 5. What comes after

**Update 2026-09-17, after this wave's dispatches ran**: T030, T031, T033, and T034 are merged
(see `specs/013-automated-ingestion/tasks.md`'s own entries for exactly what each closed — the
grounding table in §0 above held up; no task needed more than its scoped gap). T032 hit a real,
unplanned blocker mid-wave: OpenCode's `muse-spark` (the `simple` lane's model at the time) failed
every dispatch with a generic server error, confirmed independent of the brief by testing the raw
CLI directly. The user's response was to remove OpenCode from the fleet entirely, not just swap
models — see `delegate-heavily-to-codex` memory. T032 was re-dispatched to Agy and is either
already merged or still running by the time you're reading this; check `tasks.md` for its real
current status rather than trusting this paragraph.

T035/T036 got their own dedicated plan once both of this wave's hold conditions (T030–T034
merged; Agy's live walkthrough reported back) were satisfied — see
`parallel-execution-plan-ingestion-wave7.md`, not this document, for their real scope. Do not
re-plan them here.

Phase 8 (T037–T042 — API spec, data dictionary, user docs, test-strategy doc, OpenAPI contract,
security review) is the feature's close-out, after Wave 7. T042 (security review) should happen
last of all — a security review of surfaces whose E2E/a11y coverage doesn't exist yet is
reviewing an incomplete picture.

## 6. Cautions

- Don't let T031's new worker test become flaky by racing real wall-clock timing for the
  concurrent-claim assertion — use two real DB connections/transactions with explicit
  `FOR UPDATE SKIP LOCKED` ordering, not a `sleep()`-based race.
- T033's repeat-import test might reveal the "two independent matched quotations from one file
  imported twice" behavior is actually undesirable product behavior, not just an untested one —
  if so, that's a real product-scope finding to flag back, not something to silently patch
  mid-test-wave (T033 is a testing task, not a design-change task).
- Don't let a T036 a11y violation on an existing (non-ingestion) component that the axe-core scan
  incidentally touches (e.g. the shared shell/nav) get silently fixed as a drive-by — flag it
  separately; this wave's scope is the five ingestion components specifically.
