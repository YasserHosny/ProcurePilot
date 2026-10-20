# ProcurePilot English v2.2 delivery

Built from the fresh English-interface recordings. No git commands were run. All successful writes stayed in this working directory. Creating `~/Videos/pp-recording/en/masked/` failed with “Read-only file system”; the render inputs are therefore the local `masked-en/` copies and symlinks. The requested external masked directory remains undelivered. Set `PP_MASK_DIR` to change the mask destination and render input location in a writable environment.

## Rebuild

Run `bash rebuild-en.sh`. The supplied ffmpeg and Python are used; Pillow/Raqm renders the English captions and savings-counter frames. The English EDL is `edl-en.py`; `build_en.py` swaps only opening slot 0. Existing English outros are preserved, including their intentional public contact information. The private owner Gmail address is the masking target.

## Measured exports

MP4 movie-header durations; full audio/video decode using ffmpeg; EBU R128 integrated loudness and true-peak measurement with `ebur128=peak=true`. No listening audit was performed. All outputs are H.264/yuv420p at 30 fps plus AAC stereo at 256 kbit/s.

| File | Resolution | Duration (s) | LUFS | dBTP | Full decode |
|---|---|---:|---:|---:|---|
| [procurepilot-demo-en-16x9-anim.mp4](procurepilot-demo-en-16x9-anim.mp4) | 1920×1080 | 119.450 | -13.8 | -1.3 | pass |
| [procurepilot-demo-en-9x16-60s-anim.mp4](procurepilot-demo-en-9x16-60s-anim.mp4) | 1080×1920 | 53.412 | -14.1 | -2.9 | pass |
| [procurepilot-demo-en-16x9-clip.mp4](procurepilot-demo-en-16x9-clip.mp4) | 1920×1080 | 119.450 | -13.8 | -1.3 | pass |
| [procurepilot-demo-en-9x16-60s-clip.mp4](procurepilot-demo-en-9x16-60s-clip.mp4) | 1080×1920 | 53.412 | -14.1 | -2.9 | pass |

Music retains the template approach: body −6.6 dB, 0.5 s fade-in, preserved outro audio, the inherited +1.1 dB landscape / +0 dB vertical finishing gain, and `alimiter=limit=0.7079:attack=0.5:release=50:level=false` (−3 dBFS threshold) before AAC. The measured encoded true peaks above include codec/limiter overshoot; they are not asserted to equal the limiter threshold.

## Editorial decisions

- New source spans and LTR crops were derived from the English recordings, rather than copied from the Arabic timings. The long request-page load (roughly 4–19 s of that source) is omitted.
- Action crops include the full Send RFQ, Confirm & Authorize, Submit Request, Approve, Create Purchase Order, Submit order and Save 3 outcomes controls. Busy tails are cut; no endpoint freeze is placed on a busy control. A very short button-response frame may remain at a cut.
- “Request approved” starts on the loaded empty queue with the “Request approved” toast at source 16.4 s. The review/action captions precede it.
- The comparison caption for eight tins starts at source 10.5 s, after the required quantity is eight. The earlier ten-tin state is omitted.
- PO-000007 is submitted in the landscape action passage; the vertical cut uses the completed submitted header. Recording outcomes navigates directly to the savings ledger in this new footage, so the completed-outcome evidence is taken from the new s6 recording.
- The low-stock confirmation crop includes the whole check icon and the 1 L result. Vertical evidence remains between the caption and lower safe area.
- Savings counter: 200 EGP; “This order vs last purchase-order prices”; “Demo data · oil +120 · rice +60 · onions +20”. The cumulative ledger is EGP 1,260 including the earlier rounds.

## Per-cut EDL and caption text

Zero-based slots. Crop is `(x,y,w,h)` in the new masked source. All caption panels disclose **Demo data**. Source end is exclusive; output windows below are nominal 30 fps edit positions. Freeze is included in the slot duration.

### procurepilot-demo-en-16x9-anim.mp4

