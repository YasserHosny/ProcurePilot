# ProcurePilot WhatsApp kit

**Draft for Yasser's review, 2026-11-07. You send every message; Claude contacts nobody.**
**In the repo since 2026-11-13 (Yasser):** this folder is committed, and the repo is public. The `videos/` folder and `ProcurePilot-whatsapp-kit.zip` stay local only (gitignored) and have no backup.

## Read before the first message

**1. Permission comes first (legal).** Summaries of Egypt's data law (Law 151/2020, articles 17 and 18) say electronic direct marketing needs the recipient's approval, must identify the sender and give an easy way to opt out, and that you keep proof of approval for 3 years. One summary also mentions a licence from the data protection centre. I haven't read the official Arabic text and this isn't legal advice, and I don't know how it treats a business number. **Ask the lawyer reviewing the pilot agreement before scaling this up.** Until then the kit is built to stay on the careful side:
- The first message says who you are, asks one question, and offers an easy "no".
- **No image, video, PDF or link until they reply and say yes.**
- If someone says stop, stop and don't message again.
- Keep the chats; they're your record of who agreed.

**2. Protect your number.** People blocking or reporting you can get a number restricted. Send one at a time, each with a personal first line, about 5 a day. No broadcast lists, no adding people to groups, no bulk tools.

**3. Where numbers come from.** Only a number the business publishes (its website, Instagram, Facebook, Google Maps), one someone gives you, or one a person shares with you. Don't buy lists. Don't guess personal numbers. A branch number usually reaches staff, so use message 2.

**4. What's still true today.** No customers, no real savings figure, no accuracy figure. The pilot environment (PPS-29) and agreement (PPS-15) aren't ready, so don't promise a start date or accept real data yet.

## Set up once (10 minutes)

Install the free **WhatsApp Business** app on +20 102 735 4140. It's your decision; moving the number to it needs care, so back up your chats first.

| Setting | Use |
|---|---|
| Profile picture | `images/profile/profile-picture.png`, or your own photo. A person's face may get more replies |
| Name | Dr. Yasser Hosny · ProcurePilot |
| Category | Software company (or the closest option) |
| Website | https://procurepilot.iron-sys.com |
| Email | yasser.hosny@iron-sys.com |
| Description AR | نظام مشتريات للشركات اللي بتشتري من موردين كتير وعندها أكتر من فرع. بيقرا عروض الأسعار، يقارنها عبوة بعبوة، وشخص من فريقك بيوافق على كل عملية شراء. من Iron Systems. |
| Description EN | Purchasing software for companies buying from many suppliers across branches. It reads quotes, compares them pack for pack, and a person on your team approves every purchase. By Iron Systems. |
| Labels | New · Replied · Call booked · Talked · Pilot offered · Not now |
| Away message | Leave off. An automatic reply doesn't help a personal conversation |

## What to send when

| Step | When | Send | Attach |
|---|---|---|---|
| 1 | First contact | Message 1, 2, 3 or 4 | **Nothing** |
| 2 | They reply and show interest | Message 7 | Nothing, or the video if they ask |
| 3 | They agree to see it | Message 8 | One video: `videos/demo-ar-vertical.mp4` |
| 4 | They ask for something to read or forward | Message 9 | `pdf/one-pager.pdf` |
| 5 | They ask a specific question | Answers below | One image from the table below |
| 6 | After the call | Message 11 | Nothing |
| 7 | Only after a good call | Message 12 | `pdf/founding-customer-offer-PRIVATE.pdf` |

Send one thing at a time. Don't send everything at once.

## Messages

Fill in `[brackets]` and make each one sound like you. Arabic is the default; use English only if they write in English. The Arabic uses "you" in the plural, so it fits anyone.

### 1. First message: published business number, you know who owns it
> أهلًا [الاسم]، أنا د. ياسر حسني من Iron Systems. [سطر شخصي: مثلًا «مبروك فرع [المنطقة]»].
> بنعمل نظام مشتريات للشركات اللي عندها أكتر من فرع، وعندي سؤال واحد بس لو مش هيضايقكم: عروض أسعار الموردين بتوصلكم إزاي، وبتقارنوها فين؟
> لو مش مناسب قولولي وهقفل الموضوع.

