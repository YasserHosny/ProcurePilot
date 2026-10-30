# GTM Execution Plan — First Customer (handoff + tracking)

Status: **active** · Created: 2026-10-14 · Source of truth for *content*:
[`first-customer-gtm-plan.md`](first-customer-gtm-plan.md). This file tracks *execution*: what is
set up, what is next, who does it, and what blocks what.

---

## 1. How to use this file (cold start, any model)

**Read first, in order:**

1. `CLAUDE.md` — project rules (8 non-negotiables, stack, commands). Binding.
2. `docs/gtm/first-customer-gtm-plan.md` — the plan: ICP, fit gaps, currency gaps C1–C5 /
   G1–G5 (with file:line refs), demo walkthrough, pilot prerequisites, pipeline stages.
3. This file — sections 2 (state), 3 (tasks), 4 (dependencies), 5 (handoff log).
4. Only if working on the pilot environment: `docs/operations/self-hosted-deployment-plan.md`
   (status: draft, not started).

**Then:** append a row to the handoff log (section 5) before you stop.

### Atlassian

| Item | Value |
|---|---|
| Site | `https://yasser-hosny.atlassian.net` |
| cloudId | `125b7789-fa8b-449d-b2de-ef10f5400fd4` |
| Products | Jira (free plan; since Atlassian merged Jira Software into Jira, it includes Scrum spaces with sprints, Epic and Bug), Jira Product Discovery, Confluence, Loom |
| Space `PPS` | ProcurePilot Delivery — company-managed Scrum space, board 1; all delivery work (GTM, ops, demo/pilot gaps) since 2026-10-24 |
| Space `PP` | ProcurePilot — retired 2026-10-24, empty; its 29 issues moved to `PPS` (old `PP-n` links redirect) |
| Space `SP` | Sales Pipeline — one Lead per prospect company |
| Space `MDP` | JPD sample data (MDP-1..6) — in the Jira trash; **ignore** |
| Members | Dr. Yasser Hosny (owner); Omar Medhat (mr.omarmedhat@gmail.com) invited 2026-10-14 — JPD "User (creator)", Goals/Projects/Studio user, not admin; free plan gives every member access to PPS and SP |

**Tool capabilities:**

