# ProcurePilot demo v2

All new files are under `edit/v2/`. No commits or git commands were made. Original sources, v1 scripts, raw recordings and original outros were read only. Copies of the reference scripts are in `reference/`.

## Changes and rebuild

- P1: opaque source-resolution identity masks, applied before crop/scale/setpts. The raw scan checks every encoded frame using visually inspected glyph templates, with actual `showinfo` source timestamps. `analysis/raw-email-audit.json` records detections; `analysis/mask-coverage.json` joins every detection in the EDL to its mask or excluded crop. Phone compact-list identity is checked separately and that layout is omitted.
- P2: 460 EGP explicitly means this order versus last purchase-order prices; the 1,060 EGP ledger explicitly includes the earlier demo dry run. Counter animates for one second, then holds the final number for four seconds in landscape / three seconds in vertical.
- P3: comparison is labelled oil ×8, rather than claiming that Smart Compare displays every RFQ line. The 12,880 vs 13,080 supplier comparison is separate from historical-baseline savings.
- P4: first product shot at 3.00 s in landscape and 1.50 s in vertical. Most cards replaced by captions. Repeated typing/loading condensed; extracted total, recommendation, guardrail, approval, sent PO and ledger receive readable holds. The unrelated old request at the start of s3 is omitted. Illustrative notification card is removed.
- P5: successive vertical views show the quote photo, extracted fields, recommendation, guardrail, submit control, phone approval, sent PO, outcome and ledger total. Active UI is fitted inside y=475..1515 and body captions start at y=275; key text avoids top 250 / bottom 350. Original outros remain as supplied.
- English callouts translate the evidence and identify the interface as Arabic; body captions disclose demo data.
- All cuts: 30 fps H.264, yuv420p, AAC 256 kb/s; same DayFox track, body gain -6.6 dB, 0.5 s fade-in, preserved outro mix, -3 dBFS limiter before AAC. Landscape music starts at 0:00; vertical at 2:00. The measured landscape pre-calibration export was -15.15 LUFS; a common +1.1 dB trim is applied to the joined body and outro before the -3 dBFS limiter. This retains their relative gain match while approaching -14 LUFS. Vertical common trim is 0 dB. Video packets are copied from the encoded body and original outro, avoiding a second video encode.

Run `./rebuild.sh`. Paths are at the top of `paths.py`. `build_v2.py` resumes completed segment files; remove the applicable **v2** segment cache before rebuilding changed shots. `qa.py` generates final-output proof PNGs every 0.25 s around masked slots, plus contact sheets every 3 s and audio logs.

## Tooling limits / work not done

- The requested Playwright HTML-to-PNG implementation is supplied as `render_cards_v2.cjs` and was attempted twice. Chrome failed at startup because the sandbox denies its socket operation. Executed exports therefore use `render_fallback.py` with Pillow + Raqm for shaped Arabic PNGs. This is a deviation from the requested overlay-rendering method. Failure evidence: `graphics.log`.
- `ffprobe` is absent. Network/DNS restrictions prevented fetching it. Durations below are exact MP4 movie-header durations (`probe_duration.py`) cross-checked against ffmpeg input/decode logs; they must not be represented as ffprobe results.
- No new s3b insert: captions were corrected instead. Holds use cloned endpoint frames, without artificial camera motion. No claims of an auditory seam review are made; the complete exports are measured and decoded.

## Source audit

| Raw clip | Encoded frames checked | Frames with template matches | First / last detection (s) |
|---|---:|---:|---|
| s0-phone-lowstock | 205 | 0 | — |
| s1-rfq | 665 | 0 | — |
| s2-quote-photo | 247 | 62 | 5.0749 / 32.8575 |
| s2b-photo-closeup | 132 | 114 | 0.0000 / 15.5224 |
| s3-guardrail-draft | 212 | 5 | 4.6338 / 6.9962 |
| s3b-compare | 85 | 0 | — |
| s3c-smart-compare | 193 | 0 | — |
| s4-phone-approve | 133 | 37 | 8.4163 / 17.1586 |
| s5-po-savings | 694 | 0 | — |
| s6-savings-close | 107 | 0 | — |

