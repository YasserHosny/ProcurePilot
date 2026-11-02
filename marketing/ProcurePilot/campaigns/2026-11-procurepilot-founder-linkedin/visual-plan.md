# Visual plan: ProcurePilot founder posts A-01 to A-06 (LinkedIn, Yasser's profile)

Status: **v1 rendered 2026-10-29** by `scripts/render-linkedin-launch.cjs` (A-01 carousel, A-02, A-03, A-04 thumbnail); A-05 and A-06 wait for Egypt screens. Awaiting Yasser (G-asset). Identity: **ProcurePilot sub-brand**
(`../docs/brand/README.md`, `ProcurePilot/design-system/`). Iron Systems appears only as the
maker line ("by Iron Systems"), never mixed into the palette.

## Rules every image follows

| Rule | Value |
|---|---|
| Size | 1080 × 1350 (feed, portrait); A-01 is a document carousel of 1080 × 1350 pages (PDF upload) |
| Colour | Paper `#F4F6F9` ground or Navy `#0B2545`; **Teal `#12A594` is the one accent** (the winning bar, the verified line); Teal text `#0C7A6E` for small text on light; Mist `#C9D6E3` for secondary |
| Type | Readex Pro for Arabic and English display; Noto Kufi Arabic tabular figures for money (as the app); Western digits in post images |
| Logo | Converge logo, small: `ProcurePilot/design-system/logo/procurepilot-horizontal.svg` (EN) / `procurepilot-arabic-horizontal.svg` (AR); `-dark` versions on Navy |
| Screens | Real screens with synthetic data, framed (browser or phone frame), cropped to the one area the post talks about; **"Demo data" / «بيانات تجريبية» chip on every screen** |
| Never | Old pre-Ledger screens (before 2026-10-24); "-SAR 0.00"-type display bugs; the owner's email |
| Versions | Egypt (Egyptian Arabic, EGP screens), Saudi (Gulf Arabic, SAR screens), English (SAR English screens until Egypt EN exists) |
| Files | `ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images/A-0N-{eg,sa,en}-….png`, HTML source in `source/` |

## Per post

| Post | Format | What it shows | Text on image | Screens (in `../docs/gtm/`) | Status of inputs |
|---|---|---|---|---|---|
| A-01 Cheapest quote | **Document carousel, 5 pages** | 1 hook · 2 two quotes, unit price per kilo · 3 the 50 kg order with delivery · 4 "the expensive one wins by 100" · 5 Smart Compare screen + "ProcurePilot compares pack for pack" | Headline MD-09 per market; worked numbers (labelled "example numbers") | Saudi/EN: `gcc/rounds/screens/ar/11-smart-compare.jpg`, `…/sa-en/11-smart-compare.jpg` | Egypt Smart Compare (EGP) **missing** |
| A-02 Saved or think you saved | Single image | Ledger crop: one calculated row, one verified row with the teal double rule | "Calculated ≠ Verified" · «محسوب ≠ معتمد» | Egypt: `demo-tenant/round-6/screens-pps63/03-ledger-verified.jpg`; Saudi: `gcc/rounds/screens/ar/20-ledger-verified.jpg`; EN: `gcc/rounds/screens/sa-en/20-ledger-verified.jpg` | Ready |
| A-03 What ProcurePilot is | Single image | Converge logo on Navy above one framed Smart Compare screen; four short lines (reads · compares · a person approves · verified saving) | Logo + four lines per language | as A-01 | Egypt screen missing (use logo-only version until it exists) |
| A-04 Demo video | **Video** + custom thumbnail | The approved v2.5 cut per market; thumbnail = the logo-turn frame with "In about two minutes" | — | Cuts: Egypt `v2.5/…-ar-16x9.mp4`, Saudi `gcc-sa-v2/…-sa-ar-16x9.mp4`, EN `v2.5/…-en-16x9.mp4` (in `../docs/gtm/video/cuts/`) | Ready |
| A-05 WhatsApp quotes | Single image | Photo quote beside the extracted lines with confidence scores; a small WhatsApp-style "photo" tag on the quote | "Keep WhatsApp." · «خليها واتساب.» (EG) / «خلّها واتساب.» (SA) | Saudi: `gcc/rounds/screens/ar/09-quote-lines-photo.jpg`; EN: `…/sa-en/09-quote-lines-photo.jpg` | Egypt screen missing |
| A-06 A person approves | Single image | Phone frame: approval detail with remaining budget, then "Request approved" | "A person decides." · «القرار لحد من فريقك.» (EG) / «القرار لشخص من فريقك.» (SA) | Saudi: `gcc/rounds/screens/ar/3-phone-approval-detail.jpg` + `14-phone-approved.jpg`; EN: `…/sa-en/13-phone-approval-detail.jpg` | Egypt screen missing |

## What the product team must capture (Egypt, «مطاعم سند», Ledger design, owner email masked)

1. Smart Compare with two offers, EGP (Arabic UI and English UI).
2. Quotation review: photo quote beside extracted lines (Arabic UI).
3. Phone approval detail with remaining budget, and "Request approved" (Arabic).

Until then, Egypt posts A-01, A-03, A-05 and A-06 wait, or use the Saudi screen in the Saudi version only.

## How they get made

Same method as the company images: HTML in the brand, rendered to PNG/PDF with Playwright (needs a one-time install
OK), checked for text fit and contrast, sent for review. Nothing is posted.
