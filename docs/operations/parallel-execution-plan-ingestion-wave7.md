# ProcurePilot — Ingestion Wave 7 Execution Plan (E2E + Accessibility)

**Written**: 2026-09-17, following Wave 6's T030/T031/T033/T034 merge onto
`013-automated-ingestion` (commit `8d9a88e`) and Agy's live walkthrough of the same branch.

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 7, Tasks T035–T036 — the two tasks Wave
6 deliberately held back.

**Mode**: both were held until two conditions were met: (1) T030–T034 merged and the backend
suite green, and (2) a live walkthrough reported back so specs wouldn't lock in a bug as
"expected." Both conditions are now satisfied — T030/T031/T033/T034 are merged (T032 is Agy's
only remaining Wave 6 dispatch, running independently of this plan and not a blocker for E2E/a11y
work), and Agy's walkthrough (reported 2026-09-17) found two real bugs, both already fixed and
merged (`libmagic1` in the Dockerfile, the email-config 404-trap). This wave can start.

---

## 0. Grounding pass — the real conventions, not generic Playwright

Read before writing anything, and read the actual files, not just this summary:

- **`apps/web/playwright.config.ts`**: specs assume the stack is already running (`docker compose
  up` + `pnpm db:migrate` + `pnpm db:seed`) — a spec must never try to boot its own
  infrastructure. `baseURL` defaults to `http://localhost:4200`. System Chrome via `channel:
  'chrome'`, not Playwright's bundled browser.
- **`apps/web/tests/e2e/global-setup.ts`**: mints a platform invitation and drives the real
  sign-up flow to create the specs' shared owner — do not hand-seed a user into the database.
- **`apps/web/tests/e2e/support/api.ts`**: the real helper surface. `createMember(role =
  'buyer')` returns a `CreatedMember` (email/password/role) already signed up — this is how
  every existing flow spec gets a non-owner test user. `signInOwner()` returns a bearer token for
  API-level setup calls (seeding data via the real API, not direct DB inserts). Check this file
  for an existing capture/catalogue-import/email-log seeding helper before assuming one doesn't
  exist; if genuinely missing, a new helper here (calling the real
  `POST /api/v1/tenants/email-config`, `/capture`, `/suppliers/{id}/catalogue-import` endpoints)
  is the right pattern — do not seed ingestion tables directly via SQL from a spec file, every
  existing spec seeds through the real API.
- **`apps/web/tests/e2e/smart-compare.spec.ts`** (flow spec) and
  **`apps/web/tests/e2e/smart-compare-a11y.spec.ts`** (a11y spec): the two templates to copy.
  Sign-in is always `page.goto('/auth/sign-in')` +
  `page.fill('input[formControlName="email"]', ...)` + password + submit + `waitForURL('**/home')`
  — do not invent a different sign-in flow. Locale switch is `page.click('.account-btn')` +
  `page.click('button:has-text("العربية")')`.
- **Selectors**: only `email-config.component.html` has `data-testid` attributes (`domain-input`,
  `add-domain-btn`, `toggle-enabled`, `status-badge`, `forwarding-address`,
  `setup-email-config-btn`, `unconfigured-card`, plus a few stat ones) — the other four ingestion
  components (dashboard, email-log, capture, catalogue-import) have none. This matches this
  codebase's own E2E convention generally (`smart-compare.spec.ts` targets `.page-title`,
  `.quantity-input`, `.empty-state-card` — CSS classes, not testids, are the norm here) — do not
  treat the missing testids as a gap to fix; use the components' existing CSS classes (read each
  component's own `.html`/`.scss` for the real class names) or Playwright's role/text locators,
  matching how every other existing spec in this repo already works.
- **a11y tag convention**: `@a11y` in the test title, `pnpm test:a11y` runs
  `playwright test -- --grep @a11y`. `AxeBuilder` with `WCAG_21_AA = ['wcag2a', 'wcag2aa',
  'wcag21a', 'wcag21aa']`, `.exclude('.nav-item.disabled')` if a disabled nav item is in scope,
  assert `results.violations` is `[]` with a `describeViolations()`-style failure message (copy
  `smart-compare-a11y.spec.ts`'s own helper verbatim — don't reinvent it).

## 1. Non-negotiables

Unchanged. Specific to E2E/a11y: a spec must drive the real UI against the real backend, never
mock a response — that's what the Karma suite is for. An a11y scan with zero violations that
never actually ran (the exact failure mode `[[require-proof-of-execution-in-briefs]]` describes
for a prior chunk) is worse than no scan at all — the orchestrator re-runs every gate personally
before merging, same as every prior wave.

## 2. Task scope

### T035 — E2E: the four real ingestion flows

New file `apps/web/tests/e2e/ingestion.spec.ts` (or split per flow if that reads better — this
codebase has both single-file and split-per-feature precedent, pick one and be consistent).
Four flows per tasks.md, each as its own `test(...)`:

1. **Email config setup**: sign in as owner, navigate `/ingestion/email-config`. If the tenant is
   fresh (404/unconfigured state — see the just-merged fix), click through
   "Set Up Email Ingestion" first. Toggle enable/disable, confirm the status badge updates. Add a
   domain to the allowlist, confirm the chip renders and (reload) persists. This is the one flow
   with real `data-testid` hooks already in place — use them.
2. **Capture upload flow**: sign in as owner or buyer (role-gated route — confirm a viewer is
   redirected away, matching Agy's walkthrough finding that this already works, as a regression
   guard). Upload a real small PDF fixture (add one under `apps/web/tests/e2e/fixtures/` if none
   exists — check first) via the file input, submit, assert the success state and the resulting
   quotation link's `href` actually resolves to `/quotations/<uuid>`.
