# ProcurePilot Demo v2.2 — Changes and Reviewer Fixes

This release addresses all editorial findings identified in `OWNER-REVIEW-FINDINGS.md` and subsequent orchestrator review across both languages (Arabic and English) and both aspect ratios (16:9 landscape and 9:16 vertical).

No commits or git commands were run. All writes are self-contained in `/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad/edit/v22/`.

---

## 1. Summary of Changes Mapped to Review Findings

### Fix 1: Cropped Click Targets (FULL #5 RFQ Send & FULL #19 Create PO)
- **Finding**: Reviewer Section 4 reported that RFQ Send in FULL #5 sat around source $y \approx 1010$, below the crop's bottom ($y = 1000$), reducing the button to a clipped sliver. Similarly, in FULL #17/#19, Create PO sat at the bottom edge ($y \approx 1039$), clipping the label and cursor.
- **Fix**:
  - **FULL #5 (RFQ Send)**: Reframed action shot to action crop `(400, 180, 1000, 900)` spanning $y=180..1080$. The entire Send button (ending at $y=1054$) is fully visible with 26 px bottom margin before pointer arrives ($t=40.5$), during click ($t=41.6$), and cuts at $t=41.65$ right at click instant.
  - **FULL #19 (Create PO)**: Reframed action shot to action crop `(350, 160, 1220, 900)` spanning $y=160..1060$. The entire Create PO button (ending at $y=1039$) and its bottom margin (21 px) remain completely visible through pointer arrival and click at $t=18.50$.

### Fix 2: Removal of Loading / Busy States and Freeze-Holds
- **Finding**: Reviewer Section 3 and orchestrator review identified occurrences where buttons/forms remained disabled or showed loading spinners, including freeze-holding a busy state in VERT #12 and ending shots on busy controls («جاري الإنشاء...» in Create PO).
- **Fix**:
  - **FULL #1 (`s0-phone-lowstock-v3`)**: Trimmed endpoint from 20.5 s to 19.4 s, cutting right at tap instant directly to confirmation hold, eliminating the disabled-button tail.
  - **FULL #5 (`s1-rfq`)**: Ended at 41.65 s (click instant) with `freeze=0`. Removed 2.0 s of busy spinner and eliminated the 1.0 s freeze-hold on the spinner.
  - **FULL #6 (`s2-quote-photo`)**: Trimmed endpoint from 4.5 s to 3.95 s, cutting ~0.05 s after the row click directly to the extracted quote document (`s2b-photo-closeup`), eliminating 0.6 s of blank loading spinner.
  - **FULL #10 (`s2-quote-photo`)**: Ended at 26.70 s (exact confirm click), cutting before the panel collapse and busy authorize button.
  - **FULL #14 (`s3-guardrail-draft`)**: Ended at 27.20 s (click instant), cutting away 2.5 s of busy button and full-page loading spinner.
  - **FULL #16 & #17 (`s4-phone-approve`)**: Ended action click at 14.00 s, cutting out 3.1 s of disabled controls and blank transition (14.0–17.1 s), cutting straight to the completed empty queue with success toast at 17.1–18.6 s.
  - **FULL #19 (`s5-po-savings`)**: Ended Create PO action at 18.50 s (exact click instant), cutting before the button turns to busy spinner «جاري الإنشاء...» at 18.533 s.
  - **FULL #21 (`s5-po-savings`)**: Ended Save outcome action at 46.30 s (click instant), cutting away 2.2 s of faded/disabled outcome modal form.
  - **VERT #2 (`s0-phone-lowstock-v3`)**: Ended submit action at 19.40 s at tap instant.
  - **VERT #9 (`s3-guardrail-draft`)**: Ended submit action at 27.20 s, removing all busy states.
  - **VERT #11 & #12 (`s4-phone-approve`)**: Ended tap at 14.00 s, cutting out 3.1 s of loading/spinner directly to the toast at 17.1 s.
  - **VERT #14 & #15 (`s5-po-savings`)**: Ended Save action at 46.30 s, cutting out the disabled form. Crucially, **eliminated the 1.0 s freeze-hold on the busy state** and moved the hold onto the completed PO outcome card (1.5 s hold).

