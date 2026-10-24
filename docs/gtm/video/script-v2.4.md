# Demo video v2.4 — script (Ledger UI, purchasing-manager cut)

Status 2026-10-24: **draft for the owner's review.** Nothing is recorded until this script is approved.
Written with the `technical-video-script` skill. It replaces the v2.2/v2.3 copy at the owner's request
(2026-10-24), which overrides the "no new script" rule in [`motion-style.md`](motion-style.md) §11 for
this version only. The honesty rules in [`README.md`](README.md) still hold, and so does the motion and
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
buyer's: **no retyping, no chasing, a decision you can defend.**

## Shape

Feature walkthrough, cut as a silent captioned screencast (2–5 min band; the 9:16 cut is its short-form
clip). The effort ceiling allows it because the demo environment already exists and survives a clean
take; the concept and motion-explainer shapes are not needed, because the product is the proof. No
build-along or deep dive: there is no code for this viewer to follow.

## Beats — 16:9

Figures marked **[r6]** come from round 6 and are filled in after recording. The proposed round-6 data is
in the recording brief. Every beat has its own starting state, so any beat can be re-shot alone.

| # | Visual | On-screen action | Copy (AR) | Copy (EN) | Starting state | Est. s | Core / cut |
|---|---|---|---|---|---|---|---|
| **Chapter 1 — The problem, and the result** |||||||
| 0 | Opening animation: supplier quotes piling up on WhatsApp, retyped into Excel with a typo | Existing animation; Converge wipe out (music cue: first downbeat) | «٣ موردين… ٣ صيغ… وشيت بتكتبه بإيدك.» | "Three suppliers. Three formats. One sheet you retype by hand." | `~/Videos/pp-recording/edit/openings/opening-anim-16x9.mp4` | 4 | core |
| 1 | Full-colour plate: the sent PO, then the savings line **[r6]** | Two quick plates, teal hit on the saving; disclosure pill appears | «من بلاغ نقص… لأمر شراء معتمد. في مكان واحد.» | "From a low-stock report to an approved PO. In one place." | Frames from beats 13 and 14 | 6 | core |
| — | Disclosure pill, held from beat 1 to the outro | Mist pill, bottom corner | «تشغيل حقيقي · بيانات تجريبية · دقيقتين» | "Real run · demo data · 2 minutes" | — | 0 | core |
| **Chapter 2 — One RFQ to every supplier** |||||||
| 2 | Phone frame: branch user reports oil low at Maadi (1 left) | Tap «الإبلاغ عن انخفاض المخزون», pick oil, send; confirmation | «الفرع بيبلّغ من الموبايل: الزيت قرب يخلص.» | "The branch reports it from the phone: oil is running low." | Phone web build signed in as the owner, home screen; no open report for oil at Maadi | 7 | core |
| 3 | Web: new RFQ, three lines in packs, three suppliers, needed-by date | Add lines, tick suppliers, set date, press Send; status chip changes shape | «طلب عرض سعر واحد… لـ٣ موردين، والكميات بالعبوة.» | "One RFQ. Three suppliers. Quantities in packs." | Web signed in, `/rfq/new` empty, sidebar hidden | 11 | core |
| 4 | Supplier's inbox: the RFQ email in Arabic with the buyer's terms | Single plate, slow push-in | «كل مورد يوصله إيميل بالعربي، بشروطك.» | "Each supplier gets an email in Arabic, with your terms." | One sent RFQ email open in a supplier alias in Gmail (owner's address cropped out) | 4 | **cut** |
| **Chapter 3 — Quotes read themselves; you sign off** |||||||
| 5 | Web inbox: three replies, each attributed to its supplier: PDF, PDF, WhatsApp photo | Rows land one by one (staggered) | «٣ ردود: ملفين PDF… وصورة واتساب.» | "Three replies: two PDFs and a WhatsApp photo." | All three replies ingested, none opened | 5 | core |
| 6 | Quote review: the photo beside the extracted lines; EGP, expiry, total | Zoom on the lines, then hold on the reconciled total (1.5 s hold) | «اتقرت لوحدها: البنود، بالجنيه، والصلاحية… والإجمالي مطابق.» | "Read automatically: lines, pounds, expiry. The total checks out." | Photo quote open, not yet authorised | 12 | core |
| 7 | Same screen, the confirm panel and Authorise | Press Authorise; the chip turns to the approved shape | «بس الاعتماد قرارك إنت.» | "But you sign it off." | Photo quote open, fields confirmed | 5 | core |
| **Chapter 4 — Compare like for like** |||||||
| 8 | Smart Compare, oil × 8: per pack and landed, the recommended supplier marked | Teal bar overtakes the navy bar (Converge motif); hold on the gap | «مقارنة بالعبوة وبالتكلفة الواصلة: الأمانة أوفر بـ**[r6]** ج.م» | "Per pack, landed cost: Al-Amana is cheaper by EGP **[r6]**." | All three quotes authorised; `/compare` for oil | 11 | core |
| 9 | Basket split result across suppliers | Single plate | «أو قسّم الطلب على أكتر من مورد.» | "Or split the order across suppliers." | A basket split already run on round 6 | 5 | **cut** |
| **Chapter 5 — Rules draft it, a manager approves** |||||||
| 10 | Draft request with the guardrail banner, cost centre, total under the limit | Push-in to the banner, then Submit | «الضوابط اللي حطّيتها جهّزت الطلب… مسودة، مش شراء.» | "Your guardrails drafted the request. A draft, not a purchase." | Guardrail draft from round 6 open, not submitted | 10 | core |
| 11 | Phone frame: the manager opens the request and approves | Tap Approve; confirmation | «والمدير يعتمد من موبايله.» | "The manager approves from their phone." | Request submitted; phone build on the approvals list | 8 | core |
| **Chapter 6 — Order it, prove the saving** |||||||
| 12 | Web: PO generated from the approved request, then sent | Create PO, then Send; chip shape changes | «أمر الشراء طالع من الطلب المعتمد… واتبعت.» | "The PO comes from the approved request, and goes out." | Approved request open, no PO yet | 9 | core |
| 13 | Record outcome from the PO; savings per line against the last PO price | Counter rolls to the saving; teal hit | «وفّرت **[r6]** ج.م على الطلب ده، مقابل آخر سعر شراء.» | "You saved EGP **[r6]** on this order, against the last purchase price." | PO sent, outcome not recorded | 7 | core |
| 14 | Savings ledger, verified total, sidebar visible | Hold on the total (1.5 s) | «وكل وفر متسجّل ومتراجع… جاهز للمالك.» | "Every saving logged and verified, ready for the owner." | The round's savings verified as the owner | 6 | core |
| 15 | Outro: logo sting, end card | Existing renders | (existing) | (existing) | `renders/outro-16x9.mp4` / `-en.mp4` | 9.75 | core |

## Beats — 9:16 (60 s)

The same beats, re-cropped; captions are burned in and kept out of the top ~250 px and bottom ~350 px
(platform UI). It ends on the outro, as every cut so far does.

| # | From 16:9 beat | Treatment | Est. s |
|---|---|---|---|
| 0 | 0 | `opening-anim-9x16.mp4` | 3 |
| 1 | 1 | saving plate, crop on the figure | 4 |
| 2 | 3 | crop on the supplier list and Send | 6 |
| 3 | 5 + 6 | inbox rows, then the photo and lines, stacked | 10 |
| 4 | 7 | crop on Authorise and the chip | 3 |
| 5 | 8 | crop on the bars and the gap | 7 |
| 6 | 10 | crop on the guardrail banner | 5 |
| 7 | 11 | phone full height | 5 |
| 8 | 12 | crop on the PO status chip | 4 |
| 9 | 13 | counter | 4 |
| 10 | 15 | `renders/outro-9x16.mp4` / `-en.mp4` | 8.5 |
| | | **Total** | **59.5** |

## Chapters (16:9, for YouTube and LinkedIn)

```
00:00 Three suppliers, three formats, one spreadsheet
00:10 One RFQ to every supplier
00:32 Quotes read themselves, you sign off
00:54 Compare like for like
01:10 Guardrails draft it, a manager approves
01:28 Order it and prove the saving
```

Timecodes are from the runtime estimate and get corrected after the edit. Every chapter is at least 10 s.
The 9:16 cut has no chapters.

## Cut plan

If the edit overruns, cut in this order:

1. Beat 9 (basket split), −5 s
2. Beat 4 (supplier email), −4 s
3. Beat 2 trimmed to 4 s (start at the confirmation), −3 s
4. Beat 14 merged into beat 13 (ledger total as a second line under the counter), −6 s

With all four cuts the promise still holds: request, read, compare, approve, order, saving.

## Runtime

Silent cut, so the budget is reading time plus action time, not speech. Each caption is 6–12 words; at
~2.5 words/s reading speed that is 3–5 s, and every beat's action time is longer than its caption, so
action time sets the length.

| | Est. |
|---|---|
| Core beats 0–14 (without 4 and 9) | 101 s |
| Cuttable beats 4 and 9 | 9 s |
| Outro | 9.75 s |
| **16:9 total** | **1:51 core, 2:00 with the cuttable beats** (target ~2:00) |
| **9:16 total** | 59.5 s (target ≤ 60 s) |

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
وصور الواتساب، مقارنة بالعبوة، اعتماد من الموبايل، وأمر شراء بالوفر متسجّل. تشغيل حقيقي ببيانات تجريبية.
جرّبه أسبوعين مجانًا — كلّمنا واتساب ‎+20 102 735 4140»

EN: "ProcurePilot for restaurant purchasing managers: one RFQ to every supplier, quotes read from PDFs and
WhatsApp photos, per-pack comparison, approval from the phone, and a PO with the saving logged. A real run
on demo data. Try it free for two weeks: WhatsApp +20 102 735 4140."

## Pass threshold (skill gates)

| Gate | Status |
|---|---|
| 1. One-sentence promise, delivered inside 30 s | ✅ beat 1 shows the PO and the saving by 0:10 |
| 2. Every beat has a re-shootable starting state | ✅ |
| 3. Copy reads on its own, with no "as you can see" | ✅ every caption names the thing |
| 4. Runtime includes action time and lands on target | ✅ 1:51–2:00 / 59.5 s |
| 5. Every chapter titled, ≥ 10 s | ✅ six chapters, shortest 16 s |
| 6. Core/cut marked, and the core alone delivers the promise | ✅ |
| 7. Every claim reproducible on hosted | ⏳ the [r6] figures are filled from the recording |

## After publishing

Read intro retention at 30 s and where viewers drop, mapped to these beat numbers, against the v2.x cuts
of the same shape.
