# Demo video v2.5: script delta (PPS-83)

The owner approved v2.5 on 2026-10-27 after reviewing the Egyptian Arabic 16:9 cut, and asked for the same
structure in every version. Beats 1–14 keep each market's approved copy:
- Egypt: [`../v2.4-ledger/script.md`](../v2.4-ledger/script.md), revision 2026-10-25;
- Saudi and Rawaq English: [`../../../gcc/script-saudi.md`](../../../gcc/script-saudi.md);
- Liffey: the Saudi script with its euro overrides in [`../../source/edit-ie/make_data.py`](../../source/edit-ie/make_data.py).

This file lists only what v2.5 adds or changes. Build: [`../../source/edit-v2.5/`](../../source/edit-v2.5/).

## Running order (16:9; 9:16 lengths in brackets)

| # | Scene | Length | Egyptian Arabic | Saudi Arabic | English |
|---|---|---|---|---|---|
| P1 | Paper quotes and WhatsApp photos fly in | 2.5 s (2.5) | «عروض في كل صيغة…» | «عروض في كل صيغة…» | "Quotes in every format…" |
| 0 | Opening animation, framed, beside the caption | 5 s (3) | «…وكل سعر بتكتبه بإيدك في الإكسيل.» | «…وكل سعر تكتبه بيدك في الإكسل.» | "…and every price retyped into Excel." |
| P3 | Three pain lines | 3.5 s (3) | «بتلف على كل مورد لوحده» · «بتقارن عبوات مش زي بعض» · «ومش عارف وفّرت كام» | «تدوّر على كل مورد لحاله» · «تقارن عبوات مو زي بعض» · «وما تدري كم وفّرت» | "Chasing each supplier one by one" · "Comparing packs that don't match" · "And no idea what you saved" |
| Turn | The logo builds on navy | 3.5 s (3) | logo · «لمشتريات المطاعم» · «بيحلّها كلها.» | logo · «لمشتريات المطاعم» · «يحلّها كلها.» | logo · "for restaurant purchasing" · "handles all of it." |
| 1 | Bridge: the sent PO and the saving | as v1 | «من بلاغ نقص لأمر شراء تبعته للموردين… والتوفير متسجّل.» | «من بلاغ نقص لأمر شراء ترسله للموردين… والتوفير مسجّل.» | as v1 ("From a low-stock report to a sent PO, with the saving logged.") |
| 2–14 | as v1 | as v1 | | | |
| 13 | Full-page saving at +2.5 s for 2.8 s (2.3 s; beat 13 is 1.5 s longer in 9:16) | — | «توفير على الطلب ده» · ٣٠٠ ج.م · «مقابل آخر سعر شراء» | «توفير على هذا الطلب» · ١٩٠ ر.س · «مقابل آخر سعر شراء» | "Saved on this order" · EGP 200 / SAR 120 / SAR 310 / €53.50 · "against the last purchase price" |
| Recap | Five struck pains, each with its fix | 6 s (5) | «كل مشكلة وعندنا حلها» | «كل مشكلة ولها حل» | "Every pain, solved" |

Recap rows, pain → fix:

| Egyptian Arabic | Saudi Arabic | English |
|---|---|---|
| نسخ الأسعار بإيدك → بيقرا الـPDF والصور لوحده | نسخ الأسعار بيدك → يقرأ الـPDF والصور بنفسه | Retyping prices → PDFs and photos read automatically |
| مورد مورد → طلب عرض سعر واحد لكل الموردين | مورد مورد → طلب عرض سعر واحد لكل الموردين | One supplier at a time → One RFQ to every supplier |
| عبوات مختلفة → مقارنة بالعبوة شامل الضريبة والتوصيل | عبوات مختلفة → مقارنة بالعبوة شامل الضريبة والتوصيل | Different pack sizes → Per pack, VAT and delivery included (Liffey: "Per pack, delivery included") |
| اعتماد متأخر → اعتماد من الموبايل | اعتماد متأخر → اعتماد من الجوال | Slow approvals → Approval from the phone |
| وفّرنا كام؟ → سجل توفير معتمد | كم وفّرنا؟ → سجل توفير معتمد | What did we save? → A verified savings ledger |

## Other changes

- **Name card removed from beat 1.** The turn card introduces the brand: the logo and name appear together
  once, and the name is not repeated in the copy.
- **Disclosure pill removed** ('Real run · demo data'). The description carries the disclosure.
- **Outro music:** a 1.5 s crossfade from the body music into the outro, with no hard cut. The outro level is
  unchanged (owner, 2026-10-27).
- **9:16 length:** the new chapter and the recap make the vertical cuts 1:14. Files drop the `-60s` suffix.

## Arabic re-shoot (PPS-84, 2026-10-28)

The Arabic cuts were re-filmed after the UI moved to «٢٤٬٦٤٠ ج.م» / «٤٬٩١٠ ر.س»:
- beats 5–7, 10, 11, plus the read-only beats 1, 13 and 14, are new footage;
- beats 8 and 12 keep the original (old «ج.م.» style, no «EGP»);
- the Saudi beat 14 card is now ٣١٠ ر.س, today's ledger total.

Figures in the captions are unchanged. Details: [`../../source/edit-v2.5/README.md`](../../source/edit-v2.5/README.md).