| Slot | Output window | Source | Source span | Duration / freeze | Crop | Caption |
|---:|---|---|---|---|---|---|
| 0 | 0.000–5.000 | open-anim-16x9 | 0.000000–5.000000 | 5.000 / 0.000 | full canvas | Quotes on WhatsApp. Still copying by hand? |
| 1 | 5.000–12.500 | s0-phone-lowstock | 3.200000–21.300000 | 7.500 / 0.000 | (0, 0, 390, 410) | Report low stock from the phone |
| 2 | 12.500–15.500 | s0-phone-lowstock | 22.300000–24.000000 | 3.000 / 1.300 | (0, 335, 390, 285) | Report low stock from the phone |
| 3 | 15.500–18.000 | s1-rfq | 4.500000–6.000000 | 2.500 / 0.000 | (670, 90, 820, 660) | One RFQ for all suppliers |
| 4 | 18.000–30.000 | s1-rfq | 6.000000–37.800000 | 12.000 / 0.000 | (670, 90, 820, 920) | One RFQ for all suppliers |
| 5 | 30.000–32.200 | s1-rfq | 41.200000–42.066667 | 2.200 / 0.000 | (670, 170, 820, 900) | One RFQ for all suppliers |
| 6 | 32.200–33.700 | s2-quote-photo | 2.500000–4.100000 | 1.500 / 0.000 | (230, 110, 1440, 700) | A quote photo → extraction, then human review |
| 7 | 33.700–38.200 | s2b-photo-closeup | 4.500000–8.000000 | 4.500 / 1.000 | (230, 64, 1450, 1000) | A quote photo → extraction, then human review |
| 8 | 38.200–42.200 | s2b-photo-closeup | 8.000000–10.000000 | 4.000 / 2.000 | (960, 180, 720, 425) | EGP 24,940 · extracted total reconciles |
| 9 | 42.200–46.200 | s2b-photo-closeup | 11.000000–14.000000 | 4.000 / 1.000 | (960, 615, 720, 440) | Oil, rice, onions · review before authorising |
| 10 | 46.200–47.200 | s2-quote-photo | 25.300000–26.200000 | 1.000 / 0.000 | (230, 400, 1450, 680) | Human review → authorise quote |
| 11 | 47.200–48.400 | s2-quote-photo | 27.600000–28.350000 | 1.200 / 0.000 | (230, 400, 1450, 680) | Human review → authorise quote |
| 12 | 48.400–53.400 | s3c-smart-compare | 10.500000–13.500000 | 5.000 / 2.000 | (250, 100, 1420, 950) | Compare oil offers · 8 tins |
| 13 | 53.400–58.400 | s3c-smart-compare | 14.000000–17.000000 | 5.000 / 2.000 | (250, 560, 1420, 480) | Oil ×8 · EGP 12,760 vs 12,960 |
| 14 | 58.400–62.400 | s3-guardrail-draft | 20.000000–22.000000 | 4.000 / 2.000 | (680, 90, 820, 300) | Guardrails draft the request · manager decides |
| 15 | 62.400–68.400 | s3-guardrail-draft | 28.000000–35.366667 | 6.000 / 0.000 | (680, 90, 820, 920) | Review the draft, then submit for approval |
| 16 | 68.400–72.400 | s4-phone-approve | 7.600000–11.800000 | 4.000 / 0.000 | (0, 65, 390, 520) | Manager reviews and approves on the phone |
| 17 | 72.400–74.900 | s4-phone-approve | 11.800000–12.400000 | 2.500 / 0.000 | (0, 580, 390, 264) | Approve the request |
| 18 | 74.900–78.400 | s4-phone-approve | 16.400000–18.000000 | 3.500 / 1.900 | (0, 380, 390, 464) | Request approved |
| 19 | 78.400–83.400 | s5-po-savings | 7.500000–19.900000 | 5.000 / 0.000 | (350, 90, 1220, 950) | Approved request → purchase order |
| 20 | 83.400–85.200 | s5-po-savings | 19.900000–20.566667 | 1.800 / 0.000 | (350, 160, 1220, 920) | Approved request → purchase order |
| 21 | 85.200–86.200 | s5-po-savings | 24.700000–25.066667 | 1.000 / 0.000 | (350, 90, 1220, 950) | Approved request → purchase order |
| 22 | 86.200–90.200 | s5-po-savings | 28.800000–30.800000 | 4.000 / 2.000 | (350, 90, 1220, 950) | PO-000007 · purchase order submitted |
| 23 | 90.200–94.200 | s5-po-savings | 33.300000–39.800000 | 4.000 / 0.000 | (30, 150, 1120, 650) | Record the outcome from the purchase order |
| 24 | 94.200–95.200 | s5-po-savings | 39.800000–40.566667 | 1.000 / 0.000 | (30, 150, 1120, 650) | Record the outcome from the purchase order |
| 25 | 95.200–98.200 | s6-savings-close | 0.400000–2.000000 | 3.000 / 1.400 | (475, 280, 800, 620) | Record the outcome from the purchase order |
| 26 | 98.200–103.200 | counter | 0.000000–1.000000 | 5.000 / 0.000 | full canvas | 200 EGP savings counter |
| 27 | 103.200–109.700 | s6-savings-close | 7.000000–11.000000 | 6.500 / 2.500 | (475, 280, 1000, 740) | EGP 1,260 · demo ledger, including earlier rounds |
| Outro | 109.700–119.450 | Preserved English outro | whole | original | full canvas | original English brand / CTA |