Retired old-s6-savings-pending: 85 encoded frames checked, 0 email matches.

Compact phone-list layout: 19 matched frames, 6.0989–8.2495 s. That entire layout is omitted from every cut.

## ar-16x9

The EDL below is the executed v2 plan. Source spans are seconds in raw clips; freeze is additional cloned endpoint time. Speed applies only to the moving portion.

| Slot | Output interval | Source | Source span | Speed / treatment | Caption |
|---:|---|---|---|---|---|
| 0 | 0.00–3.00 | stock | 0–3 | 1.000× | open |
| 1 | 3.00–11.00 | s0-phone-lowstock | 7.5–20.5 | 1.625× | low |
| 2 | 11.00–14.00 | s0-phone-lowstock | 21–22.5 | 1.000× + 1.5 s hold | low |
| 3 | 14.00–16.50 | s1-rfq | 2.5–5 | 1.000× | rfq |
| 4 | 16.50–29.50 | s1-rfq | 6–37.5 | 2.423×; crop x,y,w,h=(400, 100, 1000, 900) | rfq |
| 5 | 29.50–33.50 | s1-rfq | 40–43 | 1.000× + 1 s hold; crop x,y,w,h=(400, 100, 1000, 900) | rfq |
| 6 | 33.50–35.50 | s2-quote-photo | 2.5–4.5 | 1.000× | photo |
| 7 | 35.50–40.50 | s2b-photo-closeup | 4–8 | 1.000× + 1 s hold; crop x,y,w,h=(240, 65, 1450, 1000) | photo |
| 8 | 40.50–45.00 | s2b-photo-closeup | 10–12 | 1.000× + 2.5 s hold; crop x,y,w,h=(240, 240, 720, 690) | fields |
| 9 | 45.00–49.50 | s2b-photo-closeup | 18–21 | 1.000× + 1.5 s hold; crop x,y,w,h=(240, 295, 720, 450) | lines |
| 10 | 49.50–53.50 | s2-quote-photo | 26–30 | 1.000×; crop x,y,w,h=(240, 120, 1450, 900) | authorise |
| 11 | 53.50–58.50 | s3c-smart-compare | 5.5–11.5 | 1.200×; crop x,y,w,h=(240, 100, 1450, 950) | compare |
| 12 | 58.50–64.00 | s3c-smart-compare | 12–15 | 1.000× + 2.5 s hold; crop x,y,w,h=(250, 550, 1420, 480) | prices |
| 13 | 64.00–68.50 | s3-guardrail-draft | 9–11 | 1.000× + 2.5 s hold; crop x,y,w,h=(430, 90, 815, 290) | draft |
| 14 | 68.50–76.50 | s3-guardrail-draft | 16–29.7 | 1.712×; crop x,y,w,h=(425, 90, 825, 920) | submit |
| 15 | 76.50–82.00 | s4-phone-approve | 9–12 | 1.000× + 2.5 s hold | approve |
| 16 | 82.00–87.00 | s4-phone-approve | 12.5–18.6 | 1.220× | approved |
| 17 | 87.00–94.00 | s5-po-savings | 7.5–19.5 | 1.714×; crop x,y,w,h=(350, 100, 1220, 900) | po |
| 18 | 94.00–97.90 | s5-po-savings | 34–35.4 | 1.000× + 2.5 s hold; crop x,y,w,h=(355, 100, 1220, 850) | po |
| 19 | 97.90–102.90 | s5-po-savings | 34–37.8 | 1.000× + 1.2 s hold; crop x,y,w,h=(355, 80, 1220, 960) | sent |
| 20 | 102.90–108.90 | s5-po-savings | 40.5–47.5 | 1.167×; crop x,y,w,h=(770, 120, 1110, 690) | outcome |
| 21 | 108.90–113.40 | s5-po-savings | 51–53 | 1.000× + 2.5 s hold; crop x,y,w,h=(220, 235, 1370, 760) | outcome |
| 22 | 113.40–118.40 | counter | 0–1 | 1 s count-up + final hold | Historical-baseline saving |
| 23 | 118.40–125.40 | s6-savings-close | 9–13 | 1.000× + 3 s hold; crop x,y,w,h=(220, 170, 1230, 800) | ledger |