> Hello [Name], I'm Dr. Yasser Hosny from Iron Systems. [Personal line, e.g. "Congratulations on the [area] branch."]
> We build purchasing software for companies with several branches, and I have one question, if you don't mind: how do supplier quotes reach you, and where do you compare them?
> If this isn't a good fit, just say so and I'll close the topic.

### 2. First message: branch or customer service number
> أهلًا، أنا د. ياسر حسني من Iron Systems. مش عميل ومش ببيع حاجة دلوقتي. ممكن أعرف مين المسؤول عن المشتريات عندكم، وأوصله إزاي؟ عندي سؤال واحد ليه. شكرًا جدًا.

> Hello, I'm Dr. Yasser Hosny from Iron Systems. I'm not a customer and I'm not selling anything right now. Could you tell me who handles purchasing, and how I can reach them? I have one question for them. Thank you.

### 3. First message: someone gave you the number
> أهلًا [الاسم]، أنا د. ياسر حسني. [اسم اللي عرّفنا] اداني رقمكم وقال أكلمكم. بنعمل نظام مشتريات للشركات اللي عندها أكتر من فرع. عندي سؤال واحد: عروض الموردين بتوصلكم إزاي، وبتقارنوها فين؟

> Hello [Name], I'm Dr. Yasser Hosny. [Introducer] gave me your number and suggested I reach out. We build purchasing software for companies with several branches. One question: how do supplier quotes reach you, and where do you compare them?

### 4. First message: you met at an event or spoke on LinkedIn
> أهلًا [الاسم]، د. ياسر حسني. اتكلمنا في [المكان]. زي ما قلتلك، بنعمل نظام لمشتريات الشركات متعددة الفروع. لسه حابب أفهم منكم: عروض الموردين بتوصلكم إزاي؟

> Hello [Name], Dr. Yasser Hosny. We spoke at [place]. As I mentioned, we build purchasing software for multi-branch companies. I'd still like to understand: how do supplier quotes reach you?

### 5. Follow-up, day 3 (once only)
> أهلًا [الاسم]، بس بفكركم بسؤالي: عروض الموردين بتوصلكم إزاي؟ رد بسطر واحد كفاية.

> Hello [Name], just a reminder of my question: how do supplier quotes reach you? A one-line answer is plenty.

### 6. Last follow-up, day 7, then stop
> آخر رسالة مني عشان ما أزعجكمش. لو الموضوع مش أولوية دلوقتي تمام جدًا. وشكرًا على وقتكم.

> Last note so I don't crowd your inbox. If it's not a priority now, no problem at all. Thanks for your time.

### 7. They answered: reflect, then offer a call
> شكرًا يا [الاسم]. يعني [لخّص رده في سطر]. ده بالظبط اللي بنحاول نحله. ينفع مكالمة ١٥ دقيقة [يوم] الساعة [١] أو [يوم] الساعة [٢]؟ هوريكم النظام وأسمع رأيكم.

> Thanks, [Name]. So [one-line summary]. That's exactly what we're trying to fix. Could we do a 15-minute call on [day] at [time 1] or [day] at [time 2]? I'll show you the system and hear what you think.

### 8. Sending the video
Restaurant:
> ده فيديو قصير للنظام وهو شغال، بيانات تجريبية. شوفوه لما تفضوا، ولو حاجة لفتت نظركم نتكلم ربع ساعة.

Other sectors:
> ده فيديو قصير للنظام وهو شغال، بيانات تجريبية. المثال فيه مطعم، بس الخطوات نفسها لأي حاجة بتشتروها. شوفوه لما تفضوا، ولو حاجة لفتت نظركم نتكلم ربع ساعة.

> Here's a short video of the system working, with demo data. [Other sectors: The example is a restaurant, but the steps are the same for what you buy.] Have a look when you're free, and if something stands out, let's talk for 15 minutes.

### 9. Sending the one-pager
> ده ملخص في صفحة واحدة، سهل تحولوه لأي حد عندكم بيتابع المشتريات.

> Here's a one-page summary that's easy to forward to whoever handles purchasing.

### 10. Asking for an introduction (no pitch)
> طيب شكرًا جدًا. لو تعرفوا حد صاحب أو مدير عمليات في شركة عندها أكتر من فرع وبتشتري من موردين كتير، ممكن تعرفوني عليه؟ عايز ١٠ دقايق من رأيه الصريح، مش بيع.