### procurepilot-demo-en-16x9-clip.mp4

| Slot | Output window | Source | Source span | Duration / freeze | Crop | Caption |
|---:|---|---|---|---|---|---|
| 0 | 0.000–5.000 | open-clip-16x9 | 0.000000–5.000000 | 5.000 / 0.000 | full canvas | Quotes on WhatsApp. Still copying by hand? |
| 1 | 5.000–12.500 | s0-phone-lowstock | 3.200000–21.300000 | 7.500 / 0.000 | (0, 0, 390, 410) | Report low stock from the phone |
| 2 | 12.500–15.500 | s0-phone-lowstock | 22.300000–24.000000 | 3.000 / 1.300 | (0, 335, 390, 285) | Report low stock from the phone |
| 3 | 15.500–18.000 | s1-rfq | 4.500000–6.000000 | 2.500 / 0.000 | (670, 90, 820, 660) | One RFQ for all suppliers |
| 4 | 18.000–30.000 | s1-rfq | 6.000000–37.800000 | 12.000 / 0.000 | (670, 90, 820, 920) | One RFQ for all suppliers |
| 5 | 30.000–32.200 | s1-rfq | 41.200000–42.066667 | 2.200 / 0.000 | (670, 170, 820, 900) | One RFQ for all suppliers |
| 6 | 32.200–33.700 | s2-quote-photo | 2.500000–4.100000 | 1.500 / 0.000 | (230, 110, 1440, 700) | A quote photo → extraction, then human review |
| 7 | 33.700–38.200 | s2b-photo-closeup | 4.500000–8.000000 | 4.500 / 1.000 | (230, 64, 1450, 1000) | A quote photo → extraction, then human review |
| 8 | 38.200–42.200 | s2b-photo-closeup | 8.000000–10.000000 | 4.000 / 2.000 | (960, 180, 720, 425) | EGP 24,940 · extracted total reconciles |
| 9 | 42.200–46.200 | s2b-photo-closeup | 11.000000–14.000000 | 4.000 / 1.000 | (960, 615, 720, 440) | Oil, rice, onions · review before authorising |
| 10 | 46.200–47.200 | s2-quote-photo | 25.300000–26.200000 | 1.000 / 0.000 | (230, 400, 1450, 680) | Human review → authorise quote |
| 11 | 47.200–48.400 | s2-quote-photo | 27.600000–28.350000 | 1.200 / 0.000 | (230, 400, 1450, 680) | Human review → authorise quote |
| 12 | 48.400–53.400 | s3c-smart-compare | 10.500000–13.500000 | 5.000 / 2.000 | (250, 100, 1420, 950) | Compare oil offers · 8 tins |
| 13 | 53.400–58.400 | s3c-smart-compare | 14.000000–17.000000 | 5.000 / 2.000 | (250, 560, 1420, 480) | Oil ×8 · EGP 12,760 vs 12,960 |
| 14 | 58.400–62.400 | s3-guardrail-draft | 20.000000–22.000000 | 4.000 / 2.000 | (680, 90, 820, 300) | Guardrails draft the request · manager decides |
| 15 | 62.400–68.400 | s3-guardrail-draft | 28.000000–35.366667 | 6.000 / 0.000 | (680, 90, 820, 920) | Review the draft, then submit for approval |
| 16 | 68.400–72.400 | s4-phone-approve | 7.600000–11.800000 | 4.000 / 0.000 | (0, 65, 390, 520) | Manager reviews and approves on the phone |
| 17 | 72.400–74.900 | s4-phone-approve | 11.800000–12.400000 | 2.500 / 0.000 | (0, 580, 390, 264) | Approve the request |
| 18 | 74.900–78.400 | s4-phone-approve | 16.400000–18.000000 | 3.500 / 1.900 | (0, 380, 390, 464) | Request approved |
| 19 | 78.400–83.400 | s5-po-savings | 7.500000–19.900000 | 5.000 / 0.000 | (350, 90, 1220, 950) | Approved request → purchase order |
| 20 | 83.400–85.200 | s5-po-savings | 19.900000–20.566667 | 1.800 / 0.000 | (350, 160, 1220, 920) | Approved request → purchase order |
| 21 | 85.200–86.200 | s5-po-savings | 24.700000–25.066667 | 1.000 / 0.000 | (350, 90, 1220, 950) | Approved request → purchase order |
| 22 | 86.200–90.200 | s5-po-savings | 28.800000–30.800000 | 4.000 / 2.000 | (350, 90, 1220, 950) | PO-000007 · purchase order submitted |
| 23 | 90.200–94.200 | s5-po-savings | 33.300000–39.800000 | 4.000 / 0.000 | (30, 150, 1120, 650) | Record the outcome from the purchase order |
| 24 | 94.200–95.200 | s5-po-savings | 39.800000–40.566667 | 1.000 / 0.000 | (30, 150, 1120, 650) | Record the outcome from the purchase order |
| 25 | 95.200–98.200 | s6-savings-close | 0.400000–2.000000 | 3.000 / 1.400 | (475, 280, 800, 620) | Record the outcome from the purchase order |
| 26 | 98.200–103.200 | counter | 0.000000–1.000000 | 5.000 / 0.000 | full canvas | 200 EGP savings counter |
| 27 | 103.200–109.700 | s6-savings-close | 7.000000–11.000000 | 6.500 / 2.500 | (475, 280, 1000, 740) | EGP 1,260 · demo ledger, including earlier rounds |
| Outro | 109.700–119.450 | Preserved English outro | whole | original | full canvas | original English brand / CTA |