### Fix 3: Cursor Misrepresentation at Quote Authorisation (FULL #10)
- **Finding**: Reviewer reported that the drawn pointer sat under Reject while authorising. Orchestrator review noted that from ~26.8 s the panel collapsed, page shifted up, and the pointer was left over «رفض عرض السعر» while the authorise button was busy.
- **Source Frame Evidence**:
  - $t=25.20..26.00$ s (Frames 0–24): pointer on page's «تأكيد واعتماد عرض السعر» button; click down at $t=25.80$.
  - $t=26.03..26.60$ s (Frames 25–48): confirmation modal panel opens, pointer ascends into modal toward «تأكيد واعتماد».
  - $t=26.67..26.70$ s (Frames 50–52): pointer on confirmation button inside modal; Frame 52 ($t=26.700$) is the active confirm click down.
  - $t=26.733$ s (Frame 53): modal collapses, page shifts up, pointer sits at $(918, 416)$ directly on «رفض عرض السعر».
- **Fix**: Set source span to $25.20 \to 26.700$ s ($d=2.2$ s). The shot presents the full page click, modal entry, and modal confirm click, cutting on Frame 52 before the collapse. No frame in the output video shows the pointer on Reject or any busy state.

### Fix 4: Caption Timing on Phone Approval
- **Finding**: In v2.1, "Request approved" / «تم اعتماد الطلب» began at FULL 82.0 s / VERT 30.5 s, several seconds before the manager tapped Approve.
- **Fix**:
  - The review shot retains caption `'approve'` («المدير يراجع ويعتمد من الموبايل» / "Manager reviews and approves on the phone").
  - Added new caption string `'approve_action'` («اعتماد الطلب» / "Approve the request") for the action click shot.
  - Caption `'approved'` («تم اعتماد الطلب» / "Request approved") now starts **only** when the success toast appears ($t=17.1$ s), perfectly aligning caption and evidence.

### Fix 5: Enlarged Decisive Evidence
- **Finding**: Landscape phone scenes occupied a narrow 409 px central strip (only 21% of screen width); vertical outcome shot in VERT #12 was scaled down to 554 px height with unreadable decimals.
- **Fix**:
  - **Landscape Phone**: Updated `build_v2.py` and `verify_output_masks.py` to support cropping and zooming for phone scenes in 16:9. Review shot uses crop `(0, 65, 390, 500)` (scaling to 694×890), and approve action & toast shots use crop `(0, 380, 390, 464)` (scaling to 748×890). Buttons, details, and success toast are nearly double their previous size.
  - **Vertical Outcome**: Reframed outcome Save action to `(770, 450, 600, 400)` and completed outcome to `(350, 235, 950, 700)`, zooming in on the decisive outcome status and total rather than squeezing an entire wide table.

### Fix 6: Elimination of Repeated PO Passage
- **Finding**: FULL #18 and #19 both restarted `s5-po-savings` at source 34.0 s, causing the viewer to watch the page load and cursor move twice.
- **Fix**: Consolidated into a single shot: `shot('s5-po-savings', 34.0, 37.8, 4.5, 'sent', (355, 80, 1220, 960), freeze=1.5)`. One progression showing the PO page settling, and one useful 1.5 s hold on PO-000006.

### Fix 7: Vertical Continuity for Low-Stock Submission
- **Finding**: In v2.1 VERT, product selection jumped straight to confirmation toast, omitting quantity entry and submission.
- **Fix**: Inserted new slot VERT #2 (`s0-phone-lowstock-v3`, 18.0–19.4 s, $d=1.8$ s, crop `(0, 65, 390, 360)`), showing the completed form with oil quantity and the user tapping the submit button at 19.3 s, followed immediately by the confirmation toast.

### Fix 8: Raw Decimals Avoidance
- **Finding**: Inspected quote showed raw unformatted numbers like `1610.0000` and raw decimals in outcome.
- **Fix**: Cutting authorisation at $t=26.70$ s avoids the unformatted table exposed during loading. The reframed vertical outcome focus isolates clean summary amounts.

---

## 2. Audio and Video Measurements

Measured using exact MP4 movie header parsing, EBU R128 integrated loudness, and full-decode true peak (`ebur128=peak=true`).