Body: 125.40 s, followed by the original landscape ar outro.

Exact mask enable intervals (whole output slots, including frozen frames; intervals are half-open):

| Slot | Output mask interval | Source mask x,y,w,h,color | Visibility |
|---:|---|---|---|
| 7 | 35.500–40.500 s | [800, 110, 148, 108, 'white'] | Identity field retained and covered |
| 8 | 40.500–45.000 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 15 | 76.500–82.000 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |
| 16 | 82.000–87.000 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |

Measured finished duration: **135.150 s**. Integrated loudness: **-14.06 LUFS**. True peak: **-1.31 dBTP** (loudnorm input measurement). See `analysis/loudness-ar-16x9.log` and `analysis/decode-ebur128-ar-16x9.log`.

Mask proof: 100 final-output full-size PNGs, every 0.25 s with 0.5 s context on either side of each masked slot. Inspection sheets: `proof/ar-16x9-inspection-01.jpg`, `proof/ar-16x9-inspection-02.jpg`, `proof/ar-16x9-inspection-03.jpg`. Exact filenames are listed in `proof/INSPECTED_FRAMES.txt`.

## en-16x9

The EDL below is the executed v2 plan. Source spans are seconds in raw clips; freeze is additional cloned endpoint time. Speed applies only to the moving portion.

| Slot | Output interval | Source | Source span | Speed / treatment | Caption |
|---:|---|---|---|---|---|
| 0 | 0.00–3.00 | stock | 0–3 | 1.000× | open |
| 1 | 3.00–11.00 | s0-phone-lowstock | 7.5–20.5 | 1.625× | low |
| 2 | 11.00–14.00 | s0-phone-lowstock | 21–22.5 | 1.000× + 1.5 s hold | low |
| 3 | 14.00–16.50 | s1-rfq | 2.5–5 | 1.000× | rfq |
| 4 | 16.50–29.50 | s1-rfq | 6–37.5 | 2.423×; crop x,y,w,h=(400, 100, 1000, 900) | rfq |
| 5 | 29.50–33.50 | s1-rfq | 40–43 | 1.000× + 1 s hold; crop x,y,w,h=(400, 100, 1000, 900) | rfq |
| 6 | 33.50–35.50 | s2-quote-photo | 2.5–4.5 | 1.000× | photo |
| 7 | 35.50–40.50 | s2b-photo-closeup | 4–8 | 1.000× + 1 s hold; crop x,y,w,h=(240, 65, 1450, 1000) | photo |
| 8 | 40.50–45.00 | s2b-photo-closeup | 10–12 | 1.000× + 2.5 s hold; crop x,y,w,h=(240, 240, 720, 690) | fields |
| 9 | 45.00–49.50 | s2b-photo-closeup | 18–21 | 1.000× + 1.5 s hold; crop x,y,w,h=(240, 295, 720, 450) | lines |
| 10 | 49.50–53.50 | s2-quote-photo | 26–30 | 1.000×; crop x,y,w,h=(240, 120, 1450, 900) | authorise |
| 11 | 53.50–58.50 | s3c-smart-compare | 5.5–11.5 | 1.200×; crop x,y,w,h=(240, 100, 1450, 950) | compare |
| 12 | 58.50–64.00 | s3c-smart-compare | 12–15 | 1.000× + 2.5 s hold; crop x,y,w,h=(250, 550, 1420, 480) | prices |
| 13 | 64.00–68.50 | s3-guardrail-draft | 9–11 | 1.000× + 2.5 s hold; crop x,y,w,h=(430, 90, 815, 290) | draft |
| 14 | 68.50–76.50 | s3-guardrail-draft | 16–29.7 | 1.712×; crop x,y,w,h=(425, 90, 825, 920) | submit |
| 15 | 76.50–82.00 | s4-phone-approve | 9–12 | 1.000× + 2.5 s hold | approve |
| 16 | 82.00–87.00 | s4-phone-approve | 12.5–18.6 | 1.220× | approved |
| 17 | 87.00–94.00 | s5-po-savings | 7.5–19.5 | 1.714×; crop x,y,w,h=(350, 100, 1220, 900) | po |
| 18 | 94.00–97.90 | s5-po-savings | 34–35.4 | 1.000× + 2.5 s hold; crop x,y,w,h=(355, 100, 1220, 850) | po |
| 19 | 97.90–102.90 | s5-po-savings | 34–37.8 | 1.000× + 1.2 s hold; crop x,y,w,h=(355, 80, 1220, 960) | sent |
| 20 | 102.90–108.90 | s5-po-savings | 40.5–47.5 | 1.167×; crop x,y,w,h=(770, 120, 1110, 690) | outcome |
| 21 | 108.90–113.40 | s5-po-savings | 51–53 | 1.000× + 2.5 s hold; crop x,y,w,h=(220, 235, 1370, 760) | outcome |
| 22 | 113.40–118.40 | counter | 0–1 | 1 s count-up + final hold | Historical-baseline saving |
| 23 | 118.40–125.40 | s6-savings-close | 9–13 | 1.000× + 3 s hold; crop x,y,w,h=(220, 170, 1230, 800) | ledger |