### procurepilot-demo-en-9x16-60s-anim.mp4

| Slot | Output window | Source | Source span | Duration / freeze | Crop | Caption |
|---:|---|---|---|---|---|---|
| 0 | 0.000–3.100 | open-anim-9x16 | 0.000000–3.100000 | 3.100 / 0.000 | full canvas | Quotes on WhatsApp. Still copying by hand? |
| 1 | 3.100–6.100 | s0-phone-lowstock | 3.200000–18.000000 | 3.000 / 0.000 | (0, 0, 390, 410) | Report low stock from the phone |
| 2 | 6.100–7.900 | s0-phone-lowstock | 19.000000–21.300000 | 1.800 / 0.000 | (0, 65, 390, 315) | Report low stock from the phone |
| 3 | 7.900–9.900 | s0-phone-lowstock | 22.300000–23.300000 | 2.000 / 1.000 | (0, 335, 390, 285) | Report low stock from the phone |
| 4 | 9.900–12.400 | s1-rfq | 33.000000–36.500000 | 2.500 / 0.000 | (680, 170, 800, 860) | One RFQ for all suppliers |
| 5 | 12.400–14.900 | s2b-photo-closeup | 4.500000–6.000000 | 2.500 / 1.000 | (240, 150, 690, 610) | A quote photo → extraction, then human review |
| 6 | 14.900–17.400 | s2b-photo-closeup | 8.000000–9.000000 | 2.500 / 1.500 | (965, 180, 710, 425) | EGP 24,940 · extracted total reconciles |
| 7 | 17.400–20.900 | s3c-smart-compare | 14.000000–16.000000 | 3.500 / 1.500 | (250, 860, 720, 185) | Oil ×8 · EGP 12,760 vs 12,960 |
| 8 | 20.900–23.900 | s3-guardrail-draft | 20.000000–21.500000 | 3.000 / 1.500 | (680, 90, 820, 880) | Guardrails draft the request · manager decides |
| 9 | 23.900–25.400 | s3-guardrail-draft | 34.400000–35.366667 | 1.500 / 0.000 | (680, 720, 820, 270) | Review the draft, then submit for approval |
| 10 | 25.400–27.900 | s4-phone-approve | 8.000000–9.500000 | 2.500 / 1.000 | (0, 65, 390, 295) | Manager reviews and approves on the phone |
| 11 | 27.900–29.400 | s4-phone-approve | 11.800000–12.400000 | 1.500 / 0.000 | (0, 580, 390, 264) | Approve the request |
| 12 | 29.400–31.900 | s4-phone-approve | 16.400000–17.400000 | 2.500 / 1.500 | (0, 380, 390, 464) | Request approved |
| 13 | 31.900–34.400 | s5-po-savings | 28.800000–30.300000 | 2.500 / 1.000 | (350, 120, 1210, 195) | PO-000007 · purchase order submitted |
| 14 | 34.400–35.900 | s5-po-savings | 39.800000–40.566667 | 1.500 / 0.000 | (700, 600, 450, 200) | Record the outcome from the purchase order |
| 15 | 35.900–38.400 | s6-savings-close | 0.400000–1.400000 | 2.500 / 1.500 | (490, 355, 780, 285) | Record the outcome from the purchase order |
| 16 | 38.400–41.900 | counter | 0.000000–1.000000 | 3.500 / 0.000 | full canvas | 200 EGP savings counter |
| 17 | 41.900–44.900 | s6-savings-close | 7.000000–8.000000 | 3.000 / 2.000 | (490, 350, 780, 290) | EGP 1,260 · demo ledger, including earlier rounds |
| Outro | 44.900–53.412 | Preserved English outro | whole | original | full canvas | original English brand / CTA |

