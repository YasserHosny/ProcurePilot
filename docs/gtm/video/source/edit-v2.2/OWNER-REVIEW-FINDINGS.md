## Review scope

**I agree with all four comments, with qualifications on language and cropped clicks.** Most loading and framing problems can be fixed in the edit. A fully English interface needs new recordings; an opening that demonstrates the procurement problem needs new footage or graphics.

I inspected:

- **380 extracted overview frames across all four v2.1 cuts**, approximately one per second, including the outros.
- Quarter-second samples around loading sequences, transitions and suspected cropped clicks, in **both languages**.
- Targeted source-recording contact sheets and six full-resolution source/export frames.

[Inspection manifest and exact sampling ranges](evidence_notes.md). All findings below concern frames I inspected. This was a sampled visual audit, not a check of every encoded frame or an audio review.

**Notation:** `FULL` means 16:9; `VERT` means 9:16. Slots are **zero-based**, matching the current `edl.py`. Times are seconds from the exported cut’s start. Rows marked “AR + EN” apply separately to both cuts. Loading boundaries and trim estimates are approximate, generally within 0.25 seconds.

Only scratch files were written in the permitted working directory.

## 1. Both language versions show the Arabic interface

**Agree factually; partly agree that this necessarily makes the English version wrong.** It is an English-captioned demonstration of an Arabic product workflow, and its captions disclose “Arabic interface.” That can serve an English-speaking stakeholder evaluating an Egyptian restaurant product. It does not demonstrate the English product experience.

| Cuts | Inspected evidence | EDL slot and source selection |
|---|---|---|
| AR + EN FULL | 3.625: Arabic phone home screen; 41.5: Arabic quote fields; 60.5: Arabic supplier comparison | #1 `s0-phone-lowstock-v3` 1.5–20.5; #8 `s2b-photo-closeup` 10–12; #12 `s3c-smart-compare` 12–15 |
| AR + EN VERT | 2.125: Arabic low-stock form; 14.5: Arabic extracted fields; 27.125: Arabic approval details | #1 `s0-phone-lowstock-v3` 2–11; #5 `s2b-photo-closeup` 10–11; #9 `s4-phone-approve` 9–11 |

The build also confirms that both languages use the same source selections and crops.

**Ranked fixes and cost:**

1. **Edit-only interim fix — low cost, approximately 1–2 hours:** retain the disclosure and add legible English translations beside the decisive evidence: supplier recommendation, approval control/status and ledger total. Existing captions translate the story, but do not translate every field viewers need to evaluate it.
2. **Preferred English release — medium cost, approximately ½–1 production day if the locale works:** re-record the web and phone workflow in English: low stock, RFQ, quote review, comparison, draft/submission, approval, PO and savings ledger. Recheck crops because English text and layout may differ.
3. **Prepare English or bilingual demo data — additional approximately 2–4 hours:** changing locale alone would ordinarily leave tenant-entered content Arabic: restaurant/branch names, products, suppliers, terms and descriptions. The photographed Arabic quote remains Arabic too. A coherent English-data demonstration needs corresponding product/supplier data and matching English quote documents. A bilingual tenant is suitable if its displayed names support both languages; otherwise use a separate English demo dataset.

I did **not** test the running app’s English locale, so these recording estimates assume it is available and complete. Arabic quote documents could deliberately remain in the English version to demonstrate Arabic-document extraction, provided that is explained.

## 2. The opening footage does not show the stated problem

**Agree.** The footage establishes “restaurant,” but does not establish quote handling or manual copying.

| Cuts | Inspected frames | EDL slot and source selection |
|---|---|---|
| AR + EN FULL | 0.5, 1.5, 2.5: chefs preparing food; no quote messages, papers or spreadsheet | FULL #0, `stock` 0–3: `pexels-4253325-kitchen-2048x1080.mp4` |
| AR + EN VERT | 0.5, 1.5: cooking at the grill; no procurement activity | VERT #0, `stock-v` 0.5–2: `pexels-31735802-chef-grill-2160x3840.mp4` |

The English caption asks, “Quotes on WhatsApp. Still copying by hand?” Nothing in those inspected opening frames demonstrates that action.

**Ranked fixes and cost:**

1. **Stage a small procurement sequence — preferred, approximately ½ day.** Record three tightly framed actions using consistent fictional data:
   - A phone displaying several Arabic supplier messages, including an attached quote photo and differing oil prices.
   - A hand sorting paper quotes beside the phone, marking prices with a pen.
   - The same quantities/prices being typed into a spreadsheet, with repeated switching back to the phone.

   For landscape, a three-second phone → paper → spreadsheet sequence could replace the existing opening. For the 1.5-second vertical opening, use one immediately understandable composition: phone quote beside a laptop, with a hand copying the price.