Body: 125.40 s, followed by the original landscape en outro.

Exact mask enable intervals (whole output slots, including frozen frames; intervals are half-open):

| Slot | Output mask interval | Source mask x,y,w,h,color | Visibility |
|---:|---|---|---|
| 7 | 35.500–40.500 s | [800, 110, 148, 108, 'white'] | Identity field retained and covered |
| 8 | 40.500–45.000 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 15 | 76.500–82.000 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |
| 16 | 82.000–87.000 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |

Measured finished duration: **135.150 s**. Integrated loudness: **-14.06 LUFS**. True peak: **-1.31 dBTP** (loudnorm input measurement). See `analysis/loudness-en-16x9.log` and `analysis/decode-ebur128-en-16x9.log`.

Mask proof: 100 final-output full-size PNGs, every 0.25 s with 0.5 s context on either side of each masked slot. Inspection sheets: `proof/en-16x9-inspection-01.jpg`, `proof/en-16x9-inspection-02.jpg`, `proof/en-16x9-inspection-03.jpg`. Exact filenames are listed in `proof/INSPECTED_FRAMES.txt`.

## ar-9x16-60s

The EDL below is the executed v2 plan. Source spans are seconds in raw clips; freeze is additional cloned endpoint time. Speed applies only to the moving portion.

