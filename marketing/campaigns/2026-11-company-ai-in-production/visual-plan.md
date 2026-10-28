# Visual plan: Iron Systems company posts CP-01 to CP-04 (LinkedIn first)

Status: **v1 rendered 2026-10-29** by `scripts/render-linkedin-launch.cjs` (CP-01 to CP-04); awaiting Yasser (G-asset). Identity: **Iron Systems v3.3**
(`<workspace>/Branding/Identity-v3/README.md`; summary `knowledge/company/brand-identity.md`).

## Rules every image follows

| Rule | Value |
|---|---|
| Size | 1080 × 1350 (LinkedIn feed, portrait); Instagram reuses it; X and Facebook get a 1200 × 675 crop later |
| Colour | Iron Dark `#0B0F17` / Iron 2 `#111827` carry ~75%; **one** Power Orange `#F97316` accent per image; text Iron Light `#E2E8F0`; never white on orange |
| Type | Archivo Expanded 800 caps for the display line (orange only on its last word); Inter for English body; Readex Pro for Arabic (no letter-spacing, Western digits); "Iron Systems" and "ProcurePilot" stay in Latin script |
| Logo | Flat logo, small, bottom corner (`<workspace>/Branding/Identity-v3/logo/`); metal mark only on CP-01, once, at least 120 px, no glow |
| Elements | One or two per image: 3 px orange rule, //// slashes at 30°, angled corner, dot grid |
| Never | Robots, brains, sparkles, circuit traces, blue-purple gradients, stock AI imagery |
| Versions | EN and AR file per image (Arabic laid out right to left, not mirrored text) |
| Files | `campaigns/2026-11-company-ai-in-production/assets/drafts/images/CP-0N-{en,ar}-1080x1350.png`, plus the HTML source in `source/` |

## Per post

| Post | Format | What the image shows | Text on image (EN / AR) | Source assets |
|---|---|---|---|---|
| CP-01 Who we are | Single image | Shards background (website hero), metal mark, wordmark, tagline; 3 px orange rule | "AI THAT WORKS IN PRODUCTION." (orange: PRODUCTION.) · «ذكاء اصطناعي يعمل في بيئة الإنتاج.» + tagline small | `brand/iron-systems/hero-bg.jpg`, metal mark PNG |
| CP-02 AI where it helps | Single principle card (first of a "principles" series: later Problem first, Built to last) | Iron Dark card, //// slashes at 30°, large display line, short line under it | "AI WHERE IT HELPS." (orange: HELPS.) · «الذكاء الاصطناعي حيث يفيد.» / sub: "We test the value before we ship." · «نختبر القيمة قبل الإطلاق.» | Brand tokens only |
| CP-03 Built by us | **Video**: ProcurePilot v2.5 cut (already approved, ends with the Iron Systems band) + a custom thumbnail | Thumbnail: Iron Dark frame, "BUILT BY US." with a framed ProcurePilot screen (demo data chip). This is the one allowed maker frame where both identities meet | "BUILT BY US." · «من صنعنا.» + "Demo data" chip | `video-cuts-latest/` cuts in `../` (EN 16:9 for EN, Egyptian AR 16:9 for AR); screen: `../docs/gtm/gcc/rounds/screens/sa-en/11-smart-compare.jpg` |
| CP-04 Automation, a person decides | Single image, the brand's split composition | Left: grey grid of re-typed rows (raw); right: clean connected blocks; an orange shard on the 30° lean between them | "RE-TYPED DATA → CONNECTED SYSTEMS" · «بيانات تُكتب مرتين ← أنظمة مترابطة» | Brand tokens; no screenshots |

## How they get made

1. Each image is an HTML page in the brand (fonts from Google Fonts: Archivo, Inter, Readex Pro), rendered to PNG with
   Playwright, the same way the LinkedIn covers were made (`LinkedIn/company-page/v1.3-shards_2026-10-23/source/`).
   Playwright is a dev dependency of `marketing/` (`npm install`, then `npx playwright install chromium` once).
2. Claude renders, checks contrast and text fit, and sends the PNGs for review. Nothing is posted.
3. Changes go into a new version; approved images move to `assets/approved/`.
