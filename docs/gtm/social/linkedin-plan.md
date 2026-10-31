# LinkedIn plan — founder-led, Egypt pilot push (then KSA)

**Written**: 2026-10-29 · **Account**: Dr. Yasser's personal LinkedIn (people follow people, not a new company page) · **Jira**: PPS-111 (P-81)
**Goal**: one thing only, **conversations with multi-branch F&B owners and purchasing managers in Egypt**. Measure DMs, connection accepts from Sales Pipeline leads, and profile visits. Likes don't count.

## Rules every post follows
- **No results we don't have.** No pilot has run yet. No "saved X%", no customer logos, no "restaurants love it". Product claims stay within what the demo tenant shows, and demo data is labelled as demo data.
- **Same facts as the battlecards and DM script**: quotes arrive by email or upload (WhatsApp photos are forwarded, not pulled in automatically); free 14-day pilot, then EGP 1,500 per branch per month with the 3× guarantee; no Foodics/Supy integration.
- **Never name a competitor or a prospect in a post.** Competitor comparisons stay in the battlecards; prospects stay in the Sales Pipeline.
- **Links go in the first comment**, never the post body (LinkedIn cuts reach for external links).
- **Language**: Arabic posts for owners (Egyptian colloquial, «د. ياسر» voice); English versions for purchasing managers and the investor/tech network. Post the Arabic one; keep the English for a later week or a comment, not both at once.
- **Timing**: Sunday, Tuesday, Thursday, 9–10 AM Cairo. Stay online 30 minutes after posting to answer comments.

## Content pillars

| Pillar | Share | What it is | Why it's credible |
|---|---|---|---|
| **How to buy better** | 40% | Practical checks for comparing quotes: pack size, VAT, delivery, validity | Built into the product (pack units, landed cost, VAT); true without any customer |
| **Building it** | 30% | Real things learned building the product for Egyptian quotes | Every story is in the repo history (currency markers, Arabic digits, date shift) |
| **Questions to buyers** | 20% | Genuine questions about how they buy today | Feeds discovery; answers become future posts |
| **The pilot** | 10% | The free 14-day pilot offer, who it's for | The real offer from the DM script |

## Two-week calendar

| # | Day | Pillar | Post | Visual |
|---|---|---|---|---|
| 1 | Sun wk1 | How to buy better | Three checks before calling a quote the cheapest | Carousel or one image of the 3-quote table |
| 2 | Tue wk1 | Building it | Four ways an Egyptian quote writes "pounds" | Screenshot of the currency-review state, or text only |
| 3 | Thu wk1 | Questions to buyers | How many suppliers do you ask before a big order? | LinkedIn poll |
| 4 | Sun wk2 | Building it | The quote that never expired | Round-7 photo quote + Smart Compare screenshot (`demo-tenant/pps50-quote-expiry/09-smart-compare-oil-en.jpg`, demo data) |
| 5 | Tue wk2 | How to buy better | Price per pack vs price per kilo | Text only |
| 6 | Thu wk2 | The pilot | Looking for 1–2 groups for a free 14-day pilot | Pilot card `whatsapp-card/pilot-card-ar.png` |

Week 3 onward: repeat the pillar mix, turning the best comments and DM answers into posts. Post the demo video once the owner has approved a v2.5 cut for public use (`video/production-tracker.md` 3.7).

## Daily engagement (20 minutes, the part that actually finds pilots)
1. Reply to every comment on your posts, the same day.
2. Comment on 5 posts from target accounts: brand pages and founders of the Warm leads in the Sales Pipeline (SP, label `wave1-egypt`). Add something specific, never "great post".
3. Only after one or two genuine comments, send the connection note from `prospects/2026-10-29-first-messages.md`. Engage first, then connect.
4. Anyone who answers a question post with a real description of how they buy: reply, then DM the "When they reply" message from the DM script, and add them to SP.

---

## Drafts

### Post 1 — Three checks before calling a quote the cheapest

**AR**
> قبل ما تقول إن العرض ده هو الأرخص، اعمل ٣ حاجات. خد مثال زيت الطبخ بتلات عروض:
>
> المورد الأول: كرتونة ١٨ لتر بـ٢٬٠٥٠ جنيه شامل الضريبة، والتوصيل ببلاش.
> المورد التاني: صفيحة ٤ لتر بـ٤٢٠ جنيه من غير ضريبة.
> المورد التالت: كرتونة ١٨ لتر بـ١٬٩٠٠ جنيه من غير ضريبة، والتوصيل ٢٥٠ جنيه على الكرتونة.
>
> التالت شكله الأرخص في الكرتونة، والتاني شكله الأرخص في الرقم. لكن لما تحسب سعر اللتر شامل الضريبة (١٤٪) والتوصيل: الأول ١١٤ جنيه، التاني ١٢٠، التالت ١٣٤. الأغلى في الحقيقة هو اللي كان شكله أرخص كرتونة.
>
> التلات حاجات: قارن بسعر الوحدة مش بسعر العبوة، وحّد الضريبة (شامل أو من غير) قبل المقارنة، وضيف التوصيل على السعر. في الواتساب والإكسل، دي بالظبط الأماكن اللي الفلوس بتضيع فيها.
>
> في فريقكم، أنهي واحدة فيهم بتتنسي أكتر؟

