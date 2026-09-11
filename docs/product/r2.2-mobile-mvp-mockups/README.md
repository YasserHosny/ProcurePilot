# R2.2 Mobile MVP — Stitch-generated mockups (reference only)

Generated 2026-09-11 from `docs/product/r2.2-mobile-mvp-DESIGN.md` and
`docs/product/r2.2-mobile-mvp-ui-mockup-prompts.md` via Google Stitch. Visual reference for Wave 2
implementers — **not** a source of requirements. The actual requirements are
`specs/009-mobile-app-mvp/spec.md` and, once written, its `tasks.md`.

**Read before building anything from these**: Stitch generated genuinely faithful screens against
every explicit constraint in the DESIGN.md's Do's/Don'ts (no camera/barcode/photo control on any
R2.2 screen, no approve/reject action anywhere, the approver's pending-count card is visibly
non-interactive, all six status chips pair color with an icon and a label, the notification
toggle's off-state explicitly says decisions still show in My Requests, sign-out is a standalone
row not nested in the account tile, language uses a segmented control not a thumbnail) — but it
also padded every screen with plausible-sounding features that are **not in the spec and must not
be treated as real**: a fabricated "warehouse sync node" / "gateway sync" status system, a
"Direct Fulfillment SLA" card, per-line "In Stock (n)" inventory counts on the request form
(explicitly excluded — FR-006 is a one-tap signal, not an inventory reading), a pre-submission
"Pre-Approved Operational Budget" check (budget comparison in the real spec happens after
submission, FR-011), and a "View PO" action implying a purchase-order entity this release doesn't
have. Strip all of that before any of it becomes a Flutter task.

| File | Screen prompt |
|---|---|
| `login_first_sign_in.png` | R2.2-M1 |
| `biometrics_enable_prompt_bottom_sheet.png` + `biometrics_returning_device_unlock.png` | R2.2-M1b (generated as two separate states, cleaner than the single combined prompt asked for) |
| `home_branch_manager.png` | R2.2-M2 |
| `home_approver.png` | R2.2-M3 |
| `new_request.png` | R2.2-M4 |
| `low_stock_report_active.png` + `low_stock_report_success_queued_variants.png` | R2.2-M5 |
| `my_requests_list.png` + `my_requests_empty_state.png` | R2.2-M6 |
| `request_detail_decision.png` | R2.2-M6b |
| `settings.png` | R2.2-M7 |
| `procurepilot_logo.png` | app icon/logo Stitch generated alongside the screens, not part of the original prompt set |

Stitch also echoed back its own expanded `design.md` (full Material 3 tonal palette generated from
our seed colors) — not committed here; it shifted `primary` and `tertiary` from the hex values in
our authored DESIGN.md through MD3's tonal-palette algorithm, which is expected Stitch behavior,
not a defect, but means the *exact* hex values in the screenshots won't match our DESIGN.md
byte-for-byte. Our authored `r2.2-mobile-mvp-DESIGN.md` remains the source of truth for
implementation; these images are for layout/hierarchy/interaction reference.