### procurepilot-demo-en-9x16-60s-clip.mp4

| Slot | Output window | Source | Source span | Duration / freeze | Crop | Caption |
|---:|---|---|---|---|---|---|
| 0 | 0.000–3.100 | open-clip-9x16 | 0.000000–3.100000 | 3.100 / 0.000 | full canvas | Quotes on WhatsApp. Still copying by hand? |
| 1 | 3.100–6.100 | s0-phone-lowstock | 3.200000–18.000000 | 3.000 / 0.000 | (0, 0, 390, 410) | Report low stock from the phone |
| 2 | 6.100–7.900 | s0-phone-lowstock | 19.000000–21.300000 | 1.800 / 0.000 | (0, 65, 390, 315) | Report low stock from the phone |
| 3 | 7.900–9.900 | s0-phone-lowstock | 22.300000–23.300000 | 2.000 / 1.000 | (0, 335, 390, 285) | Report low stock from the phone |
| 4 | 9.900–12.400 | s1-rfq | 33.000000–36.500000 | 2.500 / 0.000 | (680, 170, 800, 860) | One RFQ for all suppliers |
| 5 | 12.400–14.900 | s2b-photo-closeup | 4.500000–6.000000 | 2.500 / 1.000 | (240, 150, 690, 610) | A quote photo → extraction, then human review |
| 6 | 14.900–17.400 | s2b-photo-closeup | 8.000000–9.000000 | 2.500 / 1.500 | (965, 180, 710, 425) | EGP 24,940 · extracted total reconciles |
| 7 | 17.400–20.900 | s3c-smart-compare | 14.000000–16.000000 | 3.500 / 1.500 | (250, 860, 720, 185) | Oil ×8 · EGP 12,760 vs 12,960 |
| 8 | 20.900–23.900 | s3-guardrail-draft | 20.000000–21.500000 | 3.000 / 1.500 | (680, 90, 820, 880) | Guardrails draft the request · manager decides |
| 9 | 23.900–25.400 | s3-guardrail-draft | 34.400000–35.366667 | 1.500 / 0.000 | (680, 720, 820, 270) | Review the draft, then submit for approval |
| 10 | 25.400–27.900 | s4-phone-approve | 8.000000–9.500000 | 2.500 / 1.000 | (0, 65, 390, 295) | Manager reviews and approves on the phone |
| 11 | 27.900–29.400 | s4-phone-approve | 11.800000–12.400000 | 1.500 / 0.000 | (0, 580, 390, 264) | Approve the request |
| 12 | 29.400–31.900 | s4-phone-approve | 16.400000–17.400000 | 2.500 / 1.500 | (0, 380, 390, 464) | Request approved |
| 13 | 31.900–34.400 | s5-po-savings | 28.800000–30.300000 | 2.500 / 1.000 | (350, 120, 1210, 195) | PO-000007 · purchase order submitted |
| 14 | 34.400–35.900 | s5-po-savings | 39.800000–40.566667 | 1.500 / 0.000 | (700, 600, 450, 200) | Record the outcome from the purchase order |
| 15 | 35.900–38.400 | s6-savings-close | 0.400000–1.400000 | 2.500 / 1.500 | (490, 355, 780, 285) | Record the outcome from the purchase order |
| 16 | 38.400–41.900 | counter | 0.000000–1.000000 | 3.500 / 0.000 | full canvas | 200 EGP savings counter |
| 17 | 41.900–44.900 | s6-savings-close | 7.000000–8.000000 | 3.000 / 2.000 | (490, 350, 780, 290) | EGP 1,260 · demo ledger, including earlier rounds |
| Outro | 44.900–53.412 | Preserved English outro | whole | original | full canvas | original English brand / CTA |