**EN**
> Before you call a quote the cheapest, check three things. Take cooking oil, three quotes:
>
> Supplier A: 18-litre carton, EGP 2,050 including VAT, free delivery.
> Supplier B: 4-litre tin, EGP 420 excluding VAT.
> Supplier C: 18-litre carton, EGP 1,900 excluding VAT, plus EGP 250 delivery per carton.
>
> C looks cheapest per carton and B has the smallest number. Per litre, with Egypt's 14% VAT and delivery added, A is EGP 114, B is 120, and C is 134. The quote that looked cheapest per carton costs the most.
>
> So: compare per unit, not per pack. Put every price on the same VAT basis before comparing. Add delivery to the price. When purchasing runs on WhatsApp and Excel, these are the three places money leaks.
>
> On your team, which of the three gets missed most often?

*Numbers are an illustrative example (A: 2,050 ÷ 18 = 113.9; B: 420 × 1.14 ÷ 4 = 119.7; C: (1,900 × 1.14 + 250) ÷ 18 = 134.2). Say "example" if anyone asks; don't present it as a real supplier.*

### Post 2 — Four ways an Egyptian quote writes "pounds"

**AR**
> وأنا ببني نظام بيقرا عروض أسعار الموردين المصريين، اتعلمت إن الجنيه ليه ٤ أشكال على الأقل: «ج.م»، «جنيه»، «LE»، و«EGP». وأحيانًا الأرقام نفسها مكتوبة بالهندي ١٢٣ مش 123.
>
> في أول نسخة، لما العرض ما يقولش العملة بوضوح، النظام كان بيفترض عملة لوحده. ده غلط: رقم صح بعملة غلط أخطر من رقم ناقص. دلوقتي لو العملة مش واضحة، العرض بيقف ويستنى حد يراجعه بنفسه، بدل ما النظام يخمّن.
>
> القاعدة اللي خرجت بيها: أي حاجة لها علاقة بالفلوس، النظام يسأل ما يخمّنش.

**EN**
> Building a tool that reads Egyptian supplier quotes taught me that the pound has at least four spellings: «ج.م», «جنيه», LE and EGP. Sometimes the digits themselves are Arabic-Indic, ١٢٣ instead of 123.
>
> In an early version, when a quote didn't state its currency clearly, the system assumed one. That was wrong: a correct number in the wrong currency is more dangerous than a missing number. Now, when the currency is unclear, the quote stops and waits for a person to check it.
>
> The rule I took from it: anything to do with money, the software asks instead of guessing.

*True per spec 022 / PR #73: unresolved currency routes to review as `currency_unresolved`.*

### Post 3 — Question (LinkedIn poll)

**AR**
> سؤال لأصحاب المطاعم ومسؤولي المشتريات اللي عندهم أكتر من فرع: قبل طلبية كبيرة، بتطلبوا عرض سعر من كام مورد؟
>
> بسأل لأني بلاقي ناس بتقارن ٣ عروض وناس بتطلب من نفس المورد كل مرة. الاتنين ليهم منطق، وحابب أفهم إيه اللي بيحدد ده عندكم.

Poll options: «مورد واحد ثابت» · «٢–٣ موردين» · «٤ أو أكتر» · «حسب الصنف»

**EN**
> For restaurant owners and purchasing managers running more than one branch: before a big order, how many suppliers do you ask for a quote?
>
> I ask because some teams compare three quotes and others go back to the same supplier every time. Both have reasons, and I'd like to understand what decides it for you.

Poll options: "One regular supplier" · "2–3 suppliers" · "4 or more" · "Depends on the item"

### Post 4 — The quote that never expired

**AR**
> واحد من الأخطاء اللي لقيناها وإحنا بنجرب النظام على عروض أسعار حقيقية الشكل: العرض بيقول «صالح ١١ يوم»، والنظام قرا ده صح، لكن شاشة المقارنة كانت بتعرض العرض «بدون تاريخ انتهاء».
>
> يعني المشتري ممكن يختار سعر انتهى من أسبوع، ويتفاجئ لما المورد يقوله السعر اتغير. دلوقتي تاريخ الانتهاء بيوصل لحد المقارنة، وبيظهر جنب السعر: «صالح حتى ٣ نوفمبر».
>
> في الشغل اليدوي ده بيحصل كتير: سعر من رسالة واتساب قديمة بيفضل في الإكسل شهور. أول سؤال قبل أي مقارنة: العرض ده لسه صالح؟
>
> [صورة: العرض الأصلي (بيانات تجريبية) + شاشة المقارنة «صالح حتى 2026/11/03»]