3. **Catalogue import flow**: sign in as owner/buyer, select a supplier (seed one via
   `createTestSupplier` from `support/api.ts` if that helper exists — check before assuming),
   confirm the file picker is disabled before selection, upload a real small CSV fixture,
   confirm the results summary (imported/skipped/error counts) matches the fixture's known
   content.
4. **Dashboard stats display**: sign in, navigate `/ingestion`, confirm the stat cards render
   (including a zero-activity tenant not crashing — a fresh `createMember` workspace has no
   ingestion activity yet, this is the natural zero-state case, no special seeding needed),
   confirm all four channel cards' links resolve to the right routes.

Do not re-test what Karma/Jasmine already proves (client-side validation messages, signal state
transitions) — E2E's job is proving the real integration (routing, real HTTP calls, real
persistence across a reload), not re-deriving unit-level correctness.

### T036 — a11y: all five ingestion surfaces

New file `apps/web/tests/e2e/ingestion-a11y.spec.ts`, modeled directly on
`smart-compare-a11y.spec.ts`. For each of the five components
(`/ingestion`, `/ingestion/email-config`, `/ingestion/email-log`, `/ingestion/capture`,
`/ingestion/catalogue-import`): one English scan, one Arabic/RTL scan, zero violations required
on both. That's 10 tests minimum; tasks.md also calls out two items needing their own explicit
tests beyond the plain axe-core sweep:

- **Keyboard navigation for file upload** (capture and catalogue-import specifically): a
  keyboard-only user must be able to Tab to the file input (or its trigger button/dropzone) and
  activate it, and separately Tab to and activate the "remove file" control once a file is
  selected. Axe-core's automated scan does not fully verify keyboard operability by itself
  (WCAG 2.1.1 is only partially automatable) — write an explicit test using
  `page.keyboard.press('Tab')` and `page.keyboard.press('Enter')`/`'Space'`, asserting focus
  actually lands on the right element and the action fires, not just that axe found no static
  violation.
- **RTL layout verification**: beyond the axe-core Arabic scan (which catches accessibility
  violations, not layout correctness), do a visual/structural check — no horizontal scroll
  (`document.body.scrollWidth` vs `window.innerWidth`, matching what Agy's manual walkthrough
  already did informally — make it a real, repeatable assertion here), and confirm at least one
  directional element (an icon that should mirror, e.g. a back-arrow) actually has RTL-appropriate
  styling applied (check for a `.rtl-flip`-style class or computed `transform`, matching whatever
  convention the components' own scss actually uses — read it, don't assume).

## 3. Delegation mechanics

Per the current fleet map ([[delegate-heavily-to-codex]] — check it fresh, don't trust this
snapshot): both tasks are UI-flavored E2E/a11y work, which fits Agy (the `ui` lane, effort high)
best — Agy already has full context on this exact feature from the live walkthrough it just ran,
and E2E/a11y specs are exactly the kind of "drive the real app and report faithfully" task Agy is
already proven at. OpenCode is not an option (removed from the fleet). Cursor's `mid` lane is a
plausible alternative if Agy is busy, but Agy is the default here.

T035 and T036 touch two different new files — genuinely parallel, two separate dispatches, not
sequential. Both need the live stack running (`docker compose up`, migrated + seeded) — confirm
it's actually up before dispatching (check `docker ps` for `procurepilot-api`/`procurepilot-web`;
it was still running as of Agy's walkthrough, may still be) rather than assuming, and tell each
session explicitly not to start its own stack (matching `playwright.config.ts`'s own stated
assumption).

## 4. Review protocol

1. Re-run both new spec files myself (`pnpm --filter web exec playwright test
   tests/e2e/ingestion.spec.ts tests/e2e/ingestion-a11y.spec.ts` — remember
   `[[e2e-filter-arg-quirk]]`: a bare `-- <spec>` silently runs the *entire* suite, not the
   filtered one) against the real stack before merging, not just reading a self-report.
2. Specifically re-run the a11y file alone and confirm it reports the SAME violation count (zero)
   independently — a hollow "ran but didn't really scan" pass is the exact failure mode
   `[[require-proof-of-execution-in-briefs]]` was written about.
3. Watch for `[[e2e-auth-rate-limit-flakiness]]`: repeated back-to-back full-suite runs during
   review can trip the 10/minute auth rate limit and look like a real bug — wait ~70s and re-run
   clean before concluding a regression.
4. If these specs run alongside the FULL existing e2e suite at any point, watch for
   `[[e2e-locale-persists-server-side-per-owner]]` — a shared owner across specs leaks a locale
   switch into a later English-expecting test; keep the Arabic/RTL tests last within each file or
   add an explicit `ensureEnglish()` reset, matching how this codebase's own prior specs already
   handle it.

## 5. What comes after

Phase 8 (T037–T042 — API spec, data dictionary, user docs, test-strategy doc, OpenAPI contract,
security review) is the feature's close-out, already partially scoped in
`parallel-execution-plan-ingestion-wave6.md` §5. T042 (security review) should still happen last,
after this wave lands — a security review of surfaces whose E2E/a11y coverage doesn't exist yet
would be reviewing an incomplete picture.

## 6. Cautions

- Don't let the capture/catalogue-import E2E tests leave real uploaded test files or created
  quotations lying around in a way that pollutes later spec runs sharing the same seeded owner —
  check whether other specs in this suite clean up after themselves (delete via API, or rely on
  per-`createMember` workspace isolation) and match that convention.
- The dashboard's zero-activity-tenant case is easy to seed by accident if T035 reuses a
  `createMember` workspace that some OTHER spec in this file already gave ingestion activity to
  within the same test run — use a fresh `createMember()` per test where the zero-state actually
  matters, don't assume isolation you haven't confirmed.
