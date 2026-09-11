# ProcurePilot — Parallel Execution Plan (Claude / Codex / OpenCode)

**Written**: 2026-09-11, by Claude (orchestrator), for a 3-agent parallel run.
**Audience**: this document is shared verbatim with all three agents. Each agent should read the
whole thing, then act **only** on its own section — do not touch another agent's file scope, even
if you think you see a faster fix.

If you are Codex or OpenCode reading this without the orchestrating conversation's context: you
do not need it. Everything you need to know is below. If something here conflicts with what you
observe in the repo, stop and flag it rather than guessing.

---

## 0. Repo state right now (read this before doing anything)

- `main` @ `8e6f876`. R2.1 (Requests + Approvals, `specs/008-requests-approvals/`) backend and web
  frontend are both **merged and deployed**.
- R2.2 (Mobile MVP, `specs/009-mobile-app-mvp/`) has an approved **spec.md** and a reviewed
  mockup/design-system prompt set (`docs/product/r2.2-mobile-mvp-*`). It has **no `plan.md`,
  `research.md`, `data-model.md`, `contracts/`, or `tasks.md` yet.**
- **CI on `main` has two separate red states — do not confuse them:**
  1. **Pre-existing, unrelated to any of this work**: the `Backend tests` job fails on 6 tests
     (`test_arithmetic_mismatch_review.py`, `test_extraction_workflow.py`,
     `test_field_corrections.py`, `test_match_alias_learning.py` ×2,
     `test_quotation_versioning.py`) — `ModuleNotFoundError: No module named 'azure'` (the CI job
     never installs the `azure-ai-documentintelligence` extraction dependency) and
     `SupabaseException("Invalid API key")` (those tests' audit-log path builds a real Supabase
     client that rejects CI's fake test key). This has been red since before this plan existed.
     **Do not treat this as something you broke.** It is Track B's job to actually fix it (below).
  2. **New, as of the last few merges — a real regression**: the `Web unit tests` job now also
     fails, 2 of 269 specs, both in `RequestFormComponent — edit mode (T017)`
     (`apps/web/src/app/features/requests/request-form/request-form.component.spec.ts:317-344`).
     Likely cause (verify before fixing): `request-form.component.ts`'s `loadMembers()` (added
     recently to resolve an approver's email on the request-detail view) calls
     `this.api.members()` unconditionally in `ngOnInit` when editing an existing request, with no
     error handling — unlike the sibling `delegation-list.component.ts`, which wraps the same call
     in `catchError`. The older `T017` describe block's `TestBed` setup does not stub
     `ApiService.members`, so the unstubbed spy call likely throws inside `ngOnInit` and the whole
     `detectChanges()` cycle aborts before the template renders — which is why *every* assertion
     in both failing tests comes back null/undefined, not just one. **This is Track A's first
     task, below — fix it before starting anything else.**
- All of R2.1's test-coverage tasks (`specs/008-requests-approvals/tasks.md`, T022-T048) are done
  **except two E2E specs**: T033 (threshold-routing + delegation, real UI/API) and T041
  (budget-status warning visible on both the requester's and approver's view). Neither
  `apps/web/tests/e2e/threshold-routing.spec.ts` nor `request-budget-status.spec.ts` exists yet.
- A separate, uncommitted git worktree has pending changes to `AGENTS.md`,
  `apps/web/src/styles.scss`, and a new `docker-compose.web-dev.yml` — **these are not yours**,
  they belong to another, unrelated concurrent session. See §5.

---

## 1. Non-negotiables (apply to all three agents, every task)

These come from `.specify/memory/constitution.md` and `CLAUDE.md`. A task that violates one of
these is not done, regardless of what else it accomplishes.

1. **Specification precedes code.** `constitution → specify → clarify → plan → tasks → analyze →
   implement`. **No one writes R2.2 implementation code — no Flutter, no new backend endpoints,
   no `apps/mobile/` changes — until `specs/009-mobile-app-mvp/tasks.md` exists and has been
   reviewed.** Track A (below) is what produces that; everything R2.2-shaped in this plan stops at
   planning artifacts.
2. **Tenant isolation is enforced in the database**, not app code: `ENABLE`+`FORCE` RLS, policies
   with both `USING` and `WITH CHECK`, JWT-claim tenancy only, cross-tenant reads return
   not-found never forbidden. If any task in this plan turns out to need a new migration or an RLS
   policy, **stop and hand it to Claude** — tenancy/migration work is not delegated by default in
   this project, regardless of which track surfaced the need.
3. **No autonomous purchasing.** Nothing produced in this plan may let a request reach "approved"
   without a recorded human decision (FR-006, `008-requests-approvals`).
4. **Every user-facing string comes from `packages/i18n`** (en + ar). No hardcoded copy, in any
   fix, however small.
5. **Every monetary value carries an explicit currency.**
6. **Secrets never enter the repo.** `.env` has live remote Supabase credentials — never paste
   them into a commit, a test fixture, or a log. If a task needs a database, use a disposable local
   Postgres (see Track B, which already has a working recipe from this session) or the CI-provided
   ephemeral one — **never point tests at the production remote Supabase.**
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Every review in §3 includes "re-run the gates yourself" as a mandatory step, not an optional one.

---

## 2. Wave 1 — right now, in parallel, zero file overlap

Each track's **file scope** is an allowlist — touch only what's listed. If a task needs a file
outside your scope, stop and say so rather than expanding scope on your own judgment.

### Track A — Claude

**File scope**: `apps/web/src/app/features/requests/request-form/**` (via Agy, see below),
`specs/009-mobile-app-mvp/**` (directly).

1. **Fix the Web unit tests regression** (§0.2). This is FE/UI code — per the standing rule below,
   dispatch it to **Agy**, don't patch it directly. Brief Agy to: (a) confirm the actual root
   cause (verify the diagnosis above, don't assume it), (b) fix `loadMembers()` in
   `request-form.component.ts` to fail gracefully (mirror `delegation-list.component.ts`'s
   `catchError` pattern exactly — same fallback shape), (c) confirm the two `T017` specs pass
   again, (d) re-run the full `request-form` spec suite and `ng lint`/`ng build` to confirm nothing
   else broke. Claude reviews Agy's diff (re-run the gates independently, read the diff against
   this brief) before landing it.
2. **Write the R2.2 technical plan** (`specs/009-mobile-app-mvp/plan.md`, `research.md`,
   `data-model.md`, `contracts/`, and `tasks.md`), following the same Speckit process and
   depth already used for `specs/008-requests-approvals/`. This is planning/documentation only —
   no code. Cover at minimum: the new backend surface R2.2 needs (a device push-token
   registration endpoint, a low-stock report endpoint + table — both new, both additive, neither
   touches `purchase_request`), reuse of the existing `/requests` and `/approvals/*` endpoints
   unchanged, and a task breakdown split cleanly enough that Wave 2 (§4) can be divided the same
   conflict-free way Wave 1 is.

**Land as**: one commit for the regression fix (own branch, e.g. `fix/request-form-members-error`),
one or more commits for the R2.2 planning artifacts (own branch, e.g. `plan/009-mobile-app-mvp`).
Do not merge either without Codex's review (§3).

---

### Track B — Codex

**File scope**: `.github/workflows/ci.yml`, plus read-only re-verification across
`apps/api/**` and `apps/web/**` (gates only, no feature edits).

1. **Fix the pre-existing `Backend tests` CI failure** (§0.1, item 1). Two independent problems in
   the same job:
   - Install the `azure-ai-documentintelligence` dependency (already a real project dependency,
     just missing from the CI job's install step) so `test_arithmetic_mismatch_review.py` and
     `test_extraction_workflow.py` stop failing on `ModuleNotFoundError`.
   - The audit-log path in `shared/audit.py` builds a real Supabase client and CI's fake test key
     gets rejected with `SupabaseException("Invalid API key")`, breaking
     `test_field_corrections.py` and `test_match_alias_learning.py` (×2) and
     `test_quotation_versioning.py`. Stub or mock the Supabase client for these specific tests (or
     for the CI job's audit-writer dependency generally) rather than changing production code's
     behavior — the goal is CI reflecting reality, not weakening the real audit path.
   - Verify: `Backend tests` goes fully green on a scratch push, no other job regresses.
2. **Final R2.1 backend QA pass.** Re-run every gate across `apps/api` (ruff, the full unit +
   contract + integration suite against a disposable Postgres — the same recipe: a
   `supabase/postgres:17.6.1.136` container with `supabase/migrations/*.sql` applied and a minimal
   `storage` schema shim for `20260819000020_quotation_storage.sql`). Report pass/fail counts.
   This is verification only — if you find a real bug, **stop and report it, don't fix it inline**
   (that would be new scope outside this task; Claude will triage where it goes).

**Land as**: one commit fixing the CI workflow, on its own branch (e.g. `ci/backend-tests-fix`).
The QA pass is a report, not a commit, unless it's clean (in which case nothing to land).

---

### Track C — OpenCode (+ Agy for any UI/FE fix it surfaces)

**File scope**: `apps/web/tests/e2e/threshold-routing.spec.ts` (new),
`apps/web/tests/e2e/request-budget-status.spec.ts` (new) — plus, only if either spec surfaces a
genuine UI defect, whatever component file Agy is briefed to fix for that specific defect (name it
explicitly when you find it, don't pre-guess).

1. **`threshold-routing.spec.ts`** (closes T033, `specs/008-requests-approvals/tasks.md`): prove,
   through the real UI/API, that requests at different value tiers route to the correct approver
   per an owner-defined threshold rule, and that an active delegation redirects a newly submitted
   request to the delegate instead. Mirror the existing E2E specs' setup conventions in the same
   directory (see `purchase-request-submission.spec.ts` and `organisation-branches.spec.ts` for the
   house style — fixtures, auth helpers, `data-testid` conventions).
2. **`request-budget-status.spec.ts`** (closes T041): prove the budget-exceeded warning appears on
   both the requester's own view and the approver's queue for an exceeding request, and is absent
   for one within budget or with no applicable budget — and that the request is still submittable
   and decidable either way (FR-011, never a hard block).
3. If either spec finds a real bug (not a flaky test — see the two E2E caution notes in §5 before
   concluding that), write it up precisely (repro, expected vs actual) and **dispatch the fix to
   Agy** rather than patching the component yourself — this is the cross-cutting rule in §5.
4. Run both new specs (and the existing R2.1 E2E suite, to confirm no collateral breakage) against
   the target the other E2E specs in this repo already use.

**Land as**: one commit per spec file (or both together, your call), on its own branch (e.g.
`test/r2.1-e2e-gaps`), plus a separate commit for any Agy-authored fix it required.

---

## 3. Review protocol

**Rule**: whoever implements a task never merges it themselves. A different, single named agent
reviews first — re-running the gates independently, reading the diff against this plan's brief for
that track, and only then either landing it or sending it back with specific, actionable
feedback (mirroring the "review, don't trust the self-report" discipline the delegate-CLI skills
already use in this project).

| Implementer | Reviewer |
|---|---|
| **Claude** (Track A: both the regression fix and the R2.2 planning artifacts) | **Codex** |
| **Codex** (Track B) | **Claude** |
| **OpenCode** (Track C) | **Claude** |

(The user specified the Claude↔Codex pair explicitly; OpenCode's reviewer was not specified, so
this plan assigns it to Claude, matching the orchestrator role Claude already has elsewhere in
this project. If the user wants Codex or a Claude→OpenCode→Codex round-robin instead, that's a
one-line change to this table — flag it before Wave 1 starts if so.)

**Each review must**:
1. Re-run the gates for that track's files (ruff/lint/build/tests as applicable) — never accept a
   self-reported "passed."
2. Read the diff against that track's brief in §2 — flag scope creep (more than was asked) and
   scope shortfall (less than was asked) equally.
3. Check the diff against §1's non-negotiables specifically.
4. Either approve and merge (to `main`, following the push-and-merge pattern already used all
   session: push the feature branch, `git merge --no-ff` into `main`, push `main` — never
   force-push, never merge without the gates green), or send it back with concrete, itemized
   feedback for the implementer to address, then re-review.

---

## 4. Wave 2 — blocked until Track A's `tasks.md` is reviewed

Do not start Wave 2 work from this document alone. Once Track A's `specs/009-mobile-app-mvp/`
planning artifacts are written and pass Codex's review (§3), the orchestrator (Claude) issues a
**Wave 2 plan** the same shape as this one, dividing the approved `tasks.md` the same
conflict-free way. Expect it to look roughly like:

- **Codex**: new backend endpoints (device registration, low-stock report) + their migrations —
  except any RLS/tenancy-policy piece of those migrations, which stays with Claude per §1.2.
- **OpenCode (+Agy)**: the Flutter mobile shell build-out, or whichever subset of
  `apps/mobile/` the approved tasks.md scopes to this wave, plus its own tests.
- **Claude**: reviewing Codex's Wave 2 backend work (continuing the §3 pattern), plus anything the
  approved tasks.md flags as tenancy/migration/RLS work.

This is a placeholder, not a commitment — the real Wave 2 split is only as good as the tasks.md it
divides, which doesn't exist yet.

---

## 5. Cautions

- **Cross-cutting rule for all three agents: any change to `apps/web/src/**` component, template,
  or style files goes through Agy, not through you directly.** Writing a new E2E *spec* file is
  not itself a UI change and doesn't need Agy; a fix to the *application code* that spec is testing
  does.
- **Do not touch, stage, commit, or discard** `AGENTS.md`, `apps/web/src/styles.scss`, or
  `docker-compose.web-dev.yml` — these are another concurrent session's uncommitted work. When you
  commit, `git add` only the specific files your task changed; never `git add -A` / `git add .`.
- **The pre-existing `Backend tests` CI failure (§0.1.1) is Track B's to fix — don't let any other
  track "helpfully" patch around it**; a workaround outside Track B's scope duplicates effort and
  risks masking the real fix.
- **E2E flakiness, not regression**: back-to-back full-suite Playwright runs can hit this
  project's 10-request/minute auth rate limit and look exactly like a real bug. If an auth-adjacent
  test fails, wait ~70s and re-run clean before concluding something broke. Separately, this
  project's E2E tests share one owner account across a spec file — a locale set to Arabic by one
  test leaks into a later English test unless the suite explicitly resets it; if you see an
  unexpected-language failure, check test order before assuming a real defect.
- **`.angular` cache bloat**: before dispatching anything to Agy, check `du -sh apps/web/.angular` —
  it has repeatedly grown large enough to time out Agy's workspace scan in this project. Clear it
  first if it's multiple GB.
- **Idempotency-Key**: a known, previously-deferred finding in this codebase is that
  `Idempotency-Key` is accepted on several mutation endpoints but not actually enforced end-to-end.
  If any task in this plan touches a mutation endpoint, don't widen that gap further, but also
  don't feel obligated to fix it — it's out of scope for this plan unless explicitly assigned.
- **If Codex hits a rate limit mid-run** (it happened for an extended stretch earlier in this
  project's history): Track A and Track C continue independently — they don't depend on Track B.
  Don't have Claude silently absorb Track B's work without asking the user first; report the stall
  and wait for a decision, the way this project has handled it before.
- **Report contract for every track**: end with exactly what changed (files touched), the gate
  commands you ran and their real output (not a summary — the actual pass/fail counts), and
  anything you could not do and why. This is what makes the review in §3 possible without the
  reviewer re-deriving your entire task from scratch.