## Masking and exact ranges

English glyph templates were cut from the newly recorded quote Information panel and checked against every web-source frame in the relevant information-column region. Every matched email box receives a five-frame halo. Neighbouring boxes are unioned during scrolls; conservative fixed full-column windows cover the observed scroll/transition periods independently of detection. These deliberately overmask some adjacent content during transitions. Phone queue and detail requester text use full-width fixed masks, with substantial time margins, so the horizontal transition cannot expose either requester rendering. Opaque white is used for web Information panels; `#fff7ff` matches the phone background. H.264 CRF 12 masked copies are produced before any crop, speed change or freeze.

The English request recording’s loaded edit form has branch, cost centre, required date, lines, total, budget and submission controls; no requester/email line was visible in the inspected form or request-list frames. It is a symlink, as are the other sources with no observed email. The detector only recognises the sampled English bold quote glyphs; it is not presented as universal OCR. The independent phone windows and visual inspections are necessary.

| Source | Decoded frames | Copy treatment |
|---|---:|---|
| s0-phone-lowstock | 871 | symlink to English raw source |
| s1-rfq | 1366 | symlink to English raw source |
| s2-quote-photo | 997 | opaque masks, re-encoded |
| s2b-photo-closeup | 512 | opaque masks, re-encoded |
| s3-guardrail-draft | 1249 | symlink to English raw source |
| s3c-smart-compare | 995 | symlink to English raw source |
| s4-phone-approve | 578 | opaque masks, re-encoded |
| s5-po-savings | 1438 | symlink to English raw source |
| s6-savings-close | 534 | symlink to English raw source |

### s2-quote-photo — mask windows

Ranges below are exact filter enable windows `[start,end)` in seconds; windows extending past EOF are truncated by the source. Overlapping rectangles are intentional. These are mask coverage windows, not an assertion that the email is visible for their whole duration.

| Start | End | x | y | w | h | Colour |
|---:|---:|---:|---:|---:|---:|---|
| 7.000000 | 8.100000 | 970 | 64 | 160 | 1016 | white |
| 23.500000 | 25.800000 | 970 | 64 | 160 | 1016 | white |
| 30.600000 | 32.800000 | 970 | 64 | 160 | 1016 | white |
| 23.900000 | 25.166667 | 970 | 612 | 160 | 42 | white |
| 25.166667 | 33.233333 | 970 | 612 | 160 | 103 | white |
| 23.566667 | 23.900000 | 970 | 612 | 160 | 303 | white |
| 21.566667 | 23.566667 | 970 | 873 | 160 | 42 | white |
| 21.233333 | 21.566667 | 970 | 873 | 160 | 95 | white |
| 6.400000 | 21.233333 | 970 | 926 | 160 | 42 | white |

### s2b-photo-closeup — mask windows

Ranges below are exact filter enable windows `[start,end)` in seconds; windows extending past EOF are truncated by the source. Overlapping rectangles are intentional. These are mask coverage windows, not an assertion that the email is visible for their whole duration.