| Output File | Resolution | Duration | Integrated LUFS | True Peak | Audio Limiter | Checksum (SHA-256) |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `procurepilot-demo-ar-16x9.mp4` | 1920×1080 | 116.950 s (1:56.95) | -13.8 LUFS | -1.3 dBTP | -3.0 dBFS | `c6c4b62c11e9598acbf972b67a953ffca19399cad59a4be04098dd566853c292` |
| `procurepilot-demo-en-16x9.mp4` | 1920×1080 | 116.950 s (1:56.95) | -13.8 LUFS | -1.3 dBTP | -3.0 dBFS | `e28e941419004d025bdcbfaf4aa545bbd5b9dca849004364d0cac7cf9fe3fc46` |
| `procurepilot-demo-ar-9x16-60s.mp4` | 1080×1920 | 51.812 s (0:51.81) | -14.2 LUFS | -2.8 dBTP | -3.0 dBFS | `d18defbe30c7b10b6275bf57899c05042484870c7b130b16196d9a05f7772db1` |
| `procurepilot-demo-en-9x16-60s.mp4` | 1080×1920 | 51.812 s (0:51.81) | -14.2 LUFS | -2.8 dBTP | -3.0 dBFS | `ee5d47fa3c41dcedfe4ebbdb7c35f7711c9ffb337e33d9bfd1c721f2fb7e2931` |

All four outputs meet every constraint:
- 16:9 duration is 1:56.95 (under the 2:15 limit).
- 9:16 duration is 51.81 s (comfortably under the 60.0 s ceiling).
- Loudness is target -14 LUFS (within ±0.2 LUFS).
- True peak does not exceed -1.3 dBTP.

---

## 3. Executed v2.2 EDL

### 16:9 Landscape (`FULL`)

| Slot | Output Window | Source Clip | Source Span | Speed / Freeze | Crop $(x, y, w, h)$ | Caption | Finding / Purpose |
|---:|---|---|---|---|---|---|---|
| 0 | 0.00–3.00 | `stock` | 0.0–3.0 | 1.00× | Full (1920×1080) | `open` | Unchanged opening stock shot |
| 1 | 3.00–10.50 | `s0-phone-lowstock-v3` | 1.5–19.40 | 2.39× | Full phone (885h) | `low` | Tap submit at 19.3 s; cuts at 19.40 s (busy tail removed) |
| 2 | 10.50–13.50 | `s0-phone-lowstock-v3` | 21.3–22.8 | 1.00× + 1.5 s hold | Full phone (885h) | `low` | Low-stock confirmation hold |
| 3 | 13.50–16.00 | `s1-rfq` | 2.5–5.0 | 1.00× | Full web | `rfq` | RFQ creation page |
| 4 | 16.00–28.00 | `s1-rfq` | 6.0–37.5 | 2.63× | (400, 100, 1000, 900) | `rfq` | RFQ review details & vendor selection |
| 5 | 28.00–30.20 | `s1-rfq` | 40.5–41.65 | 0.52× | (400, 180, 1000, 900) | `rfq` | **Repaired action crop**: Send visible + margin; click at 41.6 s, no busy freeze |
| 6 | 30.20–31.70 | `s2-quote-photo` | 2.5–3.95 | 0.97× | Full web | `photo` | Quote list; click at 3.9 s; cuts at 3.95 s (spinner cut) |
| 7 | 31.70–36.20 | `s2b-photo-closeup` | 4.0–8.0 | 1.14× + 1.0 s hold | (240, 65, 1450, 1000) | `photo` | Extracted quote photo document (masked) |
| 8 | 36.20–40.20 | `s2b-photo-closeup` | 10.0–12.0 | 1.00× + 2.0 s hold | (240, 240, 720, 690) | `fields` | Reconciled fields (masked) |
| 9 | 40.20–44.20 | `s2b-photo-closeup` | 18.0–21.0 | 1.20× + 1.5 s hold | (240, 295, 720, 450) | `lines` | Oil, rice, onions line items |
| 10 | 44.20–46.40 | `s2-quote-photo` | 25.2–26.70 | 0.68× | (240, 120, 1450, 900) | `authorise` | **Repaired**: Page click + modal confirm click at 26.70 s; cuts before panel collapse |
| 11 | 46.40–51.40 | `s3c-smart-compare` | 5.5–11.5 | 1.20× | (240, 100, 1450, 950) | `compare` | Multi-vendor offers comparison |
| 12 | 51.40–56.40 | `s3c-smart-compare` | 12.0–15.0 | 1.00× + 2.0 s hold | (250, 550, 1420, 480) | `prices` | Oil price difference vs baseline |
| 13 | 56.40–60.40 | `s3-guardrail-draft` | 9.0–11.0 | 1.00× + 2.0 s hold | (430, 90, 815, 290) | `draft` | Guardrail policy evaluation |
| 14 | 60.40–66.40 | `s3-guardrail-draft` | 16.0–27.20 | 1.87× | (425, 90, 825, 920) | `submit` | Review & Submit click at 27.1 s; cuts at 27.20 s (busy spinner cut) |
| 15 | 66.40–70.40 | `s4-phone-approve` | 9.0–12.5 | 0.88× | (0, 65, 390, 500) | `approve` | **Enlarged phone review**: request details (masked) |
| 16 | 70.40–72.90 | `s4-phone-approve` | 12.5–14.00 | 0.60× | (0, 380, 390, 464) | `approve_action` | **Enlarged phone action**: tap Approve at 13.8 s, cuts at 14.00 s |
| 17 | 72.90–76.40 | `s4-phone-approve` | 17.1–18.6 | 1.00× + 2.0 s hold | (0, 380, 390, 464) | `approved` | **Corrected caption timing**: Success toast with 2.0 s hold |
| 18 | 76.40–81.40 | `s5-po-savings` | 7.5–17.5 | 2.00× | (350, 100, 1220, 900) | `po` | Review crop for PO creation |
| 19 | 81.40–83.20 | `s5-po-savings` | 17.5–18.50 | 0.56× | (350, 160, 1220, 900) | `po` | **Repaired action crop & click**: click down at 18.50 s; cuts before «جاري الإنشاء...» |
| 20 | 83.20–87.70 | `s5-po-savings` | 34.0–37.8 | 1.27× + 1.5 s hold | (355, 80, 1220, 960) | `sent` | **Unified progression**: PO-000006 sent hold (repeats removed) |
| 21 | 87.70–91.70 | `s5-po-savings` | 40.5–46.30 | 1.45× | (770, 120, 1110, 690) | `outcome` | Record outcome; click Save at 46.2 s; cuts at 46.30 s (disabled form cut) |
| 22 | 91.70–95.70 | `s5-po-savings` | 50.5–53.0 | 1.25× + 2.0 s hold | (220, 235, 1370, 760) | `outcome` | Completed PO with recorded outcome hold |
| 23 | 95.70–100.70 | `counter` | 0.0–1.0 | 1.00× + 4.0 s hold | Full canvas | None | 460 EGP order savings counter |
| 24 | 100.70–107.20 | `s6-savings-close` | 9.0–13.0 | 1.00× + 2.5 s hold | (220, 170, 1230, 800) | `ledger` | Populated savings ledger with hold |
| Outro | 107.20–116.95 | `outro-16x9` | Preserved | 1.00× | Full canvas | None | Preserved outro & brand animation |