**EN**
> One bug we found while testing on realistic supplier quotes: the quote said "valid for 11 days", the system read that correctly, and the comparison screen still showed the offer with "no expiry date".
>
> So a buyer could pick a price that had expired a week ago and only find out when the supplier said it had changed. The expiry date now travels all the way to the comparison and sits next to the price: "valid until 3 November".
>
> Manual purchasing does this all the time: a price from an old WhatsApp message lives in the Excel sheet for months. Before any comparison, the first question is whether the quote is still valid.
>
> [image: original quote (demo data) + comparison screen "valid until 2026/11/03"]

*True per PR #255 and `demo-tenant/pps50-quote-expiry/` (screenshot 09 shows the fixed screen). **Don't mention the time-zone date shift** (PPS-55 is still open): a workspace left on UTC shows the expiry one day late. Use only «مطاعم سند» screenshots, which run on Africa/Cairo.*

### Post 5 — Price per pack vs price per kilo

**AR**
> مورد بيبعت الجبنة بالكيلو، والتاني بالكرتونة ٨ كيلو، والتالت بالكرتونة ١٢ عبوة × ٥٠٠ جرام. لو قارنت الأرقام زي ما هي، هتغلط.
>
> اللي بنعمله في النظام: الطلب والسعر بيفضلوا بالعبوة اللي بتشتري بيها فعلًا (الكرتونة)، لكن المقارنة بين الموردين بتتعمل بعد ما الكل يتحوّل لنفس الوحدة. كده الكرتونة تفضل كرتونة في أمر الشراء، والمقارنة تبقى عادلة.
>
> لو بتقارن في إكسل، ضيف عمود واحد بس: السعر ÷ الكمية في العبوة. هيفرق معاك أكتر من أي خصم.

**EN**
> One supplier sells cheese by the kilo, another in an 8 kg carton, a third in a carton of 12 × 500 g packs. Compare those numbers as written and you'll get it wrong.
>
> What we do in the product: orders and prices stay in the pack you actually buy (the carton), and suppliers are compared only after everything is converted to the same base unit. The carton stays a carton on the purchase order, and the comparison is fair.
>
> If you compare in Excel, add one column: price ÷ quantity per pack. It will matter more than any discount.

*True per ADR-020 (quantities and prices per pack; base-unit conversion only for cross-supplier comparison).*

### Post 6 — The pilot

**AR**
> بدوّر على مجموعة أو اتنين من المطاعم في مصر عندهم أكتر من فرع، لتجربة مجانية ١٤ يوم.
>
> المناسب: فرعين أو أكتر (أو فرع ومطبخ مركزي)، بتشتروا كل أسبوع من ٥ موردين أو أكتر، وعروض الأسعار لسه بتتلم يدوي على الواتساب أو التليفون أو الإكسل.
>
> أنا بعمل الإعداد بنفسي على ١٠ لـ٢٠ صنف من اللي بتشتروه. من ناحيتكم مكالمتين ٣٠ دقيقة. وفي الآخر بنقارن بأسعار الشهر اللي فات ونشوف الفرق بالجنيه.
>
> لو ده شبهكم، ابعتلي رسالة.

**EN**
> I'm looking for one or two multi-branch restaurant groups in Egypt for a free 14-day pilot.
>
> A good fit: two or more branches (or one plus a central kitchen), weekly orders from five or more suppliers, and quotes still collected by hand over WhatsApp, phone or Excel.
>
> I do the setup myself on 10 to 20 items you buy every week. Your side is two 30-minute calls. At the end we compare against last month's prices and see the difference in pounds.
>
> If that sounds like you, send me a message.

*Visual*: `whatsapp-card/pilot-card-ar.png` (AR) / `pilot-card-en.png` (EN).

---

## KSA (later, after the prerequisites in PPS-109)
Reuse posts 1, 2 and 5 with Saudi facts: 15% VAT, «ر.س», Gulf register (`gcc/script-saudi.md`), Saudi demo screenshots from «مطاعم رواق». Don't run post 6 until a KSA price and pilot terms exist.

## Weekly review (15 minutes, Thursday)
- Which post brought DMs or connection accepts from SP leads? Write more like it.
- Comments that describe how someone buys today → log in SP if they fit the ICP.
- Drop any pillar that brings likes but no conversations for three weeks.