| Start | End | x | y | w | h | Colour |
|---:|---:|---:|---:|---:|---:|---|
| 15.800000 | 16.100000 | 970 | 64 | 160 | 40 | white |
| 15.733333 | 15.800000 | 970 | 64 | 160 | 58 | white |
| 15.633333 | 15.733333 | 970 | 64 | 160 | 67 | white |
| 15.500000 | 15.633333 | 970 | 64 | 160 | 86 | white |
| 15.466667 | 15.500000 | 970 | 64 | 160 | 87 | white |
| 1.700000 | 4.300000 | 970 | 64 | 160 | 1016 | white |
| 15.500000 | 17.200000 | 970 | 64 | 160 | 1016 | white |
| 15.400000 | 15.466667 | 970 | 80 | 160 | 71 | white |
| 15.300000 | 15.400000 | 970 | 89 | 160 | 64 | white |
| 15.166667 | 15.300000 | 970 | 108 | 160 | 45 | white |
| 15.066667 | 15.166667 | 970 | 109 | 160 | 44 | white |
| 3.966667 | 15.066667 | 970 | 111 | 160 | 42 | white |
| 3.933333 | 3.966667 | 970 | 111 | 160 | 44 | white |
| 3.766667 | 3.933333 | 970 | 111 | 160 | 62 | white |
| 3.700000 | 3.766667 | 970 | 111 | 160 | 95 | white |
| 3.633333 | 3.700000 | 970 | 111 | 160 | 136 | white |
| 3.600000 | 3.633333 | 970 | 113 | 160 | 134 | white |
| 3.500000 | 3.600000 | 970 | 131 | 160 | 116 | white |
| 3.433333 | 3.500000 | 970 | 131 | 160 | 155 | white |
| 3.400000 | 3.433333 | 970 | 164 | 160 | 122 | white |
| 3.366667 | 3.400000 | 970 | 164 | 160 | 202 | white |
| 3.233333 | 3.366667 | 970 | 205 | 160 | 161 | white |
| 3.166667 | 3.233333 | 970 | 205 | 160 | 188 | white |
| 3.133333 | 3.166667 | 970 | 244 | 160 | 178 | white |
| 3.066667 | 3.133333 | 970 | 244 | 160 | 325 | white |
| 2.933333 | 3.066667 | 970 | 324 | 160 | 245 | white |
| 2.900000 | 2.933333 | 970 | 324 | 160 | 292 | white |
| 2.833333 | 2.900000 | 970 | 351 | 160 | 265 | white |
| 2.800000 | 2.833333 | 970 | 380 | 160 | 236 | white |
| 2.600000 | 2.800000 | 970 | 527 | 160 | 265 | white |
| 2.566667 | 2.600000 | 970 | 574 | 160 | 226 | white |
| 2.500000 | 2.566667 | 970 | 574 | 160 | 242 | white |
| 2.466667 | 2.500000 | 970 | 574 | 160 | 308 | white |
| 2.333333 | 2.466667 | 970 | 750 | 160 | 132 | white |
| 2.300000 | 2.333333 | 970 | 750 | 160 | 153 | white |
| 2.266667 | 2.300000 | 970 | 750 | 160 | 158 | white |
| 2.233333 | 2.266667 | 970 | 758 | 160 | 150 | white |
| 2.166667 | 2.233333 | 970 | 774 | 160 | 159 | white |
| 2.100000 | 2.166667 | 970 | 840 | 160 | 103 | white |
| 2.033333 | 2.100000 | 970 | 840 | 160 | 110 | white |
| 2.000000 | 2.033333 | 970 | 840 | 160 | 120 | white |
| 1.966667 | 2.000000 | 970 | 861 | 160 | 99 | white |
| 1.933333 | 1.966667 | 970 | 866 | 160 | 96 | white |
| 1.900000 | 1.933333 | 970 | 866 | 160 | 99 | white |
| 1.833333 | 1.900000 | 970 | 891 | 160 | 75 | white |
| 1.800000 | 1.833333 | 970 | 901 | 160 | 65 | white |
| 1.766667 | 1.800000 | 970 | 901 | 160 | 67 | white |
| 1.700000 | 1.766667 | 970 | 908 | 160 | 60 | white |
| 1.633333 | 1.700000 | 970 | 918 | 160 | 50 | white |
| 1.600000 | 1.633333 | 970 | 920 | 160 | 48 | white |
| 1.566667 | 1.600000 | 970 | 923 | 160 | 45 | white |
| 1.466667 | 1.566667 | 970 | 924 | 160 | 44 | white |
| 0.000000 | 1.466667 | 970 | 926 | 160 | 42 | white |

### s4-phone-approve — mask windows

Ranges below are exact filter enable windows `[start,end)` in seconds; windows extending past EOF are truncated by the source. Overlapping rectangles are intentional. These are mask coverage windows, not an assertion that the email is visible for their whole duration.

| Start | End | x | y | w | h | Colour |
|---:|---:|---:|---:|---:|---:|---|
| 4.000000 | 7.500000 | 0 | 57 | 390 | 59 | 0xfff7ff |
| 6.500000 | 16.500000 | 0 | 225 | 390 | 35 | 0xfff7ff |

## Executed QA and inspection scope