> Thanks very much. If you know an owner or operations manager at a company with several branches and many suppliers, could you introduce me? I'd like 10 minutes of their honest opinion, not a sales call.

### 11. After the call
> شكرًا يا [الاسم] على وقتك النهارده. اللي فهمته: [سطر]. الخطوة الجاية زي ما اتفقنا: [الخطوة + الميعاد]. لو في أي سؤال قبلها أنا موجود هنا.

> Thanks for your time today, [Name]. What I heard: [one line]. Next step, as agreed: [step + date]. I'm here if anything comes up before then.

### 12. The offer (only after a good call; private)
> زي ما اتفقنا، ده ملخص التجربة والعرض:
> • أسبوعين مجانًا، وأنا اللي هجهّز النظام معاكم.
> • بنسجل الأول أسعار ١٠ إلى ٢٠ صنف ووقت وصول العروض، وفي الآخر نشوف الفرق بالأرقام.
> • لو كمّلتوا: ١٬٥٠٠ جنيه للفرع في الشهر، وخصم ٥٠٪ أول ١٢ شهر لأول العملاء، مقابل دراسة حالة قصيرة واللوجو بتاعكم.
> • لو التوفير المؤكد في شهر أقل من ٣ أضعاف الاشتراك، الشهر اللي بعده مجانًا.
> ميعاد البداية نحدده مع بعض. أبعتلكم الاتفاقية لما تبقى جاهزة؟

> As agreed, here's the pilot and the offer in short:
> • Two weeks free, and I set the system up with you.
> • We first record prices for 10 to 20 key items and how long quotes take, then compare the difference in numbers at the end.
> • If you continue: EGP 1,500 per branch per month, with 50% off for the first 12 months for our first customers, in exchange for a short case study and your logo.
> • If verified savings in a month are below 3× the fee, the next month is free.
> We'll agree the start date together. Shall I send the agreement when it's ready?

## Quick answers

Save these as quick replies in WhatsApp Business. Type the shortcut and it fills in the text.

| Shortcut | They say | Answer AR | Answer EN |
|---|---|---|---|
| `/who` | Who are you? | أنا د. ياسر حسني، مؤسس Iron Systems. بنعمل برمجيات للشركات، ومنها ProcurePilot للمشتريات. ده موقعنا: https://procurepilot.iron-sys.com | I'm Dr. Yasser Hosny, founder of Iron Systems. We build software for businesses, including ProcurePilot for purchasing. Our site: https://procurepilot.iron-sys.com |
| `/number` | Where did you get my number? | لقيته على [المكان]. لو تحبوا مبعتش تاني قولولي وهشيله فورًا. | I found it on [place]. If you'd rather I don't message again, tell me and I'll remove it right away. |
| `/stop` | Stop | تحت أمركم، مش هبعت تاني. آسف على الإزعاج. | Of course, I won't message again. Sorry for the disturbance. |
| `/no` | Not interested | تمام، شكرًا على ردكم. لو احتجتوا حاجة في المشتريات بعدين أنا موجود. | No problem, thanks for replying. I'm here if purchasing comes up later. |
| `/price` | How much? | التجربة مجانية طوال الفترة المتفق عليها، وأنا اللي بجهّزها. السعر بعدها حسب عدد الفروع، وأقولهولكم بالتفصيل لما أفهم شغلكم. عندكم كام فرع؟ | The pilot is free for the agreed period and I set it up. After that it depends on your branches, and I'll give you the details once I understand how you work. How many branches do you have? |
| `/price2` | Asks again for the exact price | ١٬٥٠٠ جنيه للفرع في الشهر، بحد أدنى فرعين. ولأول العملاء خصم ٥٠٪ أول ١٢ شهر مقابل دراسة حالة واللوجو. | EGP 1,500 per branch per month, 2 branch minimum. First customers get 50% off for 12 months in exchange for a case study and logo. |
| `/excel` | Excel works for us | تمام للاحتفاظ بقائمة. اللي بنضيفه مقارنة العروض بند بند بالعبوة والتوصيل، وتسجيل التوفير بعد ما حد يتأكد منه. ربع ساعة وأوريكم الفرق. | It works for keeping a list. We add comparing quotes line by line, pack and delivery included, and recording a saving once someone verifies it. Give me 15 minutes to show you. |
| `/wa` | Our suppliers only use WhatsApp | يفضلوا عليه عادي. بتحفظوا الملف أو الصورة وترفعوها، أو تبعتوها بالإيميل. مفيش ربط مباشر بواتساب. | They can stay on it. Save the PDF or photo and upload it, or forward it by email. There's no direct WhatsApp connection. |
| `/save` | How much will we save? | لسه معنديش رقم حقيقي ومش هخترع واحد. في التجربة بنسجل أسعاركم الأول ونقيس عليها. | I don't have a real number yet and I won't invent one. In the pilot we record your prices first and measure against them. |
| `/clients` | Who are your clients? | لسه في أول الطريق، وإنتوا هتبقوا من أول العملاء. عشان كده التجربة مجانية وأنا اللي بجهّزها بنفسي. | We're at the start, and you'd be among our first customers. That's why the pilot is free and I set it up myself. |
| `/prices` | We don't want our prices seen | أسعار مورديكم ملككم وسرية، والاتفاقية بتثبت ده كتابة. ولو ماكملتوش، بنسلمكم بياناتكم ونمسحها. | Your supplier prices stay yours and confidential, and the agreement says so in writing. If you don't continue, you get your data and we delete it. |
| `/mistake` | Could it buy by mistake? | لأ. شخص من فريقكم بيوافق على كل عملية شراء، ومفيش حاجة بتتطلب قبل موافقته. | No. A person on your team approves every purchase. Nothing is ordered before that approval. |
| `/suplyd` | We use Suplyd | كمّلوا عليه. حطوا سعره جنب سعر مورديكم التانيين قبل ما تطلبوا. | Keep it. Put its price next to your other suppliers' before you order. |
| `/time` | No time now | مفهوم. إمتى يناسبكم أسألكم تاني؟ | Understood. When would be a better time to ask again? |