2. **Find licensed stock and composite fictional quote content — approximately 2–4 hours plus any licence fee.** Relevant stock listings exist, including [Office Desk with Calculator and Smartphone](https://www.pexels.com/video/office-desk-with-calculator-and-smartphone-31250072/) and [Typing on a Laptop and Working on Paperwork](https://www.pexels.com/video/a-person-typing-on-a-laptop-and-working-on-paperwork-8298071/). I checked their listings, **not the complete clips**, so they are candidates rather than approved selections.

   Search terms: **“supplier quotes phone spreadsheet,” “copying invoice data laptop,” “paper invoices calculator smartphone,” “restaurant manager paperwork,” “Arabic quotation phone.”**

   Pexels permits commercial use under the **Pexels License**, with separate considerations for depicted brands and other protected content. [Pexels commercial-use guidance](https://help.pexels.com/hc/en-us/articles/360042295214-Can-I-use-the-photos-and-videos-for-a-commercial-project). Pixabay uses its **Content License**, whose summary specifically restricts commercial uses involving recognizable brands. [Pixabay licence](https://pixabay.com/service/license-summary/). Neither should simply be labelled “public domain.”

3. **Edit-only fallback — approximately 1 hour:** replace the kitchen footage with a clearly illustrative phone-message/spreadsheet graphic. Alternatively, change the caption to a restaurant-context statement, accepting that the opening would no longer demonstrate the pain.

Use fictional contacts, numbers, messages and documents; suppress unrelated notifications. For an actual WhatsApp screen or logo, follow [Meta’s WhatsApp brand guidelines](https://www.meta.com/brand/resources/whatsapp/whatsapp-brand/) and avoid implying endorsement or direct integration. A generic messaging mockup should be visibly illustrative and avoid copying WhatsApp branding.

## 3. Loading states remain longer than necessary

**Agree.** This includes busy buttons and disabled forms, not just full-page spinners. Several shots cut away before displaying a clean result.

Below is **every loading/busy occurrence I identified** in the inspected exports. Each AR + EN row represents two occurrences.

| Cuts / slot | Approximate output interval | Source selection | What is visible; suggested removable time |
|---|---:|---|---|
| AR + EN FULL #1 | 10.6–11.0 | `s0-phone-lowstock-v3` 1.5–20.5 | Brief sending/disabled-button tail before confirmation. **About 0.2 s**; minor. |
| AR + EN FULL #5 | 30.9–33.5 | `s1-rfq` 40–43, +1 s freeze | Send control becomes busy below the crop; only its upper edge/spinner sliver survives. The endpoint hold prolongs this. **About 2.0 s**, alongside the crop repair. |
| AR + EN FULL #6 | 34.8–35.5 | `s2-quote-photo` 2.5–4.5 | Quote-review list becomes a blank page with loading spinner. **About 0.6 s.** |
| AR + EN FULL #10 | 50.6–53.5 | `s2-quote-photo` 26–30 | Authorisation button remains busy, followed by an almost blank loading page around 53.3. **About 2.5 s.** |
| AR + EN FULL #14 | 74.5–76.5 | `s3-guardrail-draft` 16–29.7 | Submission button stays busy, then full-page loading appears around 76.0. **About 1.6 s.** |
| AR + EN FULL #16 | 83.7–86.3 | `s4-phone-approve` 12.5–18.6 | Disabled approval controls, then a blank/spinner transition. **About 2.0 s** while preserving the subsequent success evidence. |
| AR + EN FULL #17 | approximately 93.6–94.0 | `s5-po-savings` 7.5–19.5 | Create-PO busy tail is partly clipped at the bottom. **About 0.2 s**; crop repair is more important. |
| AR + EN FULL #20 | 107.0–108.8 | `s5-po-savings` 40.5–47.5 | Outcome form fades/disables while Save processes. **About 1.5 s.** |
| AR + EN VERT #8 | 25.0–26.5 | `s3-guardrail-draft` 26–29 | Busy submission button occupies most of this short shot. **About 1.2 s.** |
| AR + EN VERT #10 | 31.0–32.8 | `s4-phone-approve` 13–18.6 | Disabled approval controls followed by spinner. **About 1.5 s**, retaining success confirmation afterward. |
| AR + EN VERT #12 | 37.2–39.5 | `s5-po-savings` 45.5–47.5, +1 s freeze | Busy outcome form; **the extra one-second hold freezes the busy state**. **About 2.0 s**, including that hold. |

**Estimated recoverable time:** approximately **10–12 seconds per landscape cut** and **4–5 seconds per vertical cut**. These are editorial estimates, not measured application response times.

The mostly empty phone screen after approximately **86.3 FULL / 32.8 VERT** is a **loaded empty approval queue with a success toast**, not continuing loading. Keep enough of that evidence to establish success; improve its framing.

**Preferred edit treatment:** show the click, allow roughly 0.15–0.3 seconds of response, then cut to the completed state. Put readable holds on completed results. Existing later source frames already show useful results, including the phone success toast and the populated savings ledger. Re-record only where a clean result or convincing action cannot be assembled from those sources.

Estimated effort: **2–3 hours for these edits**, plus render and visual QA.

## 4. Click targets are cut off by crops

**Agree, but this is concentrated in two landscape actions.** I found **four clear occurrences: two actions, each repeated in AR and EN**.

| Cuts / slot | Output evidence | Source selection and crop | Finding and concrete fix |
|---|---|---|---|
| AR + EN FULL #5 | approximately 30.9–31.3; full-resolution check at **31.0** | `s1-rfq` 40–43; crop **(400,100,1000,900)** | Send sits around source y≈1010, below the crop’s y=1000 bottom. The pointer travels out of view and the control is reduced to a sliver. Split off a lower action crop containing status, **the entire Send button**, and its response. Moving the existing crop down toward y=180 is another option, but loses the heading. |
| AR + EN FULL #17 | approximately 93.3–94.0; full-resolution check at **93.65** | `s5-po-savings` 7.5–19.5; crop **(350,100,1220,900)** | Create PO lies at the bottom edge: its label/cursor are clipped. Reframe the final action around the total and complete button, extending below source y=1000 with visible margin. |

Full-resolution export evidence: [RFQ Send at 31.0](rfq-final.png) and [Create PO at 93.65](po-final.png). I compared both with uncropped source frames.

**Related omissions, rather than additional cropped-click occurrences:**

- **AR + EN VERT #1 → #2, 4.875 → 5.5:** low-stock product selection jumps to confirmation. Source selections are `s0-phone-lowstock-v3` **2–11 → 21.3–22.8**. Quantity entry and submission are omitted; no off-crop submission click is retained.
- **AR + EN VERT #3, 7.5–10.5:** `s1-rfq` **34–37** shows terms being entered, but does not include sending the RFQ.
- **AR + EN VERT #9, 26.5–30.5:** `s4-phone-approve` **9–11**, crop **(0,65,390,295)**, shows review details without approval controls. The next slot **does show the full Approve button when clicked**, around **30.875**. I would not count that as a hidden click.

**Ranked fixes and cost:**

1. **Edit-only, approximately 1–2 hours:** use separate “review details” and “perform action” crops. Keep the complete control and a margin visible before the pointer arrives, through the click and initial response.
2. **Improve vertical continuity, approximately 1 hour:** include a brief completed low-stock form and submission action, using time recovered from loading.
3. **Re-record only if necessary:** position controls comfortably inside the recording viewport and pause before each action. The two confirmed landscape defects have sufficient uncropped source material for reframing.

## Other issues

- **The drawn cursor can misrepresent the target after page movement.** At **EN FULL 50.7**, slot #10, `s2-quote-photo` **26–30**, the app says it is authorising while the drawn pointer sits beneath the Reject control. [Inspected frame](quote-final.png). The recording helper draws a separate cursor and scrolls elements into view, which makes stale positioning plausible. Cut away after the valid click, or re-record that interaction with cursor placement updated after scrolling.
- **Success captions arrive before success evidence.** “Request approved” begins at **FULL 82.0 / VERT 30.5**, while approval is still awaiting the click. These are FULL #16 / VERT #10, `s4-phone-approve` **12.5–18.6 / 13–18.6**. Start with “Approve the request,” then change to “Request approved” when the toast appears.
- **Important evidence remains small.** Landscape phone scenes occupy a narrow central strip—e.g. **FULL 77.5**, #15, `s4-phone-approve` **9–12**. Vertical outcome evidence is particularly small at **38.5**, #12, `s5-po-savings` **45.5–47.5**. Enlarge the decisive control, amount or status rather than fitting every field.
- **The landscape PO section repeats footage.** FULL #18 **94.0–97.9** and #19 **97.9–102.9** both restart `s5-po-savings` at source **34**. The repeated page settling/cursor movement is visible around **94.125 and 98.025**. Combine into one progression and one useful hold.
- **Demo formatting looks unfinished.** The inspected quote frame at **50.7** shows `1610.0000`; the outcome frames around **104.5** show long decimal quantities. Prefer shorter, clean evidence views now; use formatted application values in future recordings.

I did not inspect previous-cut footage, audition audio, test localisation, or perform a new exhaustive privacy audit.

## Prioritised fix list

| Priority | Work | Estimated effort |
|---|---|---:|
| **1** | Repair the two landscape action crops; correct misleading cursor/caption timing | 2–3 hours |
| **2** | Remove listed loading tails and busy-state freezes; hold completed results | 2–3 hours |
| **3** | Enlarge phone/outcome evidence and remove the repeated PO passage | 1–2 hours |
| **4** | Stage the phone → paper → spreadsheet opening with fictional Arabic quotes | Approximately ½ day |
| **5** | Re-record English-locale web and phone scenes with coherent English/bilingual demo data | Approximately ½–1 day, assuming locale readiness |
| **6** | Inspect all four revised exports at action boundaries, including masks after reframing | 1–2 hours plus rendering |

These effort estimates overlap; crop, pacing and caption repairs should be handled together. **No video, recording script or repository file was modified.**