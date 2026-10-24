# Demo video v2.4 — script (Ledger UI, purchasing-manager cut)

Status 2026-10-24: **approved by the owner; round 6 (Arabic UI) recorded** ([record](../../../demo-tenant/round-6/README.md)): compare 12,600 vs 12,800, saving EGP 300, ledger EGP 1,560. Round 7 (English UI) recorded the same evening ([record](../../../demo-tenant/round-7/README.md)): compare 12,480 vs 12,680, saving EGP 200, ledger EGP 1,760.

Revision 2026-10-25 (PPS-59), **draft for the owner's approval**: copy only, footage unchanged. The owner found
that the cut jumped from the viewer's pain (beat 0) to the result (beat 1) without saying that the
product, and each feature after it, answers that pain. Codex agreed and reviewed the rest of the copy.
Changes:

- Beat 1 now names the product before showing the result (the bridge).
- Each chapter opens on a short pain card, then the fix. ` / ` in a caption cell marks a card break.
- The promise drops "no chasing": the video shows one RFQ sent, not suppliers answering without a reminder.
- Arabic uses «توفير» / «توفيرات», not «وفر» / «وفورات», which Egyptian buyers do not use (owner, 2026-10-25).
- Factual fixes: the English RFQ email (beat 4) was in English, not Arabic; beat 1 says *sent* PO (the
  manager approves the request, not the PO); landed cost is named as VAT and delivery included; the
  EGP 200 supplier gap and the order saving are labelled so they don't read as the same figure.
- Beat 9 (basket split) is dropped: its "or" leaves the single purchasing journey.

Written with the `technical-video-script` skill. It replaces the v2.2/v2.3 copy at the owner's request
(2026-10-24), which overrides the "no new script" rule in [`motion-style.md`](../../motion-style.md) §11 for
this version only. The honesty rules in [`README.md`](../../README.md) still hold, and so does the motion and
brand direction.

## Decisions (owner, 2026-10-24)

