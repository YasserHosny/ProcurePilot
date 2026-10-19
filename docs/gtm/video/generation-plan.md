# Demo video — generation plan and edit decision lists

How the four cuts were produced on 2026-10-19, in enough detail to reproduce or change any of them.
Spec, style and storyboard decisions: [`README.md`](README.md). Status: [`production-tracker.md`](production-tracker.md).

## Materials

| Material | Where | In git |
|---|---|---|
| Screen recordings (9 clips, web 1920×1080, phone 390×844, H.264 30 fps) | `~/Videos/pp-recording/` on the recording machine | **Not yet**: several show the owner's email address (see Privacy) |
| Stills of every scene (3 per clip, email-free ones only) | [`screens/`](screens/) | yes |
| Card stills (each card at full opacity, taken from the v1 cuts) and the card HTML (Arabic, English, 16:9, 9:16) | [`cards/`](cards/) | yes |
| Logo sting, end card and outros (approved 2026-10-15) | [`renders/`](renders/) | yes |
| Music: Antalya Beaches by DayFox (Pixabay, 6.0 MB) | `music/` | no: licence; [`fetch-assets.sh`](fetch-assets.sh) downloads and checks it |
| Stock: Pexels 4253325 kitchen (16:9) and 31735802 chef at the grill (9:16) | `source/stock/` | no: licence; same script |
| Beat map of the track (334 beats) | [`music/antalya-beaches-beats.csv`](music/antalya-beaches-beats.csv) | yes |
| Recording scripts | [`source/record/`](source/record/) | yes |
| Edit scripts | v1 [`source/edit/`](source/edit/), v2 [`source/edit-v2/`](source/edit-v2/) | yes |
| Finished cuts (`procurepilot-demo-{ar,en}-{16x9,9x16-60s}.mp4`) | v1 `~/Videos/pp-recording/edit/`, v2 `~/Videos/pp-recording/edit/v2/`, shared with the owner | no |

`fetch-assets.sh` pins each third-party file by URL and SHA-256, so a rebuild uses byte-identical media.

## The recorded round (hosted, «مطاعم سند», 2026-10-19)

1. Phone: low-stock report, sunflower oil, Maadi, 1 tin left.
2. Web: RFQ 4503cd3c for 8 tins of oil, 12 sacks of rice and 80 kg of onions to النور, الأمانة and الحاج سيد, needed by 22/10.
3. Gmail (off camera): النور sends a PDF (rice 920, oil 1,635), الحاج سيد a PDF (onions 17.00) and الأمانة a WhatsApp photo of a printed quote covering all three items (oil 1,610, rice 910, onions 16.75; 25,140 ج.م).
4. Web: inbox → الأمانة's photo quote read correctly (lines, EGP, expiry 29/10, total reconciled) → authorised. The other two are authorised off camera.
5. Web: Smart Compare for oil ×8 recommends الأمانة (12,880 vs 13,080 landed, 1% margin).
6. The guardrail (≤ 30,000 EGP, ≥ 1 reply, ≤ 20% variance, default cost centre «المطبخ — المعادي») drafts request d1f10ff7 for EGP 25,140 from the photo quote with no human step, and the owner is emailed.
7. Web: draft opened (guardrail banner) → submitted. Phone: approved.
8. Web: PO-000006 from the approved request → sent → outcome recorded from the PO → saving 460 EGP against the last PO prices (oil +240, rice +180, onions +40).
9. The six pending savings (this round and the round-4 dry run) are verified as the owner → ledger total ١٬٠٦٠ ج.م.

## Recording method

- **Clean window:** Chrome with its own profile, `--kiosk --remote-debugging-port=9333` on the HDMI screen; the owner signs in once (Claude never types passwords).
- **Driving:** Playwright `connectOverCDP` scripts (`scene*.cjs`) with a drawn arrow pointer that glides 0.8 s to each control, human-paced typing (45–120 ms per key), 15 s step timeouts, the recorder always stopped in `finally`.
- **Capture:** GNOME Shell `ScreencastArea(3286, 0, 1920, 1080)` over D-Bus (`screencast.py`), 30 fps, OS pointer off.
- **Phone:** Flutter web build (`--dart-define DEFAULT_LOCALE=ar`, API proxied by `mobile_proxy.py` on :4310), emulated 390×844 by `phone-driver.cjs`, which keeps the CDP emulation alive and takes tap/type/record commands from a JSON file; a translucent circle marks taps.
- **Sidebar:** shown on the first app shot and the closing ledger; hidden elsewhere so the content gets the full width.