More: `docs/gtm/battlecards/` and `marketing/ProcurePilot/planning/buying-group-answers-2026-11.md`.

## Images

All show demo or example data and say so where a screen or a figure appears.

| File | Use it when | For |
|---|---|---|
| `images/send/card-general-ar.png`, `card-general-en.png` | One picture that explains everything, after they say yes. It says 2 weeks free, so keep it private | Anyone |
| `images/send/whatsapp-quotes.png` | "Our suppliers only use WhatsApp" | Anyone |
| `images/send/a-person-approves.png` | "Could it buy by mistake?" The screen shows food items | Anyone, say it's an example |
| `images/send/saved-or-think-you-saved.png` | "How do you count savings?" | Owners, finance |
| `pdf/cheapest-quote-example.pdf` | To explain the pack-and-delivery point. It's labelled restaurant purchasing | Restaurants |
| `pdf/one-pager.pdf` | Something to forward | Anyone |
| `pdf/founding-customer-offer-PRIVATE.pdf` | After a good call only. It's still marked "Draft"; tell me when to remove that | Qualified prospects |

## Videos

| File | Length, size | Use |
|---|---|---|
| `videos/demo-ar-vertical.mp4` | 1:14, 5.1 MB | **Default.** Best on a phone |
| `videos/demo-ar-wide.mp4` | 2:09, 7.4 MB | Longer version, for a laptop or a second viewer |
| `videos/demo-en-wide-send-as-document.mp4` | 2:09, 29 MB | Only if they write in English. May be too big as a normal video, so send it as a document |
| `videos/restaurant-card-ar.mp4`, `restaurant-card-en.mp4` | 0:08, 1.9 MB | Short animated card, says it's for restaurants. Restaurant contacts or groups only |

The demos show a restaurant. There's no version for other sectors yet.

## WhatsApp Status

Normally only your saved contacts who also saved your number see your Status, so this is a soft reminder, not a way to reach new people. Post one a week, and leave the phone number off the caption.

| Image | Caption |
|---|---|
| `images/status/status-1-who-is-cheapest.png` | سؤال بسيط. وإنتوا، بتعرفوا الإجابة إزاي؟ |
| `images/status/status-2-cheapest-order.png` | حجم العبوة والتوصيل بيغيروا الحسبة. |
| `images/status/status-3-free-pilot.png` | لو ده شغلكم، ابعتولي. |

## Keep track

Each evening, send me: "sent to X, Y; X replied [what they said]". I'll keep a list and update the Sales Pipeline after your OK. Keep score by replies and calls, not by messages sent.