| Slot | Output interval | Source | Source span | Speed / treatment | Caption |
|---:|---|---|---|---|---|
| 0 | 0.00–1.50 | stock-v | 0.5–2 | 1.000× | open |
| 1 | 1.50–5.00 | s0-phone-lowstock | 14–20.3 | 1.800×; crop x,y,w,h=(0, 50, 390, 330) | low |
| 2 | 5.00–7.50 | s0-phone-lowstock | 21–22.5 | 1.000× + 1 s hold; crop x,y,w,h=(0, 335, 390, 240) | low |
| 3 | 7.50–10.50 | s1-rfq | 34–37 | 1.000×; crop x,y,w,h=(420, 190, 815, 820) | rfq |
| 4 | 10.50–13.50 | s2b-photo-closeup | 4–6 | 1.000× + 1 s hold; crop x,y,w,h=(995, 245, 660, 500) | photo |
| 5 | 13.50–16.50 | s2b-photo-closeup | 10–11 | 1.000× + 2 s hold; crop x,y,w,h=(250, 250, 700, 385) | fields |
| 6 | 16.50–21.00 | s3c-smart-compare | 12–14 | 1.000× + 2.5 s hold; crop x,y,w,h=(255, 550, 1405, 480) | prices |
| 7 | 21.00–24.50 | s3-guardrail-draft | 9–10.5 | 1.000× + 2 s hold; crop x,y,w,h=(430, 140, 805, 150) | draft |
| 8 | 24.50–26.50 | s3-guardrail-draft | 26–29 | 1.500×; crop x,y,w,h=(435, 760, 795, 220) | submit |
| 9 | 26.50–30.50 | s4-phone-approve | 9–11 | 1.000× + 2 s hold; crop x,y,w,h=(0, 65, 390, 295) | approve |
| 10 | 30.50–33.50 | s4-phone-approve | 13–18.6 | 1.867×; crop x,y,w,h=(0, 380, 390, 464) | approved |
| 11 | 33.50–36.50 | s5-po-savings | 34–36 | 1.000× + 1 s hold; crop x,y,w,h=(1100, 95, 470, 605) | sent |
| 12 | 36.50–39.50 | s5-po-savings | 45.5–47.5 | 1.000× + 1 s hold; crop x,y,w,h=(775, 150, 1100, 630) | outcome |
| 13 | 39.50–43.50 | counter | 0–1 | 1 s count-up + final hold | Historical-baseline saving |
| 14 | 43.50–46.50 | s6-savings-close | 10–11 | 1.000× + 2 s hold; crop x,y,w,h=(1030, 295, 410, 105) | ledger |

Body: 46.50 s, followed by the original vertical ar outro.

Exact mask enable intervals (whole output slots, including frozen frames; intervals are half-open):

| Slot | Output mask interval | Source mask x,y,w,h,color | Visibility |
|---:|---|---|---|
| 4 | 10.500–13.500 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 5 | 13.500–16.500 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 9 | 26.500–30.500 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |
| 10 | 30.500–33.500 s | [30, 231, 276, 25, '0xfff7ff'] | Source masked; identity panel is also outside retained crop |

Measured finished duration: **55.012 s**. Integrated loudness: **-14.14 LUFS**. True peak: **-2.80 dBTP** (loudnorm input measurement). See `analysis/loudness-ar-9x16-60s.log` and `analysis/decode-ebur128-ar-9x16-60s.log`.

Mask proof: 72 final-output full-size PNGs, every 0.25 s with 0.5 s context on either side of each masked slot. Inspection sheets: `proof/ar-9x16-60s-inspection-01.jpg`, `proof/ar-9x16-60s-inspection-02.jpg`. Exact filenames are listed in `proof/INSPECTED_FRAMES.txt`.

## en-9x16-60s

The EDL below is the executed v2 plan. Source spans are seconds in raw clips; freeze is additional cloned endpoint time. Speed applies only to the moving portion.

