# Release Evidence — 022 Home Currency and the October 2026 Demo Fix Wave

Recorded 2026-10-18. Covers `specs/022-home-currency-readiness` and the fixes that came out of building the
hosted demo tenant «مطاعم سند» (`docs/gtm/demo-tenant/README.md`, findings 1–20). Gate posture is unchanged:
G3 remains unmet (`docs/quality/r4.3-release-evidence.md`).

**What this record is:** where each change landed and how it was checked. Test runs listed under each PR's
"proof" are that PR's own claims, re-checked by CI on merge; they were not re-run for this record. "Live" means
checked on the hosted demo tenant after deploy.

## 022 — Home currency readiness

| Item | Evidence |
|---|---|
| Merged | PR #73, `4da3c21`, 2026-10-14; all CI checks green, merged without admin override |
| Hosted migrations | `20261014000001_tenant_set_currency`, `20261014000002_review_reason_currency_unresolved` applied 2026-10-15 (`supabase migration list` shows them remote) |
| EGP default end-to-end test | PR #83, `6e01f74`: EGP workspace → order, RFQ guardrail and supplier forms default to EGP; an explicit USD order is saved as USD. Passed CI End-to-end. Not yet shown to fail when the expected currency is wrong |
| Open tasks | T015 real Egyptian quotes through the full pipeline (needs Azure keys); T018 mobile screenshots (needs Flutter + emulator); T020 full test pass |
| Known gap (closed) | Mobile **My Requests** list printed raw amounts; fixed by PR #124 (`formatMoney`), merged 2026-10-18 |

## Demo fix wave (2026-10-15 to 10-17)

Merge dates are UTC.

| PR | Commit | Merged | Change | Finding | Live check |
|---|---|---|---|---|---|
| #84 | `a9a34c3` | 2026-10-15 | RFQ-reply supplier wins attribution | 2 | — |
| #87 | `822b22a` | 2026-10-16 | Prepared statements off on every connection | 1 | CSV import re-run on hosted |
| #88 | `7977c2f` | 2026-10-16 | Calendar dates sent as local dates | 7 | Deployed |
| #89 | `4cdba09` | 2026-10-16 | Localised supplier RFQ email, buyer terms stored, Arabic slugs | 10, 11 | Migration applied |
| #90 | `c19af70` | 2026-10-16 | ASCII-safe storage keys, failed emails visible | 12 | Two demo emails re-ingested with Arabic names |
| #96 | `d7f0424` | 2026-10-16 | Dates parsed in Python, `date_unparsed` review | 14 | Both demo quotes re-extracted |
| #100 | `7972d2a` | 2026-10-16 | RTL table lines, structural review reasons | 15 | Both demo quotes re-extracted with 5 lines each |
| #103 | `d09bc07` | 2026-10-17 | Home modules, RFQ draft edit/send, kg unit merge, import pack | 3, 4, 5, 8, 9, 13 | Deployed, migrations applied |
| #104 | `92977b8` | 2026-10-17 | A quotation can always be authorised | 16 | Both demo quotes authorised |
| #108 | `3fda432` | 2026-10-17 | Optimiser image and deploy, stuck jobs fail | 17 | Container created by the owner; deploy passed 2026-10-17 (UTC). No basket split re-run on hosted yet |
| #109 | `8304739` | 2026-10-17 | Verified matches, exact-name bulk confirm | 20 (partly) | Deployed; hosted still on the stub embedding |
| #110 | `4ebef39` | 2026-10-17 | Per-pack estimates (ADR-020) | 18 | Deployed; PO step not yet re-run on hosted |

Since this record: finding 19 (request-flow gaps) fixed by PR #112, merged and deployed 2026-10-17, and verified on hosted 2026-10-18 (round 1 request → approval → PO-000001). Still open: finding 6 (team invites not emailed; PR #111 adds an
operator workaround).

All migrations in the repository up to `20261017000003` are applied to hosted (checked 2026-10-18).

## Not covered by this record

- No security review was done for these changes; the last security review record is
  `docs/quality/r3.1-accounting-security-review-record.md`.
- No business metric in roadmap §15.2 has been measured; there is no pilot customer yet.
