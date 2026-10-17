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
| Products | Jira (**business tier only** — no Jira Software: no Epic, no Bug, no sprints, no GitHub dev panel), Jira Product Discovery, Confluence, Loom |
| Space `PP` | ProcurePilot — non-code work + demo/pilot gaps |
| Space `SP` | Sales Pipeline — one Lead per prospect company |
| Space `MDP` | JPD sample data (MDP-1..6) — in the Jira trash; **ignore** |
| Members | Dr. Yasser Hosny (owner); Omar Medhat (mr.omarmedhat@gmail.com) invited 2026-10-14 — JPD "User (creator)", Goals/Projects/Studio user, not admin; free plan gives every member access to PP and SP |

**Tool capabilities:**

| Tool | Can | Cannot |
|---|---|---|
| Atlassian MCP connector (Claude Code) | create / edit / transition / comment issues, JQL search, Confluence pages | create spaces, rename statuses, add/edit custom fields, reorder board columns |
| Browser (Claude in Chrome, user's signed-in session) | space/field/workflow/board admin | — (still: no deletes, no sends without user OK) |
| Non-Claude models (Codex, agy, OpenCode) | code + docs in the repo | no Atlassian access assumed — leave Jira steps for an orchestrator with the connector, or the user |

### Workflow split (decided, user-approved 2026-10-14)

- **Code** → Speckit (`spec.md` → `plan.md` → `tasks.md`) → delegation lanes → PR → CI → merge.
  Never duplicated into Jira.
- **GTM / ops** → Jira `PP`. Done = sent / published / held / signed (not "drafted").
  Drafting (scripts, one-pager copy, agreements) can be done directly by the orchestrator — no
  code lane needed.
- **Bridge (one-way)**: demo/pilot gap → `PP` task labelled `from-demo` / `from-pilot` → if it
  needs code, a Speckit spec → the `PP` task links to the PR.
- **Sales conversations** → `SP` only, never `PP`.

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

### GTM plan file

| Item | State |
|---|---|
| `docs/gtm/first-customer-gtm-plan.md` | Revised and approved 2026-10-14; committed with this file (G-0). Other untracked files under `docs/` are unrelated — don't sweep them into commits. |

### Space `PP` — ProcurePilot

| Setting | Value | State |
|---|---|---|
| Template | Task tracking (team-managed, business) | Done |
| Work types | Task, Sub-task | Done |
| Labels in use | `from-demo` (product gaps), `gtm`, `ops`; `from-pilot` reserved | In use |
| Issues | 13 tasks created 2026-10-14 (J-5) — mapping below | Done |

**Plan ID → Jira key** (summaries are prefixed with the plan ID, e.g. `[G-2] …`):

| Plan ID | Key | Plan ID | Key | Plan ID | Key |
|---|---|---|---|---|---|
| P-1 (C1) | PP-1 | G-1 | PP-5 | G-6 | PP-10 |
| P-2 (C3) | PP-2 | G-2 | PP-6 | G-7 | PP-11 |
| P-3 (C2) | PP-3 | G-3 | PP-7 | G-8 | PP-12 |
| E-1 | PP-4 | G-4 | PP-8 | G-9 | PP-13 |
| | | G-5 | PP-9 | | |

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
  later option. Recorded on PP-4; confirm plan tier with the user before creating anything
  billable.
- [x] **D-2 Post-pilot price** — **confirmed by user 2026-10-14**:
  EGP 1,500 per branch per month (minimum 2 branches), annual = 10 months' price; founding-customer
  50% off for the first 12 months in exchange for case study + logo; savings guarantee — if
  verified savings in a month are below 3× the fee, the next month is free. Revisit after the
  first pilot's real savings data. Blocks: G-6 (PP-10).
- [ ] **D-3 Add Jira's free software plan?** (gets Epic/Bug/GitHub linking). Owner: User.
  Blocks: nothing. Done: yes/no recorded. Default if undecided: no.

### J — Jira setup

| ID | Task | Owner | Depends on | Done when | Space |
|---|---|---|---|---|---|
| [x] J-1 | Verify Contact, Role, City are saved on Lead; add Branches (number) and Source (dropdown, 4 options); click "Save changes" | Browser | — | All 5 fields visible on a new Lead's create screen | SP |
| [ ] J-2 | Confirm the template fields (Company size, Website, Email, Phone number, Start date, Category, Team) are still present; hide any unused from the create screen only if the user wants | Browser | J-1 | Create screen reviewed | SP |
| [ ] J-3 | Verify board column order is Target, Contacted, Talked, Qualified, Pilot offered, Pilot, Not now; reorder if "Pilot offered" is last | Browser | — | Board columns in stage order | SP |
| [x] J-4 | End-to-end test via connector: create dummy Lead → transition to Talked → add comment → set due date → run JQL `project = SP AND duedate <= now() AND status != "Not now"` and confirm it returns the dummy. **Passed 2026-10-14 (SP-1).** SP-1 deleted by the user 2026-10-14 | User | J-1 | SP-1 deleted | SP |
| [x] J-5 | Create PP tasks G-1..G-9, P-1..P-3 (as `from-demo`), E-1 below; put the task ID from this file in each summary (e.g. `[G-2] Demo video`) | Orch | G-0 | Issues exist; keys written back into this file's tables | PP |
| [ ] J-6 | Save the "weekly review" JQL as a filter (needs browser if connector can't save filters) | Browser | J-4 | Filter "SP — due or overdue" exists | SP |

### G — GTM assets (non-code, Jira PP)

| ID | Task | Owner | Depends on | Done when | Space |
|---|---|---|---|---|---|
| [x] G-0 | Commit `first-customer-gtm-plan.md` after user approval (that file only) | Orch | user approval | Commit on `main` (or PR) containing only that file | — (git) |
| [ ] G-1 | Demo tenant on hosted: dedicated tenant, Arabic supplier names, ~30-item F&B catalogue, 2–3 branches, EGP prices, one RFQ ready to send; no test leftovers | Orch + User | P-1 (forms default to EGP) | Tenant walkthrough runs clean end-to-end | PP |
| [ ] G-2 | 3-min demo video + 60-s vertical cut: Arabic UI, Arabic on-screen text + music (no voice-over), recorded with OBS; spec, storyboard and finished logo sting/end card in `docs/gtm/video/`. Script must follow the corrected walkthrough (human sends RFQ; guardrail on → draft purchase request; mobile approves the *request*; PO generated on web) | User (record), Orch (script) | G-1, P-1, P-2 | Video link stored on the PP task | PP |
| [ ] G-3 | Pitch line (Arabic + English) finalised | Orch draft, User approve | — | Approved text on the PP task | PP |
| [ ] G-4 | One-pager (Arabic + English): before (WhatsApp + Excel) vs. after (RFQ → compare → approve → PO) | Orch copy, User design | G-3 | Published PDF/link | PP |
| [ ] G-5 | Outreach DM script (Arabic + English), diagnostic-question first | Orch draft, User approve | G-3 | Approved script on PP task | PP |
| [ ] G-6 | Pilot agreement (1 page, Arabic + English) + week-0 baseline template: duration, success metric + baseline, day-14 terms, data ownership, supplier-price confidentiality, export/deletion on exit, Egypt PDPL (Law 151/2020) clause, C4/C5 workarounds (EGP-only suppliers, ex-VAT) | Orch draft, User approve (legal review advisable) | D-2 | Signed-ready PDF; baseline template (10–20 items, unit price, quote turnaround) | PP |
| [ ] G-7 | Community + target list: personal network audit, Egyptian founder/SME communities, LinkedIn search; each prospect → an SP Lead at Target | User (list), Orch (create Leads) | J-1, J-4 | ≥20 Leads in SP | SP |
| [ ] G-8 | Pilot onboarding runbook: CSV/manual supplier + catalogue load, branches/approvers, inbound-email address for WhatsApp-forwarded quotes, first live RFQ, support WhatsApp group (4 working-hour response) | Orch | E-1, P-1, P-3 | Runbook doc linked on PP task, dry-run on demo tenant | PP |
| [ ] G-9 | Outreach: work SP to 20 conversations at Talked+ | User | G-2, G-5, G-7 | 20 Leads at Talked or beyond | SP |

### P — Product tasks (PP `from-demo` → Speckit spec → code lane)

Each: create PP task labelled `from-demo` → write Speckit spec/plan/tasks → dispatch to a lane →
PR → CI → merge → link PR on the PP task. Refs are in the GTM plan's currency-gap tables.

| ID | Gap | Task | Owner | Depends on | Done when |
|---|---|---|---|---|---|
| [ ] P-1 | **C1** | Wire the **existing** `tenant.currency` (required at sign-up, returned by `/me`, already used by budget/threshold forms) into the forms that still default to USD: PO create, guardrails, quotation review fallbacks. No new setting, no schema/RLS change | Orch (spec + tenancy part), Lane (forms) | — | Merged; demo tenant set to EGP and every form opens in EGP |
| [ ] P-2 | **C3** | Locale-aware money formatting on mobile (grouping, currency minor units, ar/en) for approval queue + request detail | Lane | — | Merged; `flutter test` green; screenshots show `EGP 12,500.00` (and Arabic locale equivalent) |
| [ ] P-3 | **C2** | Test extraction with 5 real Egyptian quotes (incl. Arabic-Indic digits, ج.م / جنيه / LE); recognise Egyptian markers; replace the GBP fallback with **human review** for unresolved currency — never a tenant-currency default (also Azure DI £/$/€-only + hard-coded USD path; landed-cost GBP default) | Orch (test), Lane (fix) | — | Test results recorded on PP task; fix merged; q1–q3 extract as EGP; q4–q5 land flagged for review with no guessed currency |

### E — Pilot environment

- [ ] **E-1 Stand up the pilot environment** per D-1. If self-hosted: Phases 1–2 of
  `docs/operations/self-hosted-deployment-plan.md` (ops only, no code). Either way: daily automated
  DB backups + **one tested restore**, migrations as an explicit deploy step, secrets separate
  from staging; database and admin consoles not publicly exposed; host hardening; `pnpm test:isolation`
  green against it; a full live walkthrough on it. Owner: Orch + User (infra access). Depends on: D-1. Done: restore tested and
  recorded; app reachable over HTTPS; Mailgun inbound reaches it. Space: PP.

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
| | | | |
