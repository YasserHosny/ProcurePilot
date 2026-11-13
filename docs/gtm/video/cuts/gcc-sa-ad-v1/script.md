# Saudi ad — script, voice direction and timings (PPS-220)

Status 2026-11-13: **approved by the owner** (voice A, line 7 re-voiced with tashkeel, «راسلنا واتساب اليوم»
removed from the voice, picture cues 0.1 s ahead of the voice). Still open: a Saudi contact for the end card. Cuts:
`procurepilot-ad-sa-ar-16x9.mp4`, `procurepilot-ad-sa-ar-9x16.mp4` (1:11), captions `procurepilot-ad-sa-ar.srt`.
No-voiceover versions of both (owner, 2026-11-13): `procurepilot-ad-sa-ar-16x9-no-vo.mp4` and
`procurepilot-ad-sa-ar-9x16-no-vo.mp4`, the same picture with music and effects only, for feeds that autoplay
muted or placements where the voice is not wanted; the on-screen type carries the message.
Source: [`../../source/edit-sa-ad/`](../../source/edit-sa-ad/).

Audience: owners and purchasing managers of Saudi restaurant groups. Structure: hook → problem → product →
five benefits (ask, read, compare, approve, save) → offer. Each product line says what the buyer gains, not
what the feature is called.

## Voice direction

White Saudi dialect, male, confident and friendly, conversational. Built with ElevenLabs Eleven v4, preset voice
«Callum» (picked by the owner from two auditions), one take with a direction per line: curious and confident (1),
relatable and a bit fed up (2), relieved and upbeat (3), friendly (4), reassuring (5), confident (6), easygoing (7),
proud (8), warm and inviting (9). Line 7 was regenerated with vowel marks on «الطَّلَب يِتْجَهَّز لَك مُسْوَدَّة» after the
owner heard it mispronounced; the owner asked for vowel marks on any text sent to the voice from now on.

## Lines

| # | Time | Voiceover (Saudi) | On screen | What it sells |
|---|---|---|---|---|
| 1 | 0:00–0:03 | كم مرة اشتريت بسعر أغلى، وأنت ما تدري؟ | The question as full-screen type, word by word | Hook: a loss the viewer may already be taking |
| 2 | 0:04–0:12 | عروض الموردين تجيك واتساب، وبي دي إف، وورق مصوّر. وأنت تنقل الأسعار بيدك في الإكسل، وتقارن كراتين مو نفس الحجم! | Real demo quotes landing as paper; the WhatsApp-to-Excel animation | The daily pain, in their words |
| 3 | 0:13–0:19 | خلاص، ارتاح من هالدوخة. بروكيور بايلوت: مشتريات مطعمك كلها في مكان واحد. | «خلاص.» → the logo builds → the promise | The product as the way out |
| 4 | 0:19–0:25 | الفرع يبلّغك من الجوال إن الزيت قرّب يخلص، وبطلب واحد توصل كل مورّدينك. | Phone low-stock report; the RFQ and the sent RFQ list | No more chasing suppliers one by one |
| 5 | 0:26–0:36 | جاك الرد صورة واتساب؟ ولا يهمّك. النظام يقرأ الأصناف والأسعار والضريبة لحاله، بدون ما تكتب ولا رقم. وأنت بس تراجع وتعتمد. | The photo quote; extracted lines; «التحقق الحسابي ناجح»; «تمت المراجعة والاعتماد» | No retyping, and the decision stays with a person |
| 6 | 0:36–0:42 | ويقارن لك العروض صح: بالكرتون، وشامل الضريبة والتوصيل. وتعرف بالأرقام مين الأوفر لك. | Smart Compare; الذهبي ١٬٥٢٠ against الوفرة ١٬٥٦٠; «أوفر بـ٤٠ ر.س» | A fair comparison and a number |
| 7 | 0:43–0:52 | الطلب يتجهّز لك مسودة، والمدير يعتمده من جواله وهو في أي مكان. وأمر الشراء ترسله للمورد على طول. | The guardrail's draft; phone approval; PO-000002 sent | Orders stop waiting for a signature |
| 8 | 0:52–1:00 | وإذا سألك صاحب المطعم: كم وفّرنا؟ جوابك جاهز. كل ريال وفّرته، مسجّل ومراجَع. | «كم وفّرنا؟» → ١٩٠ ر.س → the verified ledger | Proof of the saving for the owner |
| 9 | 1:01–1:11 | بروكيور بايلوت. قارن. اختار. ووفّر. جرّبه أسبوعين مجاناً، وحنّا نجهّزه معك. | Logo, the tagline, the offer, then the WhatsApp number on screen only (the spoken «راسلنا واتساب اليوم» was removed at the owner's request) | The offer and the next step |

Exact word timings: [`../../source/edit-sa-ad/timeline.json`](../../source/edit-sa-ad/timeline.json).

## Claims

- Every figure is from round A on «مطاعم رواق» ([record](../../../gcc/rounds/README.md)); all data is demo data.
- The request is a draft the guardrails prepare; a person approves it and a person sends the PO. The voice says
  «مسودة», «يعتمده» and «ترسله» for that reason.
- No testimonial, customer count, integration or certification is claimed. The two-week free trial and the
  set-up offer are the ones on the approved end card.