## Edit decision list — Arabic 3:00 (16:9)

Body 0:00–2:50.25, then `renders/outro-16x9.mp4` (9.75 s). Speeds = source span ÷ slot length.

| # | Slot (s) | Source | Source span (s) | Speed |
|---|---|---|---|---|
| 0 | 6.0 | stock kitchen (−5% brightness) | 0–6 | 1× |
| 1 | 3.2 | card 0 «عروض الأسعار على الواتساب… ونسخ يدوي في إكسل.» | — | — |
| 2 | 4.0 | stock kitchen | 22–26 | 1× |
| 3 | 3.2 | card 1 «إنت بتشتري كده كده — إحنا بنوريك بتوفّر قد إيه.» | — | — |
| 4 | 10.0 | `s0-phone-lowstock` in the phone frame | 1.5–22.5 | 2.1× |
| 5 | 3.2 | card 2 «طلب عرض سعر واحد… لكل الموردين مرة واحدة.» | — | — |
| 6 | 15.0 | `s1-rfq` | 2.5–47.0 | 3.0× |
| 7 | 3.2 | card 3 «العروض توصل وتتقري لوحدها بالجنيه المصري.» | — | — |
| 8 | 6.0 | `s2-quote-photo` (inbox → open) | 2.5–13.0 | 1.75× |
| 9 | 15.0 | `s2b-photo-closeup` | 1.0–22.0 | 1.4× |
| 10 | 7.0 | `s2-quote-photo` (confirm → authorise) | 18.0–32.5 | 2.1× |
| 11 | 3.2 | card 4 «مقارنة بند بند… والوفر قدامك.» | — | — |
| 12 | 14.0 | `s3c-smart-compare` | 2.5–31.5 | 2.1× |
| 13 | 14.0 | `s3-guardrail-draft` | 2.5–31.0 | 2.0× |
| 14 | 4.5 | notification card (real request: Maadi, oil, rice, onions, 25,140) | — | — |
| 15 | 3.2 | card 5 «المدير يوافق من موبايله.» | — | — |
| 16 | 12.0 | `s4-phone-approve` in the phone frame | 1.5–18.5 | 1.4× |
| 17 | 3.2 | card 6 «وأمر الشراء يطلع جاهز.» | — | — |
| 18 | 22.0 | `s5-po-savings` | 2.5–58.0 | 2.5× |
| 19 | 3.6 | savings counter → ٤٦٠ ج.م («وفّرت في الطلب ده») | — | — |
| 20 | 14.75 | `s6-savings-close` (verified ١٬٠٦٠ ج.م) | 1.5–21.3 | 1.3× |

Music: the track from 0:00 to 2:50.25 at −6.6 dB (the gain the outro mix uses, measured at the seam), 0.5 s fade-in, then the outro's own audio; limiter −3 dBFS before AAC 256 kb/s. Result −14.6 LUFS, peak −2.2 dBFS.

## Edit decision list — Arabic 60 s (9:16)

Body 0–51.34 s, then `renders/outro-9x16.mp4` (8.5 s, fast sting) → ends 0:59.85. Music from the track's 2:00.

| # | Slot (s) | Source | Treatment |
|---|---|---|---|
| 0 | 3.0 | stock chef at the grill | 1080×1920 |
| 1–2 | 3.2 + 3.2 | vertical cards 0, 1 | — |
| 3 | 8.0 | `s0-phone-lowstock` | phone scaled to 1080 wide, cropped to 1920 high |
| 4 | 3.2 | vertical card 3 | — |
| 5 | 8.0 | `s2b-photo-closeup` | crop 1080×1080 at x=620 (photo + fields), on navy |
| 6 | 6.0 | `s3c-smart-compare` | crop 1350×1080 at x=420, scaled to 1080 wide |
| 7 | 5.5 | `s3-guardrail-draft` | crop 1080×1080 at x=300 |
| 8 | 3.2 | vertical card 5 | — |
| 9 | 4.44 | `s4-phone-approve` | full height |
| 10 | 3.6 | vertical counter → ٤٦٠ | — |

−13.8 LUFS, peak −2.6 dBFS.

## English cuts