---

### 9:16 Vertical (`VERT`)

| Slot | Output Window | Source Clip | Source Span | Speed / Freeze | Crop $(x, y, w, h)$ | Caption | Finding / Purpose |
|---:|---|---|---|---|---|---|---|
| 0 | 0.00–1.50 | `stock-v` | 0.5–2.0 | 1.00× | Full (1080×1920) | `open` | Unchanged opening stock shot |
| 1 | 1.50–4.50 | `s0-phone-lowstock-v3` | 2.0–11.0 | 3.00× | (0, 0, 390, 420) | `low` | Product selection |
| 2 | 4.50–6.30 | `s0-phone-lowstock-v3` | 18.0–19.40 | 0.78× | (0, 65, 390, 360) | `low` | **Vertical continuity**: completed form & submit tap at 19.3 s, cuts at 19.40 s |
| 3 | 6.30–8.30 | `s0-phone-lowstock-v3` | 21.3–22.8 | 1.50× + 1.0 s hold | (0, 335, 390, 240) | `low` | Confirmation toast hold |
| 4 | 8.30–10.80 | `s1-rfq` | 34.0–37.0 | 1.20× | (420, 190, 815, 820) | `rfq` | RFQ terms entry |
| 5 | 10.80–13.30 | `s2b-photo-closeup` | 4.0–6.0 | 1.33× + 1.0 s hold | (995, 245, 660, 500) | `photo` | Quote photo document view (masked) |
| 6 | 13.30–15.80 | `s2b-photo-closeup` | 10.0–11.0 | 1.00× + 1.5 s hold | (250, 250, 700, 385) | `fields` | Extracted quote reconciliation hold (masked) |
| 7 | 15.80–19.30 | `s3c-smart-compare` | 12.0–14.0 | 1.33× + 2.0 s hold | (880, 590, 790, 470) | `prices` | Comparison outcome & savings hold |
| 8 | 19.30–22.30 | `s3-guardrail-draft` | 9.0–10.5 | 1.00× + 1.5 s hold | (435, 90, 800, 820) | `draft` | Guardrail auto-draft |
| 9 | 22.30–23.80 | `s3-guardrail-draft` | 26.2–27.20 | 0.67× | (435, 480, 800, 520) | `submit` | Submit click at 27.1 s; cuts at 27.20 s (busy state cut) |
| 10 | 23.80–26.30 | `s4-phone-approve` | 9.0–11.0 | 1.33× + 1.0 s hold | (0, 65, 390, 295) | `approve` | Manager review details (masked) |
| 11 | 26.30–27.80 | `s4-phone-approve` | 13.0–14.00 | 0.67× | (0, 380, 390, 464) | `approve_action` | Action: tap Approve at 13.8 s, cuts at 14.00 s |
| 12 | 27.80–30.30 | `s4-phone-approve` | 17.1–18.6 | 1.50× + 1.5 s hold | (0, 380, 390, 464) | `approved` | **Corrected caption timing**: Success toast with hold |
| 13 | 30.30–32.80 | `s5-po-savings` | 34.0–36.0 | 1.33× + 1.0 s hold | (1100, 95, 470, 605) | `sent` | PO sent badge hold |
| 14 | 32.80–34.30 | `s5-po-savings` | 45.5–46.30 | 0.53× | (770, 450, 600, 400) | `outcome` | **Enlarged outcome action**: click Save at 46.2 s, cuts at 46.30 s before busy state |
| 15 | 34.30–36.80 | `s5-po-savings` | 50.5–52.5 | 2.00× + 1.5 s hold | (350, 235, 950, 700) | `outcome` | **Enlarged completed PO outcome hold** (replaces freezing busy state) |
| 16 | 36.80–40.30 | `counter` | 0.0–1.0 | 1.00× + 2.5 s hold | Full canvas | None | 460 EGP order savings counter |
| 17 | 40.30–43.30 | `s6-savings-close` | 10.0–11.0 | 1.00× + 2.0 s hold | (630, 290, 800, 620) | `ledger` | Populated savings ledger with hold |
| Outro | 43.30–51.81 | `outro-9x16` | Preserved | 1.00× | Full canvas | None | Preserved vertical outro & brand animation |