| Question | Answer |
|---|---|
| Viewer | **Purchasing manager** at an Egyptian restaurant group: runs quotes, comparisons and orders every day; reports savings to the owner |
| Footage | A **fresh round 6** on hosted «مطاعم سند», recorded in the Ledger design system (#235, live since 2026-10-24 11:35) |
| Look | v2.3 brand editorial engine (kinetic type, Converge wipes, official logo), but app footage as **full-colour plates**, not navy duotone: the UI now carries the brand palette itself |
| Sound | Text + music only, as before (autoplay is muted on WhatsApp, LinkedIn and Reels). The "Copy" columns below are the on-screen kinetic text, not a voice-over |
| Formats | Arabic and English, 16:9 (~2:00 with outro) and 9:16 (~60 s) |

## Promise

For a purchasing manager, this video shows one low-stock report becoming an RFQ to three suppliers,
quotes read without retyping, a like-for-like comparison, a manager's approval and a sent PO, with the
saving recorded, all in the real product.

The v2.x promise was the owner's ("you're buying anyway, we show you what you save"). This one is the
buyer's: **quotes without retyping, a fair comparison, a decision you can defend.**
AR: «عروض من غير ما تكتبها بإيدك، مقارنة عادلة، وقرار تقدر تدافع عنه.»

## Story

Every chapter answers one pain the viewer already has. The pain card comes first (≤ 6 words, ~2.5 s,
over the opening frames of the chapter's first beat), then the fix caption over the action.

| Chapter | Pain (card) | Fix (what the footage proves) |
|---|---|---|
| 1 | Retyping three suppliers' formats by hand | ProcurePilot: report to sent PO, saving logged |
| 2 | Sending the same request to each supplier | One RFQ to three suppliers, quantities in packs |
| 3 | Retyping prices from PDFs and photos | Lines read automatically; a human signs off |
| 4 | Prices in different pack sizes | Per pack, VAT and delivery included |
| 5 | Requests stuck waiting for approval | Guardrails draft it; the manager approves by phone |
| 6 | The owner asks what was saved | Saving against the last PO price, verified in the ledger |

## Shape

Feature walkthrough, cut as a silent captioned screencast (2–5 min band; the 9:16 cut is its short-form
clip). The effort ceiling allows it because the demo environment already exists and survives a clean
take; the concept and motion-explainer shapes are not needed, because the product is the proof. No
build-along or deep dive: there is no code for this viewer to follow.

## Beats — 16:9

Figures come from rounds 6 (AR) and 7 (EN). Every beat has its own starting state, so any beat can be
re-shot alone. ` / ` splits a caption into two cards: the pain card, then the fix.

| # | Visual | On-screen action | Copy (AR) | Copy (EN) | Starting state | Est. s | Core / cut |
|---|---|---|---|---|---|---|---|
| **Chapter 1 — The problem, and the result** |||||||
| 0 | Opening animation: supplier quotes piling up on WhatsApp, retyped into Excel with a typo | Existing animation; Converge wipe out (music cue: first downbeat) | «٣ موردين… ٣ صيغ… وكل سعر بتكتبه بإيدك.» | "Three suppliers. Three formats. Every price retyped by hand." | `~/Videos/pp-recording/edit/openings/opening-anim-16x9.mp4` | 4 | core |
| 1 | Bridge: the scattered quote sheets fly into the product frame (logo), then full-colour plates of the sent PO and the saving | Sheets converge into the app header; two quick plates, teal hit on the saving; disclosure pill appears | «ProcurePilot لمشتريات المطاعم / من بلاغ نقص لأمر شراء متبعت… والتوفير متسجّل.» | "ProcurePilot, for restaurant purchasing / From a low-stock report to a sent PO, with the saving logged." | Frames from beats 13 and 14 | 8 | core |
| — | Disclosure pill, held from beat 1 to the outro | Mist pill, bottom corner | «تشغيل حقيقي · بيانات تجريبية · دقيقتين» | "Real run · demo data · 2 minutes" | — | 0 | core |
| **Chapter 2 — One RFQ to every supplier** |||||||
| 2 | Phone frame: branch user reports oil low at Maadi (1 left) | Tap «الإبلاغ عن انخفاض المخزون», pick oil, send; confirmation | «الفرع بيبلّغ من الموبايل: الزيت قرب يخلص.» | "The branch reports it from the phone: oil is running low." | Phone web build signed in as the owner, home screen; no open report for oil at Maadi | 7 | core |
| 3 | Web: new RFQ, three lines in packs, three suppliers, needed-by date | Pain card over the empty form; add lines, tick suppliers, set date, press Send; status chip changes shape | «بتبعت نفس الطلب لكل مورد لوحده؟ / طلب عرض سعر واحد لـ٣ موردين، والكميات بالعبوة.» | "Sending the same request to every supplier? / One RFQ to three suppliers, quantities in packs." | Web signed in, `/rfq/new` empty, sidebar hidden | 11 | core |
| 4 | Supplier's inbox: the RFQ email with the buyer's terms | Single plate, slow push-in | «كل مورد يوصله إيميل بكمياتك وشروطك.» | "Each supplier gets an email with your quantities and terms." | One sent RFQ email open in a supplier alias in Gmail (owner's address cropped out) | 4 | **cut** |
| **Chapter 3 — Quotes read themselves; you sign off** |||||||
| 5 | Web inbox: three replies, each attributed to its supplier: PDF, PDF, WhatsApp photo | Pain card, then rows land one by one (staggered) | «بتنقل الأسعار بإيدك؟ / ٣ ردود: ملفين PDF وصورة واتساب.» | "Retyping prices by hand? / Three replies: two PDFs and a WhatsApp photo." | All three replies ingested, none opened | 5 | core |
| 6 | Quote review: the photo beside the extracted lines; EGP, expiry, total | Zoom on the lines, then hold on the reconciled total (1.5 s hold) | «البنود والأسعار بالجنيه وتاريخ الصلاحية اتقروا لوحدهم… والإجمالي مطابق.» | "Items, EGP prices and validity, read automatically. The total checks out." | Photo quote open, not yet authorised | 12 | core |
| 7 | Same screen, the confirm panel and Authorise | Press Authorise; the chip turns to the approved shape | «من غير ما تكتب حاجة… بس الاعتماد قرارك إنت.» | "Nothing retyped. But you sign it off." | Photo quote open, fields confirmed | 5 | core |
| **Chapter 4 — Compare like for like** |||||||
| 8 | Smart Compare, oil × 8: per pack and landed, the recommended supplier marked | Pain card, then the teal bar overtakes the navy bar (Converge motif); hold on the gap | «عبوات مختلفة؟ / بالعبوة وشامل الضريبة والتوصيل: الأمانة أرخص بـ٢٠٠ ج.م في الزيت.» | "Different pack sizes? / Per pack, VAT and delivery included: Al-Amana is EGP 200 cheaper on oil." | All three quotes authorised; `/compare` for oil | 11 | core |
| 9 | Basket split result across suppliers | Single plate | «أو قسّم الطلب على أكتر من مورد.» | "Or split the order across suppliers." | A basket split already run on round 6 | 0 | **dropped** (2026-10-25) |
| **Chapter 5 — Rules draft it, a manager approves** |||||||
| 10 | Draft request with the guardrail banner, cost centre, total under the limit | Pain card, then push-in to the banner, then Submit | «الطلب واقف مستني اعتماد؟ / الضوابط اللي حطّيتها جهّزت الطلب… مسودة، مش شراء.» | "Requests stuck waiting for approval? / Your guardrails drafted the request. A draft, not a purchase." | Guardrail draft from round 6 open, not submitted | 10 | core |
| 11 | Phone frame: the manager opens the request and approves | Tap Approve; confirmation | «والمدير يعتمد من موبايله، من أي مكان.» | "The manager approves from their phone, wherever they are." | Request submitted; phone build on the approvals list | 8 | core |
| **Chapter 6 — Order it, prove the saving** |||||||
| 12 | Web: PO generated from the approved request, then sent | Create PO, then Send; chip shape changes | «من الطلب المعتمد بتطلّع أمر الشراء وتبعته.» | "From the approved request, you create the PO and send it." | Approved request open, no PO yet | 9 | core |
| 13 | Record outcome from the PO; savings per line against the last PO price | Pain card, then the counter rolls to the saving; teal hit | «المالك بيسأل: وفّرنا كام؟ / توفير ٣٠٠ ج.م على الطلب ده، مقابل آخر سعر شراء.» | "The owner asks: what did we save? / EGP 200 saved on this order, against the last purchase price." | PO sent, outcome not recorded | 7 | core |
| 14 | Savings ledger, verified total, sidebar visible | Hold on the total (1.5 s) | «وكل توفير متسجّل ومعتمد… جاهز للمالك.» | "Every saving logged and verified, ready for the owner." | The round's savings verified as the owner | 6 | core |
| 15 | Outro: logo sting, end card | Existing renders | (existing) | (existing) | `renders/outro-16x9.mp4` / `-en.mp4` | 9.75 | core |

## Beats — 9:16 (60 s)

The same beats, re-cropped; captions are burned in and kept out of the top ~250 px and bottom ~350 px
(platform UI). It ends on the outro, as every cut so far does. There is no time for pain cards here:
the 9:16 cut shows the **fix card only**, except beat 1 (the product name, then the saving) and beat 13
(the owner's question is the hook for the last shot).

| # | From 16:9 beat | Treatment | Est. s |
|---|---|---|---|
| 0 | 0 | `opening-anim-9x16.mp4` | 3 |
| 1 | 1 | name card, then the saving plate, crop on the figure | 4 |
| 2 | 3 | crop on the supplier list and Send | 6 |
| 3 | 5 + 6 | inbox rows, then the photo and lines, stacked | 10 |
| 4 | 7 | crop on Authorise and the chip | 3 |
| 5 | 8 | crop on the bars and the gap | 7 |
| 6 | 10 | crop on the guardrail banner | 5 |
| 7 | 11 | phone full height | 5 |
| 8 | 12 | crop on the PO status chip | 4 |
| 9 | 13 | owner's question, then the counter | 4 |
| 10 | 15 | `renders/outro-9x16.mp4` / `-en.mp4` | 8.5 |
| | | **Total** | **59.5** |

## Chapters (16:9, for YouTube and LinkedIn)

```
00:00 Three suppliers, three formats, one spreadsheet
00:12 One RFQ to every supplier
00:34 Quotes read themselves, you sign off
00:56 Compare like for like
01:07 Guardrails draft it, a manager approves
01:25 Order it and prove the saving
```

Timecodes are from the runtime estimate (with beat 4) and get corrected after the edit. Every chapter is
at least 10 s; the shortest is chapter 4, 11 s. The 9:16 cut has no chapters.

## Cut plan

If the edit overruns, cut in this order:

1. Beat 4 (supplier email), −4 s
2. Beat 2 trimmed to 4 s (start at the confirmation), −3 s
3. Beat 14 merged into beat 13 (ledger total as a second line under the counter), −6 s

Never cut a pain card: the cards carry the story. With all three cuts the promise still holds: request,
read, compare, approve, order, saving.

## Runtime

Silent cut, so the budget is reading time plus action time, not speech. Fix captions run 5–14 words
(3–5.5 s at ~2.5 words/s); pain cards are 2–6 words and get ~2.5 s over the chapter's opening frames,
before the action starts. The UI competes for attention, so each caption holds until the reveal has
settled, not just for its reading time.

| | Est. |
|---|---|
| Core beats 0–14 (without 4 and 9) | 103 s |
| Cuttable beat 4 | 4 s |
| Outro | 9.75 s |
| **16:9 total** | **1:53 core, 1:57 with beat 4** (target ~2:00) |
| **9:16 total** | 59.5 s (target ≤ 60 s) |

Beat 1 grew from 6 to 8 s for the bridge; dropping beat 9 (5 s) pays for it.

## Recording brief

### Round 6 (Arabic UI) and round 7 (English UI)

The English cuts need the English interface (owner, 2026-10-20), and action beats only happen once per
record, so the English version needs its own round 7 with the same steps. Same data shape, slightly
different prices, so each round still saves against the previous round's PO prices.

Proposed round-6 data: the same three suppliers and items as rounds 4–5, so the story stays familiar.
Round 5's PO prices (الأمانة: oil 1,595 · rice 905 · onions 16.50) are now the "last PO price" baseline.

| Supplier | Channel | Lines | Total |
|---|---|---|---|
| الأمانة | WhatsApp photo of a printed quote | oil ×8 @ 1,575 · rice ×12 @ 895 · onions 80 kg @ 16.25 | 24,640 ج.م |
| النور | PDF | oil ×8 @ 1,600 · rice ×12 @ 910 | 23,720 ج.م |
| الحاج سيد | PDF | onions 80 kg @ 16.75 | 1,340 ج.م |

Expected on screen: Smart Compare oil × 8 at 12,600 vs 12,800; guardrail draft 24,640 (under the
30,000 limit); saving against the last PO price oil +160 · rice +120 · onions +20 = **EGP 300**. These
are proposals; the video uses whatever hosted actually shows.

### Starting states

Per beat, in the tables above. Common to all beats:

- Kiosk Chrome profile `~/.pp-recorder-profile`, `--remote-debugging-port=9333`, 1920×1080; the owner signs
  in. Claude never types passwords or submits the sign-in form.
- Light theme (dark mode is not built yet). Sidebar hidden except in beats 1 and 14.
- Phone: the Flutter web build at 390×844 via `phone-driver.cjs`, signed in by the owner.
- Capture by tab over CDP (`source/opening/assemble.py`), as in round 5; it doesn't depend on where the
  window lands under Wayland.

### What must stay off screen

- The owner's email (quote review «رُفع بواسطة» / «راجعه», the request page, the phone «مقدم الطلب»):
  masked at source, then checked with `verify_output_masks.py`. No unmasked "before" proof images in git.
- Gmail beyond one RFQ email (beat 4): no inbox list, no addresses.
- Any other tenant, any test tenant, the hosted database URL.
- Smart Compare's validity line: both rounds show «no expiry» / "Open-ended" although the quote states
  03/11/2026. PPS-50 (#255) fixed this for new quotes, but rows already priced stay open-ended, so keep the
  line out of frame in beat 8 (or re-shoot that beat on a fresh quote). It undercuts a trust story.

### Honesty notes for the edit

- The WhatsApp photo reached ProcurePilot as an email attachment. The motion must not suggest a direct
  WhatsApp integration (no WhatsApp logo flying into the app).
- The manager approves the **request**; the PO is generated and sent after it. Captions say so (beats 1, 11, 12).

### Show the new design (check on hosted before each take)

- Status chips that change **shape** with status (RFQ sent, quote approved, PO sent): beats 3, 7 and 12.
- Tabular figures in Noto Kufi on money columns: beats 6, 8 and 13.
- The Converge logo in the app header: beat 1.
- The double rule under verified totals and the source stamp on extracted figures are in the design system;
  show them only if hosted actually renders them (not confirmed in #235).

### Supplier replies

Each batch of Gmail replies is sent only after the owner's OK for that batch, as in rounds 4–5.

### Description (16:9, one call to action)

AR: «ProcurePilot لمديري المشتريات في المطاعم: طلب عرض سعر واحد لكل الموردين، عروض بتتقري لوحدها من PDF
وصور الواتساب، مقارنة بالعبوة، اعتماد من الموبايل، وأمر شراء والتوفير متسجّل. تشغيل حقيقي ببيانات تجريبية.
جرّبه أسبوعين مجانًا — كلّمنا واتساب ‎+20 102 735 4140»

EN: "ProcurePilot for restaurant purchasing managers: one RFQ to every supplier, quotes read from PDFs and
WhatsApp photos, per-pack comparison, approval from the phone, and a PO with the saving logged. A real run
on demo data. Try it free for two weeks: WhatsApp +20 102 735 4140."

## Pass threshold (skill gates)

| Gate | Status |
|---|---|
| 1. One-sentence promise, delivered inside 30 s | ✅ beat 1 names the product and shows the PO and the saving by 0:12 |
| 2. Every beat has a re-shootable starting state | ✅ |
| 3. Copy reads on its own, with no "as you can see" | ✅ every caption names the thing; every chapter names the pain it answers |
| 4. Runtime includes action time and lands on target | ✅ 1:53–1:57 / 59.5 s |
| 5. Every chapter titled, ≥ 10 s | ✅ six chapters, shortest 11 s |
| 6. Core/cut marked, and the core alone delivers the promise | ✅ |
| 7. Every claim reproducible on hosted | ✅ figures from rounds 6 (AR) and 7 (EN) |

## Before re-rendering

[`make_data.py`](../../source/edit-v2.4/make_data.py) reads one caption per beat. For this revision it
must split a cell on ` / ` into a pain card and a fix card, give the pain card ~2.5 s over the beat's
opening frames, and skip beat 9 (0 s). The 9:16 spec keeps only the fix card, except beats 1 and 13.

## After publishing

Read intro retention at 30 s and where viewers drop, mapped to these beat numbers, against the v2.x cuts
of the same shape.