| Slot | Output interval | Source | Source span | Speed / treatment | Caption |
|---:|---|---|---|---|---|
| 0 | 0.00–1.50 | stock-v | 0.5–2 | 1.000× | open |
| 1 | 1.50–5.00 | s0-phone-lowstock | 14–20.3 | 1.800×; crop x,y,w,h=(0, 50, 390, 330) | low |
| 2 | 5.00–7.50 | s0-phone-lowstock | 21–22.5 | 1.000× + 1 s hold; crop x,y,w,h=(0, 335, 390, 240) | low |
| 3 | 7.50–10.50 | s1-rfq | 34–37 | 1.000×; crop x,y,w,h=(420, 190, 815, 820) | rfq |
| 4 | 10.50–13.50 | s2b-photo-closeup | 4–6 | 1.000× + 1 s hold; crop x,y,w,h=(995, 245, 660, 500) | photo |
| 5 | 13.50–16.50 | s2b-photo-closeup | 10–11 | 1.000× + 2 s hold; crop x,y,w,h=(250, 250, 700, 385) | fields |
| 6 | 16.50–21.00 | s3c-smart-compare | 12–14 | 1.000× + 2.5 s hold; crop x,y,w,h=(255, 550, 1405, 480) | prices |
| 7 | 21.00–24.50 | s3-guardrail-draft | 9–10.5 | 1.000× + 2 s hold; crop x,y,w,h=(430, 140, 805, 150) | draft |
| 8 | 24.50–26.50 | s3-guardrail-draft | 26–29 | 1.500×; crop x,y,w,h=(435, 760, 795, 220) | submit |
| 9 | 26.50–30.50 | s4-phone-approve | 9–11 | 1.000× + 2 s hold; crop x,y,w,h=(0, 65, 390, 295) | approve |
| 10 | 30.50–33.50 | s4-phone-approve | 13–18.6 | 1.867×; crop x,y,w,h=(0, 380, 390, 464) | approved |
| 11 | 33.50–36.50 | s5-po-savings | 34–36 | 1.000× + 1 s hold; crop x,y,w,h=(1100, 95, 470, 605) | sent |
| 12 | 36.50–39.50 | s5-po-savings | 45.5–47.5 | 1.000× + 1 s hold; crop x,y,w,h=(775, 150, 1100, 630) | outcome |
| 13 | 39.50–43.50 | counter | 0–1 | 1 s count-up + final hold | Historical-baseline saving |
| 14 | 43.50–46.50 | s6-savings-close | 10–11 | 1.000× + 2 s hold; crop x,y,w,h=(1030, 295, 410, 105) | ledger |

Body: 46.50 s, followed by the original vertical en outro.

Exact mask enable intervals (whole output slots, including frozen frames; intervals are half-open):

| Slot | Output mask interval | Source mask x,y,w,h,color | Visibility |
|---:|---|---|---|
| 4 | 10.500–13.500 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 5 | 13.500–16.500 s | [800, 110, 148, 108, 'white'] | Source masked; identity panel is also outside retained crop |
| 9 | 26.500–30.500 s | [30, 231, 276, 25, '0xfff7ff'] | Identity field retained and covered |
| 10 | 30.500–33.500 s | [30, 231, 276, 25, '0xfff7ff'] | Source masked; identity panel is also outside retained crop |

Measured finished duration: **55.012 s**. Integrated loudness: **-14.14 LUFS**. True peak: **-2.80 dBTP** (loudnorm input measurement). See `analysis/loudness-en-9x16-60s.log` and `analysis/decode-ebur128-en-9x16-60s.log`.

Mask proof: 72 final-output full-size PNGs, every 0.25 s with 0.5 s context on either side of each masked slot. Inspection sheets: `proof/en-9x16-60s-inspection-01.jpg`, `proof/en-9x16-60s-inspection-02.jpg`. Exact filenames are listed in `proof/INSPECTED_FRAMES.txt`.

## Final validation

- All four complete exports decoded without reported corruption or timestamp errors. FFmpeg metadata confirms H.264 / yuv420p / 30 fps and AAC.
- Source containment: zero uncovered email-template detections in the executed EDLs. Every retained masked field was also checked in every output frame: 1,170 opaque mask interiors passed.
- Visually inspected all 344 quarter-second proof PNGs through the ten inspection sheets, plus all four final 3-second contact sheets. No readable private login email found. Exact inspected frame names: `proof/INSPECTED_FRAMES.txt`. The supplied outros retain their original public business contact details.
- `MEASUREMENTS.json` contains final durations, loudnorm input measurements, proof counts and SHA-256 hashes.
- Temporary unmasked source stills were removed after the audit; rebuild templates are now extracted directly from the raw sources in memory.