The same footage and timings. Cards come from `source/edit/make_en.py` (LTR, the bar grows from the left): "Quotes on WhatsApp… copied into Excel by hand.", "You’re buying anyway — we show you what you save.", "One request for quotes… to every supplier at once.", "Quotes arrive and read themselves in Egyptian pounds.", "Line-by-line comparison… and the saving in front of you.", "The manager approves from their phone.", "And the purchase order comes out ready.", notification "A purchase request needs your approval · Maadi branch · oil, rice, onions · EGP 25,140", counter "You saved on this order 460 EGP". Outros: `renders/outro-*-en.mp4`. The app screens stay Arabic.

## Rebuild

### v2 (current candidate)

`source/edit-v2/` rebuilds all four v2 cuts: `./rebuild.sh` from that folder. Inputs come from `paths.py`, each overridable by environment: `PP_RAW` (the raw clips), `PP_FFMPEG` (an ffmpeg 7 with libx264), `PP_VIDEO_DOCS` (this folder, after `./fetch-assets.sh`) and `PP_PYTHON` (a Python with numpy and Pillow built with Raqm, for Arabic shaping). Outputs, segment caches and proof frames land beside the scripts and are git-ignored. Per-cut edit decision lists, mask intervals and measurements: [`source/edit-v2/CHANGES.md`](source/edit-v2/CHANGES.md).

### v1

1. `./fetch-assets.sh` (music and stock, checked by SHA-256).
2. Record: start the kiosk window, sign in, run `source/record/scene*.cjs` (paths at the top of each script).
3. Cards: run each renderer on its own, for example `node source/edit/render_cards.cjs <boards dir> <frames dir>`, then the same for `render_cards_v.cjs`, `render_cards_en_.cjs` and `render_cards_env_.cjs`. A shell glob would pass the other renderers to the first as its arguments.
4. Bodies: `python source/edit/build*.py`; mux each with `source/edit/final.sh <body> <outro> <music start> <body length> <out> [w h]`.

The v1 scripts are kept as they ran: their first lines hard-code the recording machine's scratch, ffmpeg and stock paths. Edit those lines before running them elsewhere, or use v2.

## v2 (2026-10-19, after the Codex review)

Built by Codex from [`review-codex-2026-10-19.md`](review-codex-2026-10-19.md): the email is masked in every frame where it appears (opaque boxes applied at source resolution, 344 proof frames inspected); captions over the footage replace most full-screen cards, with «بيانات تجريبية · واجهة عربية» / "Demo data · Arabic interface" on each; the first product shot is at 3 s (16:9) and 1.5 s (9:16); decision moments get 1–2.5 s holds; 460 EGP is labelled as this order against last purchase-order prices and 1,060 EGP as the demo ledger including the dry run; the comparison is labelled as oil ×8; the vertical cut shows the sent PO and the recorded outcome before the counter. 16:9 runs 2:15, 9:16 runs 0:55; −14.1 LUFS. Not done: an s3b all-lines insert (captions were corrected instead), and the notification card is still illustrative.

### v2.1 (2026-10-19, evening)

- The phone low-stock scene was re-recorded after #195: it now starts from the home screen's «الإبلاغ عن انخفاض المخزون» button and the confirmation reads «الكمية المتبقية: ١ لتر». Source: `s0-phone-lowstock-v3` = take `s0b` (0–21 s, ends while sending) + `s0c` (the confirmation, 0.5–5 s). It filed one more real low-stock report (oil, Maadi, 1) in the demo tenant.
- Vertical shots that had become thin strips were recropped closer to the 972×1040 frame: comparison (880,590,790,470), guardrail draft (435,90,800,820), submit (435,480,800,520), ledger (630,290,800,620).
- −14.0 LUFS on all four cuts; durations unchanged.

## Privacy

The owner's email (`…+pp-owner@gmail.com`) is visible in `s2` / `s2b` (quote review «رُفع بواسطة» / «راجعه»), in `s3` (the request page) and in `s4` (phone approval «مقدم الطلب»), so it also appears in the four v1 cuts, which must not be posted. The v2 cuts mask it in every frame (see v2 above). The raw clips stay out of git until they are masked at source. Stills that show it are left out of `screens/`.

## Known on-camera rough edges

Raw numbers «30000.0000» (Smart Compare guardrail line, finding 34) and «300.000000» (record-outcome form); English unit labels ("litre", "kilogram", finding 32); month-first date in the request form's native date input; the requester shown as an email, not a name.