---

## 4. Mask Verification & Inspection Log

- Ran `verify_output_masks.py` across all four encoded outputs. All opaque mask interior checks passed with 100% compliance:
  - `ar-16x9`: PASSED (Slot 7: 135 frames checked, min gray 255; Slot 15: 120 frames checked, min gray 249; 0 bad frames).
  - `en-16x9`: PASSED (Slot 7: 135 frames checked, min gray 255; Slot 15: 120 frames checked, min gray 249; 0 bad frames).
  - `ar-9x16-60s`: PASSED (Slot 10: 75 frames checked, min gray 249; 0 bad frames).
  - `en-9x16-60s`: PASSED (Slot 10: 75 frames checked, min gray 249; 0 bad frames).
- Sourced clips `s2-quote-photo`, `s2b-photo-closeup`, `s3-guardrail-draft`, and `s4-phone-approve` were sampled at 0.25 s intervals across all output windows:
  - A total of **564 sampled frames** across all four cuts were extracted and visually inspected (logged in `analysis/s2_s4_inspection_manifest.json` and `proof/`).
  - No email addresses, personal identification, or unmasked tenant identity glyphs appear in any frame of any output.

---

## 5. Action-Boundary Contact Sheets

Per-cut contact sheets showing the exact frame immediately before and after every user click action were generated in `qa-v2.2/`:
1. `qa-v2.2/action-boundary-sheet-ar-16x9.jpg`: 8 click actions in Arabic 16:9 (before vs after).
2. `qa-v2.2/action-boundary-sheet-en-16x9.jpg`: 8 click actions in English 16:9 (before vs after).
3. `qa-v2.2/action-boundary-sheet-ar-9x16-60s.jpg`: 4 click actions in Arabic 9:16 (before vs after).
4. `qa-v2.2/action-boundary-sheet-en-9x16-60s.jpg`: 4 click actions in English 9:16 (before vs after).

In every case, the complete target control, pointer position, and comfortable margins are visible throughout the interaction.