| Tool | Can | Cannot |
|---|---|---|
| Atlassian MCP connector (Claude Code) | create / edit / transition / comment issues, JQL search, Confluence pages | create spaces, rename statuses, add/edit custom fields, reorder board columns |
| Browser (Claude in Chrome, user's signed-in session) | space/field/workflow/board admin | — (still: no deletes, no sends without user OK) |
| Non-Claude models (Codex, agy, OpenCode) | code + docs in the repo | no Atlassian access assumed — leave Jira steps for an orchestrator with the connector, or the user |

### Workflow split (decided, user-approved 2026-10-14)

- **Code** → Speckit (`spec.md` → `plan.md` → `tasks.md`) → delegation lanes → PR → CI → merge.
  Never duplicated into Jira.
- **GTM / ops** → Jira `PPS`. Done = sent / published / held / signed (not "drafted").
  Drafting (scripts, one-pager copy, agreements) can be done directly by the orchestrator — no
  code lane needed.
- **Bridge (one-way)**: demo/pilot gap → `PPS` task labelled `from-demo` / `from-pilot` → if it
  needs code, a Speckit spec → the `PPS` task links to the PR.
- **Sales conversations** → `SP` only, never `PPS`.

### Repo / delegation rules that bite (from user memory; details in `CLAUDE.md` + memory)

- Orchestrator dispatches and reviews; implementation goes through lanes (Codex / agy / OpenCode
  fallback). **Tenancy work (RLS, tenancy migrations, JWT path) stays in-house.**
- **Commit a checkpoint before any Codex dispatch** (Codex once wiped a clone). Run Codex with
  `< /dev/null`, in the foreground.
- **agy needs a real `git clone`** under `~/agy-clones/`, not `git worktree add`; the user has a standing
  approval for `--dangerously-skip-permissions` on Agy dispatches (AGENTS.md requires explicit
  approval — this is it; keep the task/file scope narrow and rerun the gates before merging); clear a bloated `.angular` cache first.
- Check `df -h /` before dispatch (root disk nearly full).
- Concurrent agents share this checkout — use isolation or wait; don't run git while another
  agent is working.
- Proof of execution required: a task is not done until its tests/commands were actually run.
- Drive the real UI end-to-end after a change, not just unit tests.
- Hosted (`procurepilot.iron-sys.com`) is the **test/staging** DB — fine for demos, **not** for
  real customer data.

---

## 2. Current state (snapshot 2026-10-14)

> Snapshot of the Jira and plan setup on 2026-10-14. Product status since then lives in §3 (P rows), `docs/roadmap/procurepilot_roadmap.md` Delivery Status and `docs/gtm/demo-tenant/README.md`.

### GTM plan file

| Item | State |
|---|---|
| `docs/gtm/first-customer-gtm-plan.md` | Revised and approved 2026-10-14; committed with this file (G-0). Other untracked files under `docs/` are unrelated — don't sweep them into commits. |

### Space `PP` — ProcurePilot (retired 2026-10-24, see `PPS`)

| Setting | Value | State |
|---|---|---|
| Template | Task tracking (team-managed, business) | Done |
| Work types | Task, Sub-task | Done |
| Labels in use | `from-demo` (product gaps), `gtm`, `ops`; `from-pilot` reserved | In use |
| Issues | 13 tasks created 2026-10-14 (J-5) — mapping below | Done |

**Plan ID → Jira key** (summaries are prefixed with the plan ID, e.g. `[G-2] …`). Keys are `PPS`
since the 2026-10-24 move; the old `PP` key is in brackets.

| Plan ID | Key | Plan ID | Key | Plan ID | Key |
|---|---|---|---|---|---|
| P-1 (C1) | PPS-9 (PP-1) | G-1 | PPS-24 (PP-5) | G-7 | PPS-20 (PP-11) |
| P-2 (C3) | PPS-5 (PP-2) | G-2 | PPS-26 (PP-6) | G-8 | PPS-21 (PP-12) |
| P-3 (C2) | PPS-6 (PP-3) | G-3 | PPS-16 (PP-7) | G-9 | PPS-19 (PP-13) |
| P-4 | PPS-12 (PP-14) | G-4 | PPS-18 (PP-8) | G-10 | PPS-11 (PP-17) |
| P-5 | PPS-13 (PP-15) | G-5 | PPS-14 (PP-9) | G-11 | PPS-4 (PP-19) |
| P-6 | PPS-10 (PP-16) | G-6 | PPS-15 (PP-10) | G-12 | PPS-1 (PP-20) |
| P-7 | PPS-3 (PP-18) | E-1 | PPS-29 (PP-4) | | |
| P-8 | PPS-25 (PP-28) | P-9 | PPS-17 (PP-29) | J-7 | PPS-30 |
| P-10 | PPS-32 | P-11 | PPS-33 | P-12 | PPS-34 |
| P-13 | PPS-38 | P-14 | PPS-35 | P-15 | PPS-36 |
| P-16 | PPS-37 | P-17 | PPS-40 | P-18 | PPS-42 |
| P-19 | PPS-44 | P-21 | PPS-46 | P-22 | PPS-47 |
| P-20 | PPS-45 | P-23 | PPS-49 | P-24 | PPS-50 |
| P-25 | PPS-51 | G-13 | PPS-39 | | |
| P-26 | PPS-53 | | | | |
| P-27 | PPS-55 | P-28 | PPS-56 | P-29 | PPS-58 |
| P-30 | PPS-59 | P-31 | PPS-61 | P-32 | PPS-62 |
| P-33 | PPS-63 | P-34 | PPS-64 | P-35 | PPS-65 |
| P-36 | PPS-66 | P-37 | PPS-67 | P-38 | PPS-68 |
| P-39 | PPS-69 | P-40 | PPS-70 | P-41 | PPS-71 |
| P-42 | PPS-72 | P-43 | PPS-73 | P-44 | PPS-74 |
| P-45 | PPS-75 | P-46 | PPS-76 | | |
| P-49 | PPS-79 | | | | |
| P-52 | PPS-82 | P-53 | PPS-83 | P-54 | PPS-84 |
| P-57 | PPS-87 | P-58 | PPS-88 | P-59 | PPS-89 |
| P-60 | PPS-90 | P-61 | PPS-91 | P-62 | PPS-92 |
| P-63 | PPS-93 | P-64 | PPS-94 | P-65 | PPS-95 |
| P-66 | PPS-96 | P-67 | PPS-97 | P-68 | PPS-98 |
| P-69 | PPS-99 | P-70 | PPS-100 | P-71 | PPS-101 |
| P-72 | PPS-102 | P-73 | PPS-103 | P-74 | PPS-104 |
| P-75 | PPS-105 | P-76 | PPS-106 | P-77 | PPS-107 |
| P-78 | PPS-108 | P-79 | PPS-109 | P-80 | PPS-110 |
| P-81 | PPS-112 | P-82 | PPS-113 | P-83 | PPS-114 |
| P-84 | PPS-115 | P-85 | PPS-116 | P-86 | PPS-117 |
| P-87 | PPS-118 | P-88 | PPS-119 | P-89 | PPS-120 |
| P-90 | PPS-121 | P-91 | PPS-122 | P-92 | PPS-123 |
| P-93 | PPS-124 | P-94 | PPS-125 | P-95 | PPS-126 |
| P-96 | PPS-127 | P-97 | PPS-128 | P-98 | PPS-129 |
| P-102 | PPS-133 | | | | |

Without a plan ID: PPS-2 (PP-21), PPS-7 (PP-22), PPS-8 (PP-23), PPS-22 (PP-24), PPS-27 (PP-25),
PPS-28 (PP-26), PPS-23 (PP-27) — architecture diagrams and two shipped code changes, all Done.

PP-14..PP-18 were added 2026-10-22 to track work done since 2026-10-15 that had no Jira task. PP-19 (G-11, company website on iron-sys.com, `docs/gtm/website/`) was added the same day. PP-20 (G-12, WhatsApp pilot-invite cards + video, `docs/gtm/whatsapp-card/`) was added the same day.

**Progress convention:** status is the board column — To Do → In Progress → In Review → Done
(the `in-progress` label is retired). Work runs in two-week sprints, Sunday to the second
Thursday. Each update is a dated **Progress** comment saying what is done and what is left.
Dependencies are Jira *Blocks* links matching §4.

D-1..D-3 (user decisions), J-* (setup) and G-0 (commit) are tracked in this file only.

### Space `SP` — Sales Pipeline

| Setting | Value | State |
|---|---|---|
| Template | Sales pipeline (team-managed) | Done |
| Work types | Lead (id `10006`), Customer (id `10005`) — one shared workflow | Done |
| Statuses | Target (new) → Contacted, Talked, Qualified, Pilot offered (in progress) → Pilot, Not now (done); every status reachable from any status | Done, verified via connector |
| Board column order | "Pilot offered" may have been appended at the end | **Verify** (J-3) |
| Template fields on Lead | Company size, Website, Email, Phone number, Start date, Category, Team | Done |
| Custom field: Contact (short text) | `customfield_10074` | Done |
| Custom field: Role (short text) | `customfield_10073` | Done |
| Custom field: City (short text) | `customfield_10072` | Done |
| Custom field: Branches (number) | `customfield_10071` | Done |
| Custom field: Source (dropdown: Personal network / Community / LinkedIn / In person) | `customfield_10070` | Done |
| Transition IDs (any → status) | Target `21` · Contacted `31` · Talked `41` · Qualified `51` · Pilot offered `2` · Pilot `61` · Not now `71` | Verified |
| Conventions | Due date = next-step date · one comment per touch · one Lead per company | Agreed |
| End-to-end test | SP-1 `[TEST] Example Bakery Co.` — create with all 5 custom fields, comment, → Talked, overdue JQL, Talked+ count JQL all passed; parked at Not now | Done — **SP-1 awaits deletion by the user** |

Connector field names work directly: `createJiraIssue` with `additional_fields: {"Contact": ..., "Role": ..., "City": ..., "Branches": 6, "Source": "LinkedIn", "duedate": "YYYY-MM-DD"}`.

---

## 3. Task list

Owner types: **User** (only the user can do it) · **Orch** (orchestrator model with repo +
Atlassian connector) · **Lane** (code lane via Speckit: Codex / agy / OpenCode) · **Browser**
(Claude in Chrome on the user's session).

### D — Decisions (user only)

- [x] **D-1 Pilot environment** — **decided 2026-10-14: Option B, separate paid hosted
  production** (own Supabase project + containers, isolated from staging). Self-hosting stays a
  later option. Recorded on PPS-29; confirm plan tier with the user before creating anything
  billable.
- [x] **D-2 Post-pilot price** — **confirmed by user 2026-10-14**:
  EGP 1,500 per branch per month (minimum 2 branches), annual = 10 months' price; founding-customer
  50% off for the first 12 months in exchange for case study + logo; savings guarantee — if
  verified savings in a month are below 3× the fee, the next month is free. Revisit after the
  first pilot's real savings data. Blocks: G-6 (PPS-15).
- [x] **D-3 Add Jira's free software plan?** — **decided 2026-10-24: yes, as a Scrum space.** No
  product to add (Jira already includes Scrum); `PPS` created and PP's issues moved there.

### J — Jira setup

| ID | Task | Owner | Depends on | Done when | Space |
|---|---|---|---|---|---|
| [x] J-1 | Verify Contact, Role, City are saved on Lead; add Branches (number) and Source (dropdown, 4 options); click "Save changes" | Browser | — | All 5 fields visible on a new Lead's create screen | SP |
| [ ] J-2 | Confirm the template fields (Company size, Website, Email, Phone number, Start date, Category, Team) are still present; hide any unused from the create screen only if the user wants | Browser | J-1 | Create screen reviewed | SP |
| [ ] J-3 | Verify board column order is Target, Contacted, Talked, Qualified, Pilot offered, Pilot, Not now; reorder if "Pilot offered" is last | Browser | — | Board columns in stage order | SP |
| [x] J-4 | End-to-end test via connector: create dummy Lead → transition to Talked → add comment → set due date → run JQL `project = SP AND duedate <= now() AND status != "Not now"` and confirm it returns the dummy. **Passed 2026-10-14 (SP-1).** SP-1 deleted by the user 2026-10-14 | User | J-1 | SP-1 deleted | SP |
| [x] J-5 | Create PP tasks G-1..G-9, P-1..P-3 (as `from-demo`), E-1 below; put the task ID from this file in each summary (e.g. `[G-2] Demo video`) | Orch | G-0 | Issues exist; keys written back into this file's tables | PP |
| [ ] J-6 | Save the "weekly review" JQL as a filter (needs browser if connector can't save filters) | Browser | J-4 | Filter "SP — due or overdue" exists | SP |
| [ ] J-7 | Move delivery tracking to the `PPS` Scrum space (board 1): issues moved from PP, Story Points on the default screen, two-week sprints from 2026-10-26 | Orch + Browser | D-3 | Docs PR merged; PPS Sprint 1 active (PPS-30) | PPS |

### G — GTM assets (non-code, Jira PPS)

| ID | Task | Owner | Depends on | Done when | Space |
|---|---|---|---|---|---|
| [x] G-0 | Commit `first-customer-gtm-plan.md` after user approval (that file only) | Orch | user approval | Commit on `main` (or PR) containing only that file | — (git) |
| [ ] G-1 | Demo tenant on hosted: dedicated tenant, Arabic supplier names, ~30-item F&B catalogue, 2–3 branches, EGP prices, one RFQ ready to send; no test leftovers | Orch + User | P-1 (forms default to EGP) | Tenant walkthrough runs clean end-to-end | PPS |
| [ ] G-2 | 3-min demo video + 60-s vertical cut: Arabic UI, Arabic on-screen text + music (no voice-over), recorded with OBS; spec, storyboard and finished logo sting/end card in `docs/gtm/video/`. Script must follow the corrected walkthrough (human sends RFQ; guardrail on → draft purchase request; mobile approves the *request*; PO generated on web) | User (record), Orch (script) | G-1, P-1, P-2 | Video link stored on the PPS task | PPS |
| [ ] G-3 | Pitch line (Arabic + English) finalised | Orch draft, User approve | — | Approved text on the PPS task | PPS |
| [ ] G-4 | One-pager (Arabic + English): before (WhatsApp + Excel) vs. after (RFQ → compare → approve → PO) | Orch copy, User design | G-3 | Published PDF/link | PPS |
| [ ] G-5 | Outreach DM script (Arabic + English), diagnostic-question first | Orch draft, User approve | G-3 | Approved script on PPS task | PPS |
| [ ] G-6 | Pilot agreement (1 page, Arabic + English) + week-0 baseline template: duration, success metric + baseline, day-14 terms, data ownership, supplier-price confidentiality, export/deletion on exit, Egypt PDPL (Law 151/2020) clause, C4/C5 workarounds (EGP-only suppliers, ex-VAT) | Orch draft, User approve (legal review advisable) | D-2 | Signed-ready PDF; baseline template (10–20 items, unit price, quote turnaround) | PPS |
| [ ] G-7 | Community + target list: personal network audit, Egyptian founder/SME communities, LinkedIn search; each prospect → an SP Lead at Target | User (list), Orch (create Leads) | J-1, J-4 | ≥20 Leads in SP | SP |
| [ ] G-8 | Pilot onboarding runbook: CSV/manual supplier + catalogue load, branches/approvers, inbound-email address for WhatsApp-forwarded quotes, first live RFQ, support WhatsApp group (4 working-hour response) | Orch | E-1, P-1, P-3 | Runbook doc linked on PPS task, dry-run on demo tenant | PPS |
| [ ] G-9 | Outreach: work SP to 20 conversations at Talked+ | User | G-2, G-5, G-7 | 20 Leads at Talked or beyond | SP |
| [ ] G-10 | Company formation: Egyptian one-person company on the simplified regime (research in `docs/gtm/company-formation/`) | User | — | Company registered; name + tax ID on PPS-11, then into G-6 | PPS |

### P — Product tasks (PPS `from-demo` → Speckit spec → code lane)

Each: create PPS task labelled `from-demo` → write Speckit spec/plan/tasks → dispatch to a lane →
PR → CI → merge → link PR on the PPS task. Refs are in the GTM plan's currency-gap tables.

| ID | Gap | Task | Owner | Depends on | Done when |
|---|---|---|---|---|---|
| [x] P-1 | **C1** | Wire the **existing** `tenant.currency` (required at sign-up, returned by `/me`, already used by budget/threshold forms) into the forms that still default to USD: PO create, guardrails, quotation review fallbacks. No new setting, no schema/RLS change | Orch (spec + tenancy part), Lane (forms) | — | Merged; demo tenant set to EGP and every form opens in EGP — **done: 022 (#73), PPS-9 Done** |
| [ ] P-2 | **C3** | Locale-aware money formatting on mobile (grouping, currency minor units, ar/en) for approval queue + request detail | Lane | — | Merged; `flutter test` green; screenshots show `EGP 12,500.00` (and Arabic locale equivalent) — **code merged in 022 (#73, #124); stays open until the screenshots (022 T018) exist** |
| [ ] P-3 | **C2** | Test extraction with 5 real Egyptian quotes (incl. Arabic-Indic digits, ج.م / جنيه / LE); recognise Egyptian markers; replace the GBP fallback with **human review** for unresolved currency — never a tenant-currency default (also Azure DI £/$/€-only + hard-coded USD path; landed-cost GBP default) | Orch (test), Lane (fix) | — | Test results recorded on PPS task; fix merged; q1–q3 extract as EGP; q4–q5 land flagged for review with no guessed currency — **fix merged in 022 (#73); the real-quote run is 022 T015, still open** |

| [ ] P-4 | — | One combined jobs container for the background workers hosted lacks (report schedules, offer refresh, exports, digests, webhooks, accounting/POS sync); deploy workflow modelled on #108 | Lane, User (container) | demo video recorded | Deployed; overdue schedules run on hosted (PPS-12) |
| [ ] P-5 | finding 20 | Real product-matching embeddings on hosted (stub scores exact names 55%) — switch on the Bedrock provider (#62) or decide to keep the stub | User (cost OK), Orch | — | Decision on PPS-13; if on, exact names score above auto-accept |
| [ ] P-6 | finding 50 | Hidden/idle web tab signs out after a few hours; visible tab renews fine | Orch → Lane | — | Hidden tab survives several expiries, or cause fixed (PPS-10) |
| [x] P-7 | findings 1–49 | Demo-tenant fix wave record (PRs per finding) | — | — | PPS-3 Done |
| [x] P-8 | email audit | Password reset broken on hosted: Site URL was localhost, no set-password page, no custom SMTP (2 emails/hour) | Orch (config + code), User (SMTP credentials) | — | Live reset on hosted: email arrives, link opens `/auth/update-password`, new password signs in — **done 2026-10-24: #227, #228, #229, Mailgun SMTP; PPS-25 Done** |
| [x] P-9 | — | Upgrade the web app to Angular 22 + Material 22 (TypeScript 6.0, ngx-translate 18, Sentry 11, `@angular/build`, Node 24 in CI/Docker) so the new design system is built on the current Material API | Orch | — | PR merged with every required check green on its head commit (PPS-17) — **done 2026-10-24: #230 (6ef2c0e); PPS-17 Done** |
| [x] P-10 | — | Design system for the web app: Ledger look on the Converge brand, three-layer tokens, aligned with Angular Material 22 (`docs/design/`); app implementation follows after P-9 | Orch | P-9 (to implement) | Docs PR merged (PPS-32) — **done 2026-10-24: #234 (4a741ba); PPS-32 Done** |
| [x] P-11 | — | Build the design system into `apps/web`: tokens, Material 22 theme, Readex Pro + Noto Kufi figures, Material Symbols, Converge logo, hard-coded colours mapped to tokens | Orch → Agy | P-9, P-10 | PR #235 merged with every required check green, user-doc screenshots regenerated (PPS-33) — **done 2026-10-24: #235 (5d34a0f), contrast fix and 36 screenshots included; PPS-33 Done** |
| [x] P-12 | — | Flaky `mat-select` E2E since Angular 22: Material 22's 100 ms panel fade still takes clicks, so re-opening a select right after a pick hits the old panel; E2E runs with reduced motion | Orch → Agy | P-9 | Fix merged, main CI green on its head (PPS-34) — **done 2026-10-24: #237 (d4414e7), main CI green; PPS-34 Done** |
| [ ] P-13 | — | Alerts page took ~48 s on hosted: every alert check opened its own DB connection per product and per supplier (182 per request). One connection per request, price history fetched once per product | Orch | — | Merged and deployed; `/alerts` measured on hosted (PPS-38) |
| [x] P-14 | — | Guest landing page at `/` (Ledger design): hero, how it works, Sign in, Request pilot access (mailto; sign-up stays invitation-gated), EN / عربي toggle on the landing and sign-in pages, hidden gallery slot; signed-in users still go to `/home` | Orch → Agy | P-11 | PR merged with every required check green on its head commit; driven in a browser in en + ar (PPS-35) — **done 2026-10-24: #240** |
| [x] P-15 | — | Rich landing page from the owner-reviewed content (Codex + Agy review): audience-led hero, buyer fit, 4-step workflow, 5-tab en/ar product gallery (MatDialog), evidence section, "Built by Iron Systems" band + iron-sys.com links, pilot invitation with pre-filled email and Q&A. Gallery images captured from the hosted app with one reserved synthetic tenant (`landing-gallery-demo`), never local Supabase | Orch → Agy (UI) + Codex (captures) | P-14 | PR merged with every required check green on its head commit (PPS-36) — **done 2026-10-24: #242** |
| [x] P-16 | — | Design-system follow-ups: emails wrap without splitting words (`overflow-wrap: anywhere`), unused `material-icons` removed. Component style-budget warnings left as they are (owner decision 2026-10-24) | Orch → Agy | P-11 | **done 2026-10-24: #241 (d2d3409); PPS-37 Done** |
| [x] P-17 | — | Ledger design system on the Flutter mobile app (theme from the web's palette tones, Readex Pro + Noto Kufi figures, Converge logo, launcher/web icons); fixes the blank mobile web build (i18n assets outside `build/web`) | Orch → Agy | P-11 | **done 2026-10-24: #245 (b129298); PPS-40 Done** |
| [x] P-18 | — | Web sidebar grouped by job (Sourcing, Purchasing, Catalogue, Insight, Setup), collapsible, active group always open; user guide and screenshot updated | Orch → Agy | P-11 | **done 2026-10-24: #246 (e683d92), #249 (393fb84); PPS-42 Done** |
| [ ] P-19 | — | Savings Ledger labelled every delta "Verified Saving", Pending rows included. Column is now "Saving (Delta)"; a pending delta is outlined with "Calculated, not yet verified" under it; user docs §16 updated | Orch | — | PR merged with every required check green on its head commit (PPS-44) |
| [ ] P-21 | — | Docs screenshot capture showed duplicated sample rows after a CI retry: the serial spec re-seeds its data on retry, which pushed 3 screenshots over the 1% limit (#241). The docs config now never retries, CI sample names drop the timestamp whose digit widths reflowed 10-smart-compare, and the canonical save step checks the typed total and the saved response, so the rare stuck mismatch banner (3 of ~40 runs) reports its cause | Orch | — | PR merged; two consecutive docs-screenshot runs pass the diff with no retry (PPS-46) |
| [ ] P-22 | — | CI: the five deploy workflows shared one BuildKit cache scope with `mode=max`, filling 10.4 GB of the 10 GB Actions cache and evicting pnpm/uv caches; each image now has its own scope (`mode=min` for single-stage, `max` for web). E2E sharded five ways instead of three (predicted ~199 s of specs per shard, was ~330 s) | Orch | — | PR merged with every required check green on its head commit; measured shard times recorded in `docs/operations/ci-pipeline.md` (PPS-47) |
| [ ] P-20 | — | Landing page v2 from an impeccable critique (26/40) and a copywriting pass: provenance-led hero with a 2x recommendation crop, merged "how it works", native scroll-snap screenshot rail (peek, prev/next, step index, keyboard, RTL, lightbox), navy evidence band with a ledger excerpt (double rule on the verified line), navy pilot panel with copy-email and FAQs beside it, Iron Systems byline; page split into gallery/evidence/pilot components | Orch → Agy (UI) + Codex (captures, polish) | P-15 | PR merged with every required check green on its head commit; checked in en, ar and at 375 px (PPS-45) |
| [ ] P-23 | — | Mobile user guide: the Google Stitch concept mockups (2026-09-11, pre-ship) replaced by real renders of the shipped app from a tagged Flutter capture test (17 screens, EN + AR sign-in/home); Approvals, Delivery and Quality Issue get images; Settings keeps its preview mockup | Orch → Agy | P-17 | PR merged; guide shows real screenshots (PPS-49) |
| [x] P-24 | — | Smart Compare showed quote-derived offers as open-ended: `landed_cost.valid_to` was never written. It now carries the quotation's expiry (end of that day in the tenant's reporting timezone); a lapsed quote reads as expired. Existing rows are append-only and stay open-ended | Orch | — | **done 2026-10-24: #255 (f9961f4), verified on hosted with a new quote (`docs/gtm/demo-tenant/pps50-quote-expiry/`, #259); PPS-50 Done** |
| [x] P-25 | — | Mobile request detail showed the approver as a raw member ID and the decision time as an ISO timestamp (found by P-23). The approval step now carries `assigned_email` (looked up through the caller's RLS client, like `requester_email`; `assigned_name` reserved), mobile shows name → email → "Unknown approver", and `decided_at` is a local date in en/ar via a shared intl `formatDateTime` | Orch → Codex (API) + Agy (mobile) | P-23 | **done 2026-10-25: #256 (76893ae); PPS-51 Done** |
| [x] P-26 | — | Mobile showed required-by dates as raw `YYYY-MM-DD` (Western digits in Arabic) on request list, request detail, approval queue, approval decision and delivery screens; the mobile counterpart of PPS-48 (web, other session). A date-only `formatDate` beside `formatDateTime` parses the calendar date without a timezone shift; the request form input keeps `YYYY-MM-DD` | Orch → Agy | P-25 | **done 2026-10-25: #260 (bdf65b8); PPS-53 Done** |
| [ ] P-27 | — | Found by the P-24 hosted check: an offer's expiry ends at midnight in the workspace's `reporting_timezone`, which sign-up leaves on UTC, while the web formats dates in the browser's timezone. A UTC workspace viewed from Cairo shows a 03/11 quote as valid until Nov 4 and keeps it valid 2 h too long. Default the timezone from the region at sign-up and/or show the expiry in the workspace timezone; coordinate with PPS-54 (`formatDate`) | Orch | P-24 | an EG sign-up gets Africa/Cairo (or the date reads Nov 3 in any timezone), with a test (PPS-55) |
| [ ] P-28 | — | Found by the P-24 hosted check: bulk confirm reads "1 matches confirmed." — `matching.queue.exact.*` counted strings have no plural forms (en, and ar's full plural set) | Orch | — | a count of 1 reads "1 match confirmed.", Arabic counts correct, with a component test (PPS-56) |
| [x] P-29 | — | Arabic UI said «وفر» / «وفورات» for a saving; Egyptian buyers say «توفير» / «توفيرات» (owner, 2026-10-25). 56 `ar.json` values and four Arabic E2E assertions; other roots («متوفر», «يوفر», «أوفر») untouched | Orch → Codex | — | **done 2026-10-25: #263 merged, CI green; PPS-58 Done** |
| [x] P-30 | — | Demo video v2.4 jumped from the pain to the result without saying the product answers it. Script revised: product bridge in beat 1, a pain card before each chapter's fix, an honest promise, caption fixes, beat 9 dropped; script moved to `video/cuts/v2.4-ledger/script.md` | Orch, User (approval) | — | **done 2026-10-25: script #264, v2.4.1 cuts #274 (`video/cuts/v2.4.1-ledger/`); PPS-59 Done** |
| [x] P-31 | — | Material's `savings` glyph is a piggy bank (owner, 2026-10-25). Money-saved icons now `payments` (banknotes; was `toll`, owner chose 2026-10-25), empty budget list `account_balance_wallet`; 8 uses in 7 web files. The home regional settings card, which also used `payments`, now uses `public` (globe) | Orch | — | **done 2026-10-25: #271 merged; icon switched to `payments` in #275; home settings card to `public` in #276; PPS-61 Done** |
| [ ] P-32 | — | Landing gallery was a sideways snap rail, so most visitors saw only screen 01 (owner, 2026-10-25). Four options mocked up; owner chose guided steps: a numbered steps list beside one framed screenshot, ARIA tabs, chip row on phones | Orch → Agy | — | merged with required checks green, EN/AR before/after on the PR (PPS-62) |
| [ ] P-33 | — | The Arabic v2.4.1 cuts still showed «وفورات» / «الوفر» in three shots recorded before #263 (owner, 2026-10-25). Re-shot on hosted, no pixel patching: the record-outcome form (PO-000008, nothing saved), the ledger after recording and the verified ledger, as hosted shows them now (١٬٧٦٠ ج.م verified). Privacy audit re-run; cuts in `docs/gtm/video/cuts/v2.4.2-ledger/`. | Orch | — | Arabic cuts show no «وفر» / «وفورات», numbers match hosted, re-published (PPS-63) |
| [ ] P-34 | — | A fully English demo for the Saudi market (owner, 2026-10-25): workspace Rawaq Restaurant Group with English branches, products, suppliers, quotes, WhatsApp photo and UI, recorded on hosted in a dry round and a recorded round (SAR 310 saved). Cut built by `video/source/edit-sa-en/`; the end card uses the Egyptian contact number for now (owner) | Orch | G-13 | cuts in `docs/gtm/video/cuts/gcc-sa-en-v1/`, privacy audit clean, round record in `gcc/rounds/README.md` (PPS-64) |
| [ ] P-35 | — | The same English demo for a eurozone market, Ireland (owner, 2026-10-25): workspace Liffey Kitchen Group, EUR, Irish VAT (IE region and euro extraction #285, Subtotal row #286/#287), €53.50 saved in the recorded round. Cut built by `video/source/edit-ie/` with three owner-approved Irish captions (beat 8 drops VAT: Irish quotes are ex-VAT) | Orch | P-34 | cuts in `docs/gtm/video/cuts/eu-en-v1/`, privacy audit clean, round record in `gcc/rounds/README.md` (PPS-65) |
| [ ] P-36 | — | Found by the English rounds: euro amounts drop a trailing zero ("EUR 1,289.5") on the purchase request, and a zero saving shows as red "-SAR 0.00" on the ledger | Orch | — | both display as "EUR 1,289.50" and "SAR 0.00", with tests (PPS-66) |
| [x] P-37 | — | Owner asked for the `find-skills` agent skill (vercel-labs/skills). Added unchanged at `.claude/skills/find-skills/SKILL.md`, so every Claude Code session on the repo has it (cloud containers are wiped when a session ends) | Orch | — | **done 2026-10-25: #288 (b80157a); PPS-67 Done** |
| [ ] P-38 | — | Docs screenshot drift failed #291 on 28-email-ingestion-log alone (2.23%): the seeded email rows were dated `now()`, so the Received At column showed the capture day and the image changed daily. The spec now anchors them at noon UTC today, so the dashboard's today/week/month counts stay 5 at any hour, then moves them to a fixed day (2026-10-26, the day #292's committed image shows) before capturing 28 | Orch | — | PR merged; two consecutive docs-screenshot runs pass the diff (PPS-68) |
| [ ] P-39 | — | Docs screenshot 17-approval-queue sat at 0.92–0.94% drift, just under the 1% limit: its Requester column shows the E2E owner's email, which carried a new `Date.now()` each run (as did the workspace name on 02 and the buyer's email on 18). A docs capture under CI now signs up as `e2e.owner@example.test` / `E2E Test Co` with a fixed buyer address; the docs job uploads its images after every complete capture | Orch | — | PR merged; two consecutive docs-screenshot runs show 17 well under the limit (PPS-69) |
| [ ] P-40 | — | Found in docs screenshot 17 (P-39): on the web approval queue, Approve/Reject render under the Lines column and the Actions column is empty. Likely `display: flex` on the `.lines-cell` / `.actions-cell` `<td>`s takes them out of table layout | Orch → Agy | — | buttons under Actions in EN and AR, with a test and zero axe violations; 17 re-committed from CI (PPS-70) |
| [ ] P-41 | — | The outro's closing "A product of Iron Systems" line was small and said nothing about the company (owner, 2026-10-26). End card v2 replaces it with an Iron Systems band: logo, www.iron-sys.com and hello@iron-sys.com, as a footer strip in 16:9 and a safe-area panel in 9:16, Arabic and English; timing and audio unchanged. Latest cuts only (v2.4.2, gcc-sa-v1 Arabic, gcc-sa-en-v1, eu-en-v1), bodies and audio byte-identical; source `video/source/endcard-v2/` | Orch | — | latest cuts end on the v2 card, merged (PPS-71) |
| [ ] P-42 | — | Landing pilot enquiries went to support@ (existing customers per iron-sys.com); now `salesEmail` hello@iron-sys.com, support@ kept in the app (owner, 2026-10-26) | Orch → Agy | — | merged (PPS-72) |
| [ ] P-43 | — | No privacy policy or terms existed. Public /privacy and /terms (en + ar) naming Iron Systems as provider, the processors actually used, AI use, retention, rights; linked from landing footer and sign-up. Owner to confirm entity name, governing law (Egypt), 90-day deletion and liability cap before pilots rely on it | Orch (copy) → Agy | — | merged; owner confirms the four items (PPS-73) |
| [ ] P-44 | — | Mobile had no company or support info: Help & about screen (support@, privacy, terms, by Iron Systems, version); new deps url_launcher, package_info_plus | Orch → Agy | P-43 | merged (PPS-74) |
| [ ] P-45 | — | Web account menu: Privacy, Terms and "ProcurePilot by Iron Systems" as keyboard-reachable menu items | Orch → Agy | P-43 | merged (PPS-75) |
| [ ] P-46 | — | "Sent with ProcurePilot by Iron Systems · www.iron-sys.com" footer on invitation, auto-prepared request and digest emails; RFQ emails to suppliers unchanged | Orch → Codex | — | merged (PPS-76) |
| [ ] P-49 | — | Web unit test `DirectionService (T064)` "switch to rtl" failed once on #299 (no web code). CDK's root `Directionality` reads `dir` from `<body>`/`<html>` when it is constructed; a spec that ran earlier left the page RTL, so `setDirection('rtl')` changed nothing and emitted nothing. The spec now clears `dir`/`lang` before and after each test | Orch | — | PR merged; full web suite green 3 runs in a row (PPS-79) |
| [ ] P-52 | — | Docs screenshots check (`docs-screenshots.yml`) failed on every frontend PR since #297: its Terms/Privacy notice under the sign-up button made 01c 7px taller (1440×900 → 1440×907). 01c re-committed from CI; user docs mention the notice on Create workspace and Accept invitation | Orch | — | docs-screenshots run green on the PR (PPS-82) |
| [ ] P-53 | — | Demo video v2.5 in every version (owner-approved 2026-10-27): 10-s problem chapter with each market's own quotes, a logo-build brand turn, beat 1 on the fix caption, full-page saving, pain-to-fix recap, no disclosure pill, music crossfade into the outro. 12 cuts (Egypt ar/en, Saudi ar/en, Rawaq English, Liffey × 16:9/9:16); one build for every market (`docs/gtm/video/source/edit-v2.5/`) | Orch | P-41 | PR open (PPS-83) |
| [ ] P-54 | — | Arabic UI showed money as «EGP ٣٠٠» (owner, 2026-10-27): Arabic now reads «٣٠٠ ج.م» / «ر.س» (Intl symbol, English unchanged); then re-record the Arabic rounds and rebuild the Arabic v2.5 cuts. UI: #305, #308, #311; re-shoot and cuts: this PR | Orch → Agy | P-53 | PR open (PPS-84) |
| [ ] P-57 | — | Faster Claude sessions (owner, 2026-10-26): every session started at ~102k tokens and 31% of model calls ran past 400k, where a call is ~60% slower. Trimmed always-loaded context: `CLAUDE.md` 21 → 10 KB (stale speckit tech list, change log and narrative phase removed) and, outside the repo, 147 unrelated subagent definitions archived | Orch | — | PR open (PPS-87) |
| [ ] P-58 | — | RFQ flow review 2026-10-28 on «مطاعم رواق» (`docs/gtm/gcc/rounds/flow-review-2026-10-28/`): RFQ lines keep the buyer's order (`rfq_line.position`, R2); product picker search (R5); supplier emails shown (R4); `dir="auto"` on terms (R3); Quantity focus after a pick (R1); new RFQ Details page with Details / Items / Recipients / Responses tabs and breadcrumbs (O4, O5); history: sent date + time (O1), recipients popover (O3), responses link and "•••" menu with Duplicate (O6); date-only strings stay on their calendar day (O2). Out of scope pending owner: RFQ email locale (R6), delivered/opened tracking, cancel/resend | Orch → Codex + Agy | — | PR open (PPS-88) |
| [x] P-86 | — | Round-1 flow review continued on «مطاعم رواق» (2026-10-30, `docs/gtm/gcc/rounds/flow-review-2026-10-28/`): steps 3–8 (authorize → auto-match 97% → guardrail draft → submit → approve → PO-000005, SAR 4,830), basket split SAR 4,770, savings outcomes. New findings R7–R18, all open: authorize busy state (R7), quote number formats and VAT per line (R8, R9), per-line compare and guardrail outcome text (R10, R11), requester name (R12), duplicate-PO risks (R13, R14), basket split input and RFQ link (R15, R16), outcome formats/VAT label and baseline rounding (R17, R18) | Orch (Claude in Chrome) | — | write-up merged (#336, PPS-117 Done); R13 → P-87, R14 → P-88; R7–R12, R15–R18 not scheduled |
| [ ] P-87 | — | Create Purchase Order stays on the filled form after «Order created successfully.» (flow review R13): diagnose why the success navigation (`order-create.component.ts:430–433`) did not open the PO on hosted, land on the PO page every time, and keep the button disabled until then so no second PO can be created | — | — | To Do (PPS-118) |
| [ ] P-88 | — | An ordered request still offers «Create purchase order» after its PO covers every line (flow review R14; also round 1): `canCreateOrder` (`request-form.component.ts:102–105`) checks approval only; show the button only while a line has remaining quantity, else link the PO(s); the API refuses over-ordering | — | — | To Do (PPS-119) |
| [ ] P-89 | — | Confirm & Authorize shows no busy state for ~5 s (flow review R7): disable the actions and show «Authorizing…» until the response; measure whether matching preparation is the delay | — | — | To Do (PPS-120) |
| [ ] P-90 | — | Quote review shows the unit price as «86.0000» while in review (R8): no trailing zeros in the editable value (`quotation-lines.component.html` ~178) | — | — | To Do (PPS-121) |
| [ ] P-91 | — | VAT-inclusive quotes record no VAT per line (R9): product decision on how to store VAT-inclusive pricing, extraction reads «شامل ضريبة القيمة المضافة N%», carried to PO line tax and savings (with R17) | — | — | To Do (PPS-122) |
| [ ] P-92 | — | RFQ Responses compares totals only (R10): mark the cheapest supplier per line and show the split saving with a link to Basket Split (coordinate with 024 / PPS-96) | — | — | To Do (PPS-123) |
| [ ] P-93 | — | RFQ Responses guardrail outcome (R11): fired outcome not styled as an error, link to the draft it prepared, Prepare Request disabled once the RFQ is converted, «not open» explained | — | — | To Do (PPS-124) |
| [ ] P-94 | — | Approval Queue shows the requester's email (R12): find why `requester_name` is empty, give members a name, short fallback with tooltip | — | — | To Do (PPS-125) |
| [ ] P-95 | — | Basket Split input (flow review R15): new rows start empty, no duplicate product in one basket, pack hint no longer overlaps the next row | — | — | To Do (PPS-126) |
| [ ] P-96 | — | Basket Split from an RFQ and back (R16): start a split from RFQ Responses pre-filled; «Prepare requests» from the result (one draft per supplier, 024 request groups). Fold into the next 024 phase if already planned | — | — | To Do (PPS-127) |
| [ ] P-97 | — | Record outcome (R17): no trailing zeros («675.000000», «1230.0000»); the «excl. tax» label follows the VAT basis decided in P-91 | — | — | To Do (PPS-128) |
| [ ] P-98 | — | Savings baseline from a quoted price (R18): pack price × packs like the PO path, so 85 × 15 = 1,275.00 not 1,275.01 (`savings/baseline.py` ~159–162) | — | — | To Do (PPS-129) |
| [ ] P-102 | — | `GET /quotations/{id}/matches` takes 3–6 s on a prepared 4-line quote: one round trip per line, candidate and task, and preparation re-run on every read (`matching/service.py` `quotation_matches`). Batch the reads and skip preparation once settled; confirm-side background prep stays with PPS-130 | — | — | In Review (PPS-133) |

### E — Pilot environment

- [ ] **E-1 Stand up the pilot environment** per D-1. If self-hosted: Phases 1–2 of
  `docs/operations/self-hosted-deployment-plan.md` (ops only, no code). Either way: daily automated
  DB backups + **one tested restore**, migrations as an explicit deploy step, secrets separate
  from staging; database and admin consoles not publicly exposed; host hardening; `pnpm test:isolation`
  green against it; a full live walkthrough on it. Owner: Orch + User (infra access). Depends on: D-1. Done: restore tested and
  recorded; app reachable over HTTPS; Mailgun inbound reaches it. Space: PPS.

### B — Backlog (after pilot / before GCC; not blocking customer #1)

- [ ] **B-C4** FX / exchange rates (pilot workaround: EGP-only suppliers, EGP baseline). Lane, after pilot.
- [ ] **B-C5** VAT: add inclusive/exclusive semantics on top of the existing `quotation_line.vat_rate` — not a second rate (workaround: ex-VAT quotes). Lane, after pilot.
- [ ] **B-G1** One shared currency list (add QAR, KWD, BHD, OMR). Before first GCC prospect.
- [ ] **B-G2** 3-decimal currencies (KWD/BHD/OMR) rounded to 2 in ~23 places → use currency minor units. Before GCC.
- [ ] **B-G3** Extraction: recognise ر.س / د.إ / د.ك / ر.ق / ر.ع. Before GCC (pairs with P-3).
- [ ] **B-G4** Per-country VAT (builds on B-C5). Before GCC.
- [ ] **B-G5** KSA ZATCA e-invoicing — only when accounting matters for a Saudi customer.
- [ ] Fit gaps from the GTM plan (WhatsApp channel, non-Square POS, Odoo/local accounting, PO
  approval on mobile) — only if a real pilot is blocked; enter as `from-pilot`.

---

## 4. Dependency order

```text
user approval ─► G-0 (commit plan) ─► J-5 (create PP tasks)
J-1 ─► J-2, J-4 ─► J-6 ; J-3 independent
J-1 + J-4 ─► G-7 (Leads) ─┐
G-3 ─► G-4, G-5 ──────────┤
P-1 (C1) ─► G-1 (demo tenant) ─┐
P-2 (C3) ──────────────────────┴─► G-2 (demo video) ─► G-9 (outreach, 20 conversations)
P-1 ─► P-3 (C2 test + fix)
D-1 ─► E-1 (pilot env)
D-2 ─► G-6 (pilot agreement)
E-1 + P-1 + P-3 ─► G-8 (onboarding runbook) ─► first real customer record
G-9 ─► Qualified Lead ─► G-6 offered ─► Pilot (needs G-8 done)
```

**Critical path to the demo video:** P-1 + P-2 + G-1 → G-2.
**Critical path to onboarding a pilot:** D-1 → E-1, plus P-1 → P-3, then G-8.
Can start now with no blockers: J-1, J-3, G-3, P-1, P-2, D-1/D-2/D-3.

---

## 5. Handoff log

Append one row per session. Newest at the bottom. Include Jira keys and PR numbers.

| Date | Model / agent | What was done | Next step |
|---|---|---|---|
| 2026-10-14 | Claude (orchestrator) | Revised GTM plan (uncommitted); created Jira spaces PP and SP; SP workflow (7 statuses) + 5 Lead custom fields done; J-4 test passed on SP-1 (parked at Not now); wrote this file | User deletes SP-1; J-3 (column order); get user approval → G-0, then J-5 |
| 2026-10-14 | Claude (orchestrator) | User approved both docs → committed (G-0); created PP-1..PP-13 (J-5); teammate invite to the site dispatched to a side agent (result pending) | Start P-1 / P-2 specs (Speckit) and G-3 draft; user: D-1, D-2, delete SP-1 |
| 2026-10-14 | Claude (orchestrator) | Spec `specs/022-home-currency-readiness/spec.md` (covers PP-1, PP-2, PP-3 fix) committed c8e2c1a and pushed on branch `022-home-currency-readiness` — **plan/tasks are being produced by a separate Claude CLI session in the main checkout; it owns the 022 PR**. PP-7: three pitch-line drafts posted (recommend C for DMs, A for one-pager). PP-3: 5 synthetic Egyptian test quotes + expected.json attached (no real quotes publicly available). D-1 = B recorded on PP-4. D-2 recommendation posted (awaiting confirmation). Omar invited. SP-1 deleted. This file pushed as PR #72. | User: confirm D-2, pick PP-7 line, merge #72. Then: G-6 draft (PP-10) once D-2 confirmed; E-1 setup (PP-4) after tier confirmation; run PP-3 fixtures before + after 022 ships |
| 2026-10-14 | Claude (orchestrator) | D-2 confirmed. Pilot agreement drafted as a Claude Doc (EN + AR, 15 clauses, Annex A week-0 baseline): https://claude.ai/code/artifact/7f1d9481-a2a7-43a7-a0e4-b397c64e042b — linked on PP-10. Open question in the doc: liability cap. | User: review agreement, answer liability-cap comment, lawyer review before first signature |
| 2026-10-14 | Claude (orchestrator) | All GTM docs moved to `docs/gtm/` (README indexes them + live Claude Doc / canvas links); one-pager PDF and PP-3 test fixtures added there. PP-7, PP-8, PP-9 Done. **Note for the 022 session:** `specs/022-home-currency-readiness/spec.md` still cites `docs/product/first-customer-gtm-plan.md` — update to `docs/gtm/` when convenient. | PP-10 user review; PP-11 prospect list |
| 2026-10-14 | Claude (orchestrator) | Codex review on PR #72 verified and applied: `tenant.currency` already exists (C1/P-1 = wire it into forms, no schema); `quotation_line.vat_rate` exists (C5/B-C5 = inclusive/exclusive only); unresolved currency → human review, never a tenant default (C2/P-3); production hardening + `test:isolation` + live walkthrough before onboarding (E-1); Agy flag wording. **Spec 022 is now out of step:** US1 FR-001..FR-003 (new owner-set home currency) are unnecessary, and FR-011 (fallback to home currency) contradicts the ingestion rule — the 022 session must revise before planning further. | 022 session revises spec; merge #72 |
| 2026-10-14 | Claude (orchestrator) | **Pilot shortened from 90 days to 2 weeks (14 days)** everywhere: GTM plan, pilot agreement, DM script, one-pager (canvas + PDF), Jira. Knock-on fixes: success-metric example now per-pilot not monthly; early exit any time in writing; two check-ins (week 1, day 14); the 14 days start after onboarding + first live RFQ. New Converge logo in PR #75. | Merge two-week-pilot PR and #75; one-pager to new logo |
| 2026-10-15 | Claude (orchestrator) | New Converge logo merged (#75, store icons opaque after Codex review); 2-week pilot + new-logo one-pager merged (#76). Demo-video decisions recorded in `docs/gtm/video/README.md`: screencast + 2D motion graphics, text + music (no voice), music Antalya Beaches (112.35 BPM, librosa beat map), beat-locked logo sting with «قارن. اختار. وفّر.», end card, five Pixabay sound cues. Sting + end card rendered (16:9 and fast 9:16), in user review. | User reviews outros; then PP-5 demo tenant → screencast recording |
| 2026-10-15 | Claude (orchestrator) | Founder title **Dr. Yasser Hosny / «د. ياسر حسني»** applied everywhere it is shown: one-pager (canvas AR+EN, PDF re-exported, re-attached to PP-8), DM script intro lines, video end cards + outros (re-rendered), video README. Pilot agreement unchanged (signature fields are blank). English video versions added: sting "Compare. Choose. Save." + English end cards, 16:9 and fast 9:16, same beats/audio. | PP-5 demo tenant → screencast recording |
| 2026-10-17 | Claude (orchestrator) | Company-formation research in `docs/gtm/company-formation/` (Arabic): 22 Lean Startup Circle Egypt posts + all comments read via Claude in Chrome, key facts verified against official/professional sources (Law 6/2025 rates + consulting exclusion, VAT, e-invoicing, OPC capital EGP 1,000, Delaware $400 LLC tax, Form 5472, BOI). Recommendation: Egyptian one-person company on the simplified regime now; Delaware C-Corp flip only at a funding round. Setup guide, 3-year cost comparison, flip-readiness checklist added. | User books an Egyptian accountant (questions in `recommendations.md` §6), then incorporates; pilot agreement (G-6) moves to the company name |
| 2026-10-18 | Claude (orchestrator) | P-1 ticked (shipped in 022, #73). P-2 code merged (#73/#124) but left open until its screenshots (022 T018). P-3 fix merged, real-quote run still 022 T015. Roadmap v1.2 records the security review and the background workers missing on hosted | Demo video first; then one combined jobs container for the missing workers; demo findings 22–30 |
| 2026-10-22 | Claude (orchestrator) | Jira brought up to date with work since 10-18. **Done:** PP-5 (demo tenant, walkthrough runs end to end), new PP-18 (fix-wave record, findings 1–49). **Progress comments + `in-progress` label:** PP-2 (T018 screenshots left), PP-3 (T015 real-quote run left), PP-6 (cuts v2.2, owner review left), PP-10 (liability cap, lawyer, company name left). PP-4 status comment. **New:** PP-14 (combined jobs container), PP-15 (finding 20), PP-16 (finding 50), PP-17 (company formation). Blocks links per §4; priorities High on the critical path (PP-3, PP-4, PP-6, PP-11, PP-13). | User: add board columns (see §2 progress convention), then the orchestrator moves issues; user reviews video cuts (PP-6) |
| 2026-10-24 | Claude (orchestrator) | Web app on Angular 22 + Material 22 (P-9, #230) and the Ledger design system adopted (P-10, #234) and built into `apps/web` (P-11, #235). Fixed the flaky `mat-select` E2E that the upgrade exposed (P-12, #237): Material 22's closing panel still takes clicks for 100 ms, so E2E now runs with reduced motion. PPS-17, PPS-32, PPS-33, PPS-34 Done. New standing rules: front-end/design fixes go to Agy; `docs/design/design-system.html` is the reference for UI changes. | Follow-ups on PPS-33 (email word-break, style budgets, unused `material-icons`, dark mode), unscheduled |
| 2026-10-24 | Claude (orchestrator) | P-14 / P-15 created (PPS-35, PPS-36; PPS-33 blocks both, PPS-35 blocks PPS-36; drafted as P-12 / P-13, renumbered twice: P-12 is PPS-34, P-13 is PPS-38). P-14 guest landing page + EN / عربي toggle on landing and sign-in implemented by Agy on `feat/guest-landing-page`; includes a guest-locale fix in `I18nService` (the session effect overwrote a guest's stored Arabic with `en`). Gates re-run by the orchestrator: lint, 916 unit tests, build, landing E2E against an isolated build; driven in a browser in en + ar and at phone width. Local `procurepilot-web` (:4200) had been serving branch builds; rebuilt from main 18ab083. | Open the PR. P-15 after it merges |
| 2026-10-24 | Claude (orchestrator) | P-14 merged (#240, live). Owner found it too thin; Codex and Agy reviewed the content (Agy's unprovable claims dropped: WhatsApp ingestion, security superlatives, "immutable ledger", invented refs). P-15 built in two lanes and merged on `feat/landing-rich`: Agy the page, Codex the bilingual gallery capture. Owner rule mid-task: no local Supabase anywhere, so captures run from a dev machine against the hosted app with the reserved `landing-gallery-demo` tenant (`pnpm --filter web landing:screenshots`, opt-in `CAPTURE_LANDING_GALLERY=1`). Captures exposed two app display bugs (approval-queue raw decimal quantities; pending savings under a "Verified Saving" header), offered as separate tasks. | Merge the P-15 PR |
| 2026-10-24 | Claude (orchestrator) | P-15 merged (#242, live). Owner asked for a more elegant page with a scrollable gallery: find-skills search (installed `copywriting`, coreyhaines31/marketingskills), impeccable critique of the live page (26/40, dual assessment), copy pass, then P-20 built on `feat/landing-v2` (Agy; Codex for the 2x hero crop captured from hosted and the final polish after an Agy quota hit). Another session reused P-14 for PPS-41; flagged to the owner. | Merge the P-20 PR |
| 2026-10-24 | Claude (orchestrator) | P-16 to P-18 done, all implemented by Agy and verified by the orchestrator. P-16 (#241): email wrapping, `material-icons` removed. Two Agy attempts at the 4 kB style budgets were rejected because they deleted 31 mobile breakpoint rules; the owner chose to leave those warnings. P-17 (#245): mobile design system plus the blank mobile-web-build fix; review caught an Arabic `MaterialLocalizations` crash and an 85 px app-bar overflow first. P-18 (#246, #249): grouped, collapsible sidebar; three flat-sidebar E2E tests updated. Plan IDs were renumbered from P-13 to P-15 after colliding with another session's rows. | Mobile mockups in `docs/user/screenshots/mobile/` still show the old look; dark mode needs an owner decision |
| 2026-10-24 | Claude (orchestrator) | P-23 (PPS-49): the mobile guide's mockups are replaced by real renders of the shipped app, which supersedes the "mobile mockups still show the old look" note above. Regenerate with `cd apps/mobile && flutter test --tags docs --run-skipped test/docs/`. The real request-detail render exposed a bug: the approval step shows the approver's raw member ID and an ISO timestamp. It is documented as a limitation and suggested as a separate fix. | Approver name and local date on mobile request detail (not yet tracked in Jira); dark mode needs an owner decision |
| 2026-10-25 | Claude (orchestrator) | P-37 (PPS-67): `find-skills` (vercel-labs/skills) added to the repo at `.claude/skills/find-skills/`, unchanged from the source, so every session can search for and suggest skills; merged in #288. PPS-67 Done. | — |
| 2026-10-28 | Claude (orchestrator) | P-59 (PPS-89): UX audit of the RFQ pages and of round 1 end to end on «مطاعم رواق» with four skills (ux-audit, ux-heuristics, impeccable critique, ui-ux-pro-max); reports in `docs/quality/ux-audits/2026-10-28-*`. Both verdicts Fail: round-1 heuristic score 5/10, impeccable 21/40; every step dead-ends, the RFQ is lost after step 1, request/approval/PO never name the supplier. Fix tasks P-60 to P-75 (PPS-90 to PPS-105) in the backlog; P-73 (PPS-103) needs owner decisions; P-65/P-66 need a short spec. | |
| 2026-10-28 | Claude | P-76 (PPS-106): competitor quick-scan profiles in `docs/gtm/competitor-profiles/` (Supy, Foodics, Suplyd, MarketMan, Apicbase + `_summary.md`). No competitor shows RFQ / quote comparison on the pages checked; Supy is the GCC reference, Suplyd the Egypt objection, Foodics a likely integration. Next: verify gaps in a Supy demo, battlecards via `sales-enablement`. | |
| 2026-10-28 | Claude | P-77 (PPS-107): cold email sequence `docs/gtm/outreach/cold-email-sequence.md`, 4 emails / 14 days, AR + EN, beside the DM script; Supy/Suplyd/Foodics variants, KSA adaptation. Owner decisions before first send: secondary sending domain + warm-up, footer postal address, KSA price. | |
| 2026-10-29 | Claude | P-78 (PPS-108): prospect list wave 1, Egypt multi-branch F&B, 24 accounts (9 Warm, 0 Hot: no verified contacts). Kept local in `docs/gtm/prospects/` (excluded from git: public repo); SP is the system of record. Next: contact paths for Warm accounts, load into SP at Target. | |
| 2026-10-29 | Claude | P-78: 9 Warm Egypt leads loaded into SP (SP-2 to SP-10, Target). P-79 (PPS-109): KSA prospect list wave 1, 13 rows, 5 Warm, local only; research targets until KSA price, Saudi demo workspace (PPS-39) and Gulf copy exist. | |
| 2026-10-28 | Claude (orchestrator) | P-65/P-66 (PPS-95/96): drafted specs `specs/023-rfq-aware-matching` (replies to an RFQ match against the RFQ's own lines; one confirmation of a wording clears every open line using it; extraction keeps the printed pack) and `specs/024-rfq-basket-split` (split an RFQ from its Responses, priced only from its replies; prepare one draft request per supplier, all-or-nothing; approver sees the split). Owner decisions the same day: Q1, an RFQ match that fits exactly one RFQ line is accepted automatically (so match decisions become correctable); Q2, a split's requests are approved as one group, routed by the combined total. Next: `/speckit.plan` for each. | |
| 2026-10-28 | Claude (orchestrator) | P-65/P-66 (PPS-95/96): `/speckit.plan` for 023 and 024. Plans, research, data models, contracts and quickstarts are in `specs/023-rfq-aware-matching/` and `specs/024-rfq-basket-split/`. 023: an `rfq-fit-v1` rule ahead of catalogue search; match decisions become correctable through an insert-only supersession chain and a `current_match_decision` view (about 19 readers move); alias sweep; Azure pack column. 024: the advanced optimiser priced only from the RFQ's replies (pack↔base conversion); atomic `prepare-requests` under the existing RFQ lock; a `purchase_request_group` layer whose approval is routed by combined total. Next: `/speckit.tasks`. | |
| 2026-10-28 | Claude (orchestrator) | P-65/P-66 (PPS-95/96): `/speckit.tasks` for 023 (35 tasks: foundational supersession migration, view and reader move in-house; US1 RFQ fit and correction; US2 measured signals; US3 alias sweep; US4 pack column) and 024 (37 tasks: foundational group table, RLS and conversion lock in-house; US1 split from RFQ; US2 prepare N requests; US3 group approval by combined total, which must ship with US2; US4 standalone page). Tests are written first throughout. Next: implementation, 023 Phase 2 first. | |
| 2026-10-29 | Claude (orchestrator) | P-80 (PPS-110): `test_supplier_iq` trace test failed from 00:00 to 03:00 Cairo time because it compared `date.today()` (local) with the scorecard's UTC `window_end`. The service stays on the UTC date (specs 011/019 name no time zone; `reporting_timezone` is for scheduled reports only). Fix: `supplier_iq._utc_now()` clock seam; the test reads today from it; a regression test freezes 00:30 Cairo (21:30 UTC the day before). Verified red then green on hosted (:5432) under TZ=Africa/Cairo and UTC. | |
| 2026-10-30 | Claude (orchestrator) | P-81 (PPS-112): a purchase request created during a match correction can keep the superseded price (023 US1 review finding D2; needs the correction lock on request-line pricing). P-82 (PPS-113): deterministic (alias/GTIN/supplier-code) auto-matches offer no other candidate to correct to, and a keyed new-product retry cannot repair a missing pack. Both from the 023 US1 review (#331), backlog. | |
| 2026-10-30 | Claude | Sales-skill assessment → three tasks. P-83 (PPS-114): status-quo battlecard `battlecards/whatsapp-excel.md` + `outreach/discovery-demo-call-script.md` (AR + EN, `sales-enablement`). P-84 (PPS-115): `community/g7-community-plan.md` for G-7 (`community-marketing`, installed 2026-10-30 from coreyhaines31/marketingskills). P-85 (PPS-116): `research/` call-notes template + synthesis method (`customer-research`); filled notes local in `research/calls/` (excluded); phase 2 synthesis blocked by G-9. Skipped: Apify OSM leads, social scraping, outbound-prospecting. | Owner: review the Arabic copy; pick the first 3 communities. |
| | | | |
