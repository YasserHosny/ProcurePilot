# Cold email sequence — first pilot (Egypt, then KSA)

**Written**: 2026-10-28 · **For**: Dr. Yasser, founder-led outreach · **Jira**: PPS-107 (P-77)
**Sits beside**: the approved [Outreach DM Script](https://claude.ai/code/artifact/30523eee-168f-4a1c-b7ac-dcb50cd9ded8) (WhatsApp and LinkedIn). Same question, same price, same tone.

## When to use email at all

In Egypt, WhatsApp and personal introductions beat cold email (`first-customer-gtm-plan.md`, Phase 1). Use this sequence only where the DM script can't reach:

| Use email when… | Don't |
|---|---|
| The group has a **named purchasing or operations manager** with a company address (common in groups of 5+ branches, and in KSA) | Small owner-run groups: WhatsApp them instead |
| You found them through a website, an expo list or a LinkedIn profile that shows a work email | You have a mutual contact: ask for the intro (DM script §2) |
| The prospect is in **KSA**, where work email is the normal first touch for procurement | You can't verify the address |

Target per week: 15–25 hand-written emails. This is founder outreach, not volume.

## Before the first send (one-time)

- [ ] **Sending domain**: don't send cold email from `iron-sys.com` (your main domain, which carries your Zoho mail). Register one look-alike domain (~$10/yr, e.g. `procurepilot-mail.com`; **owner decision, costs money**), set SPF, DKIM and DMARC, and warm the mailbox for 3–4 weeks before cold sends.
- [ ] **Verify every address** before sending; keep bounces under 2%.
- [ ] **Open and click tracking off.** Count replies.
- [ ] **Footer on every email**: plain-text opt-out line plus a postal address. *Needs the company's registered address (see `company-formation/`); don't send until it exists.*
- [ ] Plain text, **one link at most**. Attach the one-pager PDF only in email 2 or after a reply.

## Sequence (4 emails, 14 days)

| # | Day | Angle | Ask |
|---|---|---|---|
| 1 | 0 | How do you collect supplier quotes today? (diagnostic) | One-line reply |
| 2 | 3 | What the comparison looks like, with the one-pager | "Worth 15 minutes?" |
| 3 | 7 | The pilot offer: free 14 days, I do the setup | Yes or no |
| 4 | 14 | Breakup | None |

A reply on **any** channel (email, WhatsApp, LinkedIn) stops the sequence. Log every touch in the Sales Pipeline (SP): one Lead per company, a comment per email, the due date set to the next step.

Fill-ins: `[الاسم]/[Name]`, `[الشركة]/[Company]`, `[عدد]/[n]` branches, `[ملاحظة]/[observation]` = one specific thing you saw (a new branch opening, a hiring post for a purchasing role, their menu size).

---

### Email 1 — day 0

**Subject**: `عروض الموردين` / `supplier quotes`

**AR**
> أهلًا أستاذ [الاسم]،
>
> [ملاحظة: مثلًا «شفت إن [الشركة] فتحت فرع في التجمع الشهر ده»]. مع [عدد] فروع، أكيد في حد عندكم بيلم عروض أسعار من موردين كتير كل أسبوع.
>
> سؤال واحد بس: العروض دي بتوصلكم إزاي، وبتقارنوها فين؟ واتساب وإكسل، ولا عندكم سيستم؟
>
> بسأل لأني ببني أداة لده بالظبط لسلاسل المطاعم في مصر، وعايز أفهم الواقع قبل ما أعرض حاجة.
>
> د. ياسر حسني

**EN**
> Hi [Name],
>
> [Observation, e.g. "Saw [Company] opened a branch in New Cairo this month"]. With [n] branches, someone on your team is probably collecting quotes from a lot of suppliers every week.
>
> One question: how do those quotes reach you, and where do you compare them? WhatsApp and Excel, or a system?
>
> I'm asking because I'm building a tool for exactly this for restaurant groups in Egypt, and I want to understand how it really works before I show anyone anything.
>
> Dr. Yasser Hosny

*Why this works*: it's the same diagnostic question as the DM script, asks for one line, and doesn't pitch. If the observation could be removed and the email still made sense, find a better observation.

### Email 2 — day 3

**Subject**: `مقارنة العروض` / `comparing quotes`

**AR**
> أهلًا أستاذ [الاسم]،
>
> بكمّل على سؤالي. في مطاعم كتير، المورد بيبعت السعر صورة على الواتساب، وحد بينقله في إكسل، والمقارنة بتاخد وقت.
>
> اللي بنعمله: تبعت طلب العرض مرة واحدة، والعروض توصل (صورة أو PDF أو إيميل) تتقري لوحدها وتتحط جنب بعض بند ببند، وتعرف مين الأرخص قبل ما تطلب. مرفق صفحة واحدة توضح الفرق.
>
> تستاهل ١٥ دقيقة أوريك على مثال زي بتاعكم؟
>
> د. ياسر

**EN**
> Hi [Name],
>
> Following up on my question. In a lot of restaurant groups, suppliers send prices as a WhatsApp photo, someone retypes them into Excel, and the comparison eats time.
>
> With ProcurePilot you send the request once. Quotes that come back as a photo, PDF or email are read automatically and lined up item by item, so you know who's cheapest before you order. The attached one-pager shows the before and after.
>
> Worth 15 minutes to see it on an example like yours?
>
> Dr. Yasser

*Attach*: `one-pager/ProcurePilot-one-pager.pdf`. Once the demo video is ready, link it instead. Check before sending: photo and PDF extraction is live; WhatsApp still needs a forward or an upload (don't imply the quotes arrive from WhatsApp automatically).

### Email 3 — day 7

**Subject**: `تجربة أسبوعين` / `two-week trial`

**AR**
> أهلًا أستاذ [الاسم]،
>
> عرض واضح: تجربة مجانية ١٤ يوم على ١٠ لـ٢٠ صنف من اللي بتشتروه كل أسبوع. أنا بعمل الإعداد بنفسي، ومن ناحيتكم مكالمتين ٣٠ دقيقة بس. في الآخر بنقارن بأسعار الشهر اللي فات ونعرف التوفير بالجنيه.
>
> لو مش مناسب دلوقتي، رد بـ«لأ» وهفهم.
>
> د. ياسر

**EN**
> Hi [Name],
>
> A concrete offer: a free 14-day trial on 10 to 20 items you buy every week. I do the setup myself; your side is two 30-minute calls. At the end we compare against last month's prices and put the saving in pounds.
>
> If it's not a fit right now, just reply "no" and I'll understand.
>
> Dr. Yasser

*Only send email 3* if the company plausibly meets the five pilot criteria (2+ branches, 5+ suppliers, weekly orders, manual quotes, a named decision-maker).

### Email 4 — day 14 (breakup)

**Subject**: `آخر رسالة` / `last note`

**AR**
> أهلًا أستاذ [الاسم]،
>
> دي آخر رسالة مني عشان ما أزحمش الإيميل. لو المشتريات مش أولوية دلوقتي، تمام جدًا. ولو حبيت ترجع للموضوع بعدين، رقمي تحت.
>
> د. ياسر · [رقم الموبايل]

**EN**
> Hi [Name],
>
> Last note so I don't crowd your inbox. If purchasing isn't a priority right now, no problem at all. If you want to come back to it later, my number is below.
>
> Dr. Yasser · [mobile]

Then move the Lead to **Not now**, reason "silent after sequence". Re-contact only on a new signal.

---

## Variants: when you know their current tool

Swap the **second paragraph of email 2** for one of these. They come from the [battlecards](../battlecards/README.md); keep to their "do not say" lines.

| They use | AR | EN |
|---|---|---|
| **Supy** | «شفت إنكم شغالين على Supy للمخزون. سؤالي عن الخطوة اللي قبل الطلبية: لما تحبوا تقارنوا أسعار كذا مورد، بيحصل فين؟» | "I see you run Supy for stock. My question is about the step before the order: when you want to compare several suppliers' prices, where does that happen?" |
| **Suplyd** | «لو بتطلبوا جزء من البضاعة من Suplyd، الفكرة إن سعرهم يبقى عرض من ضمن عروض، جنب الموردين بتوعكم، قبل ما تطلبوا.» | "If you order some of your goods through Suplyd, the idea is to put their price next to your own suppliers' quotes before you order." |
| **Foodics** | «Foodics بيسجل الشراء. إحنا في الخطوة اللي قبلها: تجميع العروض ومقارنتها.» | "Foodics records the purchase. We're the step before it: collecting and comparing the quotes." |

## KSA adaptation (after Egypt)

- Language: formal, Gulf-leaning Arabic. Reuse the register of `gcc/script-saudi.md`. Open with «السلام عليكم أستاذ [الاسم]».
- Money: SAR. **KSA pricing isn't set.** Don't quote a price; say "free 14-day trial" only.
- Supy is the most likely incumbent in KSA: lead with the Supy variant when their stack is unknown but they're a 10+ branch group.
- Send Sunday to Thursday, mornings Riyadh time.

## When they reply

| Reply | Do |
|---|---|
| Answers the question | Within hours: reflect it back in one line + two concrete times for 15 minutes (DM script, "When they reply"). Move to **Talked** only after the call. |
| "Send more info" | One-pager + one line: "Happy to walk you through it in 15 minutes, [day] or [day]?" |
| Objection | Use the DM script's objection table (price: free 14 days, then EGP 1,500 per branch per month, with the 3× guarantee) or the battlecard for their tool. |
| "Not now" | Ask which month to check back; set the SP due date to it. |
| Referral to a colleague | Thank them, email the colleague the same day and name the referrer in line one. |
| Unsubscribe | Remove them everywhere the same day. No reply needed. |

## What to measure

Positive reply rate per 20 emails sent, and calls booked. After 40 sends, compare subject and observation variants; change one thing at a time.