1. Viewed all 15 raw-source overview sheets in `qa-en/source/` (one native source frame per second, labelled at half-second sampling points). These establish the fresh story, English layout, long waits, prices and scroll positions. Native source frames separately opened: s2b 5.5 s; s2 8.5 and 32.5 s; s3 0.5 and 19.5 s; s4 5.5 and 9.5 s; Smart Compare 14.5 s; s5 29.5 and 39.5 s; RFQ 42.5 s; low stock 20.5, 21.5 and 23.5 s.
2. Viewed the eight source action-detail sheets `boundary-source-0` through `7`, the earlier RFQ action sheet, and native-resolution `low-exact.jpg` / `authorise-exact.jpg`. These identify the click/disabled boundaries used in the EDL. The small detail crops in those sheets are diagnostic; full output action PNGs retain the complete target and surrounding output frame.
3. Viewed all ten native privacy comparison sheets (`*-native-*.png`): raw and masked regions at original pixel scale through the quote appearances, scrolls, reviewed-by panel and phone queue/detail transitions. Full-resolution raw/masked proof frames for every sampled position are retained alongside them; sample times are in `qa-en/privacy/proof-times.json`. Native full frames separately opened include masked s2 at 6.6, 7.5, 24.5 and 32.5 s and masked s2b at 0 s.
4. Viewed each final cut’s two-second contact sheets, primary-action before/after sheets and privacy sheets. Additional native-resolution final proof frames and crop-repair frames are listed in `qa-en/INSPECTED.md`. These visual checks are sampled; they are not a claim to have watched every encoded frame. The compact action sheets enumerate the principal procurement actions (10 landscape / 4 vertical). To cover field-focus and dropdown clicks as well, `all-click-frame-pairs/` provides every adjacent decoded frame pair throughout all retained interactive passages, including native-resolution JPEGs and an output-frame manifest. Those exhaustive pair pages were generated; only the pages explicitly listed in INSPECTED.md were visually reviewed.
5. `audit_masked_en.py` decoded every masked/symlinked English source frame: zero matches for the English quote email template and zero nonuniform phone mask interior frames. Results: `qa-en/privacy/masked-audit.json`.
6. `verify_en_outputs.py` decoded every output frame and checked the projected interiors of active masks away from enable-window edges. Edge/transition cases are represented by the native privacy proofs. Results:

| Cut | Frames decoded | Frames with mask interiors checked | Failed mask patches |
|---|---:|---:|---:|
| procurepilot-demo-en-16x9-anim | 3583 | 321 | 0 |
| procurepilot-demo-en-16x9-clip | 3583 | 321 | 0 |
| procurepilot-demo-en-9x16-60s-anim | 1602 | 75 | 0 |
| procurepilot-demo-en-9x16-60s-clip | 1602 | 75 | 0 |

No readable private owner email was found in the inspected masked/output samples. That statement is limited to the visual samples and automated checks described above. The raw comparison proof files intentionally contain the original private email and should not be published. No assertion is made that unrelated public contact text in the preserved outro was removed.

## QA artefact index

- `qa-en/<cut>/contact-*.jpg`: exact output frames 0, 2, 4… seconds (selected every 60th decoded frame).
- `qa-en/<cut>/action-boundaries.jpg`, `action-*-before.png`, `action-*-after.png`, `actions.json`: full-frame primary action evidence, with source/output mapping.
- `qa-en/<cut>/all-click-frame-pairs/`: every adjacent frame pair in interactive passages, plus full-resolution frames and exact output-frame mapping. Both opening variants have the same body positions and share this evidence directory.
- `qa-en/<cut>/source-click-frames/`: native masked-source frames before/after the primary clicks, including the immediate button response deliberately removed from the finished edit.
- `qa-en/<cut>/privacy-sheet.jpg`, `privacy-slot-*.png`, `privacy-samples.json`: full-resolution encoded-output privacy samples at slot entry, midpoint, moving endpoint and hold endpoint.
- `qa-en/privacy/*-raw.png`, `*-masked.png`, `*-native-*.png`, mask filter files, JSON manifests and audit results.
- `qa-en/<cut>/decode-loudness.log`: executed full-decode and audio measurement log.

## SHA-256

- `procurepilot-demo-en-16x9-anim.mp4`: `77300d245349f156422e2706e37f94bd7d37b070cddeb500afc4ebc7d5cfd57c`
- `procurepilot-demo-en-9x16-60s-anim.mp4`: `e26d5b912d545cf7812367d90fe283361e0203f83e52158c0b73f8d82841d77b`
- `procurepilot-demo-en-16x9-clip.mp4`: `e8423c9e1f41e0d7ff05a704ddd981f047ab5d74e1f20d5c52514e655f0ddbb2`
- `procurepilot-demo-en-9x16-60s-clip.mp4`: `4aa78454fefee099a79ce482b721bc64be6858da072dc7b964524ade69ad55f2`
