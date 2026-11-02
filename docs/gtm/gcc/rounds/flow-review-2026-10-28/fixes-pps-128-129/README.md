# Flow review 2026-10-28: R17 and R18 fixes checked live (PPS-128 part 1, PPS-129)

[#355](https://github.com/YasserHosny/ProcurePilot/pull/355) (merge `486c7053`) was checked on hosted «مطاعم رواق» as
`pp-sa-owner` on 2026-10-30, after Deploy Backend and Deploy Frontend for that commit finished green. Arabic UI.
No email addresses appear in these screenshots.

## Why a new quote

After PO-000005, flour, rice, oil and sugar all have a submitted PO, so a new outcome for any of them takes its
baseline from the last PO price, which was already exact. To reach the quoted-price path that R18 is about, a
product needed a quote and no PO. So:

1. Quote **DH-26-1263** from الذهبي ([`gen_quote_pps129.py`](../../../setup/quotes/gen_quote_pps129.py)): eggs
   172 per carton of 30, and yogurt 50 per carton of 12 kg. Neither product had a quote or a PO before. Uploaded,
   extracted (Arithmetic Verified, SAR 716), supplier accepted, authorized; the yogurt line matched as Same Product,
   giving a landed cost of 4 cartons = 48 kg = SAR 200.0000. Pack details weren't extracted for the eggs line, so
   it was left unmatched.
2. Request `e02224e7` for 15 cartons of yogurt, approved. **PO-000009** to الذهبي: 15 × SAR 48 = SAR 720,
   submitted. (An earlier request, `3472ca12`, for 4 cartons was approved but has no PO. The PO form caps the
   quantity at the request's, and at 4 cartons the old rounding is too small to show: 200.0016 still displays as
   200.00.)

With 180 kg against a quote of 200 per 48 kg, the old arithmetic is 4.1667 × 180 = 750.0060, shown as 750.01. The
fixed arithmetic is 200 × 180 / 48 = 750.0000.

## Seen live

| # | Fix | Seen live | Screenshot |
|---|---|---|---|
| R17 (part 1) | Record outcome pre-fills without trailing zeros | PO-000009 → Record outcome: quantity «180», total «720» (before: «180.000000», «720.0000») | [01](01-record-outcome-po-000009-ar.jpg) |
| R18 | Quoted baseline without base-unit rounding | Save 1 outcome → Savings Ledger: yogurt baseline 750 «آخر سعر معروض» (Last Quoted Price), paid 720, saving **+30**. The flour row below, recorded before the fix, still reads 1,275.01 / +45.01 | [02](02-savings-ledger-ar.jpg) |
| R18 | Evidence | Net saving +30, baseline 750, unit price 4.17, policy «آخر سعر معروض», calculation version `saving-baseline-v3` | [03](03-saving-evidence-ar.jpg) |

The stored row (`saving_record` `0ab26d13`): policy `last_paid`, baseline unit price 4.1667, baseline **750.0000**,
actual 720, delta **30.0000**, `saving-baseline-v3`. Its `calculation_inputs` carry `landed_total` 200.0000 SAR,
`landed_quantity` 4 and `landed_base_quantity` 48. A read-only capture with main's code before the merge gave
750.0060 for the same outcome.

## Not in this check

- R17 part 2: the «إجمالي المدفوع دون الضريبة» («Total paid excl. tax») label is unchanged (screenshot 01). It
  follows the VAT decision on PPS-122 and is being built separately.
- Rows recorded before the fix keep their values (flour 1,275.01); the fix applies to new captures only.
- Side finding: on the quote review screen, the label of the flagged pack-text field shows the raw i18n key
  `quotations.review.fieldLabels.pack_text`.
