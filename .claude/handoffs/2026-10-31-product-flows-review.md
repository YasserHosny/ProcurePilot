# Handoff: "Product flows review" (session 253b2b77, app id local_e7af5fa6…)

Written 2026-10-31 from the transcript and live GitHub and Jira state. The session's last activity
was 2026-10-30 22:11 UTC; it is idle, with no turn in flight. Its context had grown to ~770k tokens,
and calls there take ~7 s. Read this note, then `CLAUDE.md`. Archive the old session once this one
is running.

## What this session is

The **orchestrator** for the round-1 flow review on «مطاعم رواق» (Saudi demo, PPS-117):

- It walked steps 3–8, basket split and savings live in Chrome, and wrote findings R7–R18 into
  `docs/gtm/gcc/rounds/README.md`, with screenshots in `flow-review-2026-10-28/` (#336). The
  earlier findings R1–R6 and O1–O6 are in the same README.
- It scheduled each finding as a PPS task (#340, #345, #347) and spawned **one fix session per
  task** (`spawn_task` chips).
- Since then it has only coordinated: answering "check other sessions", nudging idle sessions, and
  merging when green with its own watcher.

It writes no product code itself. Keep that split: the fix sessions implement, the orchestrator
tracks and merges.

## Fix sessions and where each stands (as of 10-30 22:11 UTC)

| Task | Session (sidebar title) | State | Next |
|---|---|---|---|
| PPS-118, 119, 132 (duplicate-PO risks) | "Fix duplicate-PO risks PPS-118 and PPS-119" | **Done** (#348, #350, #357, #358) | Archive the session |
| PPS-120, 121 (quote-review busy state, prices) | "Fix quote review: PPS-120 busy state, PPS-121 prices" | **Done** (#360, live check #361) | Archive both copies |
| PPS-126, 127 (Basket Split input; RFQ ↔ split) | "Fix Basket Split: PPS-126 input, PPS-127 RFQ link" | **Done** (#356, #362) | **#363** (post-deploy write-up, docs) is open: merge when green, then archive the older *waiting* copy |
| PPS-129 + PPS-128 part 1 (rounding, formatting) | "Fix savings: PPS-129 rounding, PPS-128 formatting" | PPS-129 **Done** (#355, #364) | — |
| PPS-125 (requester names) | "Fix Approval Queue requester name (PPS-125)" | Merged (#359; migration `20261030000000` applied to hosted first). Jira **In Review** | Live check as `+pp-sa-owner`, then Done. It was waiting for the owner's sign-in |
| PPS-122 + PPS-128 part 2 (VAT-inclusive pricing) | "Implement VAT-inclusive pricing (PPS-122, PPS-128 pt 2)" | **Running**, In Progress | Asks the owner before its hosted migration and before correcting the old Saudi POs; no merge without the owner's OK |
| PPS-123, 124 (RFQ Responses: cheapest per line; guardrail outcome) | "Fix RFQ Responses: PPS-123 per-line, PPS-124 guardrail" | **Idle, nothing pushed.** Ignored two nudges; its local build was on `localhost:4300` | Owner opens it and says "continue" |
| PPS-133 (`/matches` 3–6 s → <0.9 s) | "Speed up GET /quotations/{id}/matches" | Fix ready, **waiting for the owner's OK** to push and open its PR | Then re-measure confirm (decides PPS-130) |
| PPS-134 (RFQ emails in the supplier's language, R6) | "RFQ emails in the supplier's language (PPS-134, R6)" | Idle; probably waiting for a go-ahead (migration or emailing supplier aliases) | Owner answers it there |
| PPS-131, 135 (docs screenshots check) | "Fix failing Docs screenshots drift check" | PPS-131 Done (#353); **#365 merged** (`7a23fa11`): the check now always reports | Confirm it reports on a docs-only PR and on a web PR, then add it to `main`'s required checks **under its new name «Capture and compare screenshots»**. An old-name required check never reports and blocks every PR. The owner approved the change in principle (memory: docs-drift-check…), but the branch-protection edit needs a go-ahead in that session |
| PPS-136 (E2E gate green when `changes` fails) | "Fix End-to-end gate passing when changes fails" | **#366 open**, Jira In Review | Merge when green. Until it lands, check `changes` explicitly before merging any PR |

Separate, not this session's work: "Finish specs 023/024" (`.claude/handoffs/2026-10-30-specs-023-024.md`)
is re-walking round 1 on hosted. It overlaps the fix sessions' live checks in «مطاعم رواق», so
don't run two live walks in that workspace at once.

## Decisions the owner approved (10-30)

- **VAT storage** (recorded on PPS-122):
  - Quotes keep their printed prices, with a new `quotation.prices_include_vat` flag.
  - Landed cost gets a **new rule version** that doesn't add VAT on top of VAT-inclusive prices.
    Today's rule adds `price × qty × vat_rate`, so extracting 15% would count VAT twice: 4,830 → 5,554.50.
  - POs from VAT-inclusive quotes become net + tax, with totals that match the printed total exactly.
  - Savings use net amounts.
  - Saudi PO-000001…000009 store gross prices with 0 tax, so they need a data fix, with the owner's OK.
- **R6:** supplier emails use the supplier's language, falling back to the workspace default, never
  the buyer's UI language (PPS-134).
- **O3:** no Delivered/Opened tracking for the pilot; sent/failed is enough.
- **PPS-130** (prepare matches in the background after confirm): only if confirm is still over
  ~2 s after PPS-133 merges.
- **Docs check required:** yes, once it always reports (done in #365); see the PPS-135 row.

## How it merges

- "Merge when green" means a watcher that squash-merges at the PR's head SHA once every gating check
  has passed **on that SHA**: the 8 required checks + `changes` + «Capture and compare screenshots»
  for web PRs.
- Apply a PR's migration to hosted **before** merging it, with the owner's go-ahead, and then
  `pnpm db:check-privileges`.
- After a merge, confirm the backend and frontend deploys for the merge commit, then let the fix
  session run its live check and move its task to Done.

## Gotchas

- **Watcher scripts in a shared folder got rewritten.** `~/Work/.tmp-debate/watch-pr.sh` was
  changed by another session, and #362's watcher silently dropped the docs-check gate. The merge
  was fine, as checked afterwards. Keep watcher scripts in **this session's own scratchpad** with
  session-specific names.
- **Chrome is signed in to «مطاعم سند»** (`+pp-owner`) on procurepilot.iron-sys.com. Never act
  there. Live checks need `yasserhonsy+pp-sa-owner@gmail.com` in «مطاعم رواق». Before clicking
  anything, confirm the workspace switcher shows «مطاعم رواق». Ways in:
  - a fix session's built-in browser pane;
  - Chrome on `localhost:43xx`, which has a separate sign-in.

  Never type passwords; the owner signs in. Autofill may pick `+pp-owner`.
- **Local ports belong to sessions:** 4300 is RFQ Responses, 4310 is quote review. The app's preview
  manager has stopped them before; check one answers before telling the owner to sign in.
- **`pp-sa-buyer` doesn't exist on hosted.** The Saudi workspace has a single member, the owner, whose
  display name is «المالك».
- **Duplicate sessions** appeared twice (quote review, Basket Split, and this session itself). Before
  nudging, check `list_sessions` for two copies and close the extra.
- Status updates cover only this orchestrator's own PRs and tasks (memory: report-only-own-prs).
  Other sessions report their own.

## Jira hygiene still owed

- PPS-125: Done after its live check.
- PPS-135: Done after the required-check change.
- PPS-136: Done after #366 merges.
- PPS-117 is Done. Add a Progress comment on each state change (CLAUDE.md).
