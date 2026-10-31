# Flow review 2026-10-28 — R9 and R17 fixes checked live (PPS-122, PPS-128)

Checked on 2026-10-31 as `pp-sa-owner` of «مطاعم رواق», after [#380](https://github.com/YasserHosny/ProcurePilot/pull/380)
merged (`e65b4d2a`) and all five deploys for it finished. The decision is
[ADR-021](../../../../../architecture/adrs.md): a **VAT-inclusive quote** keeps its printed prices; landed cost derives the
VAT; orders and savings are in **net prices**. The owner's email is blurred in 01.

| # | Fix | Seen live | Screenshot |
|---|---|---|---|
| R9 | The quote records its VAT basis | Quote `2e7861de` (الذهبي, DH-26-1241, SAR 4,830, «الأسعار شاملة ضريبة القيمة المضافة 15%»): «الأسعار شاملة ضريبة القيمة المضافة» is ticked, «نسبة الضريبة (%)» shows 15, and every line's VAT reads «15% (شامل)». The arithmetic check still passes (4,830 = 4,830) | [01](01-quote-review-prices-include-vat-ar.jpg) |
| R9 | Landed cost equals the printed total | The quote's lines now have landed-cost **v2** rows: same totals (1,720 + 1,500 + 380 + 1,230 = 4,830) with the VAT derived (224.35 + 195.65 + 49.57 + 160.43). It is not added a second time | [correction-applied](correction-applied-2026-10-31.txt) |
| R9 / R17 | Orders are net + tax with the exact total | PO-000005: net pack prices 71.30, 130.43, 33.04, 74.78 and the order total still 4,830. Draft PO-000010: net 73.913 + line tax 277.175 (rice ×25), net 70.4348 + 84.5216 (flour ×8), order total exactly 2,773, order-level tax 0 | [02](02-po-000005-net-prices-total-4830-ar.jpg), [03](03-po-000010-net-and-line-tax-ar.jpg), [04](04-po-000010-total-2773-ar.jpg) |
| R17 | «Total paid excl. tax» is true | Record outcome on PO-000011 (الوفرة) pre-fills net totals 756.522 (oil 6 × 126.087) and 365.2176 (sugar 12 × 30.4348), with «لا يشمل الضريبة ١١٣٫٤٨ ر.س» / «٥٤٫٧٨ ر.س» below. Net + tax = 870 + 420 = 1,290, the printed total. Nothing was saved | [05](05-record-outcome-po-000011-net-excludes-tax-ar.jpg) |

## Historical data: the one-off correction

Every «مطاعم رواق» quote was recorded VAT-inclusive with tax 0 before ADR-021. The owner approved
[`correct_vat_inclusive.py`](correct_vat_inclusive.py) after its [dry run](correction-dry-run-2026-10-31.txt). It was applied
on 2026-10-31 at 11:44 UTC, after the API and optimiser deploys ([output](correction-applied-2026-10-31.txt), identical to
the dry run). What it changed:

- **23 quotes** set to `prices_include_vat`. A quote qualified only if its lines sum to the stated total. All 23 did.
  71 lines got `vat_rate` 0.15.
- **70 landed-cost v2 rows** appended. landed_cost is append-only, so the v1 rows stay as evidence. Each v2 row has the
  same total. Its `recorded_at` is the v1 row's plus 1 µs, so the order of offers is kept.
- **28 lines on PO-000001…PO-000011** (PO-000010/011 were added with the owner's OK) set to net (gross / 1.15, 4 dp),
  with line tax = gross − net. Every line total and order total is unchanged. PO-000005's line taxes sum to 630.0005,
  not 630.00, because the net prices are rounded to 4 dp. The total stays exactly 4,830.
- One `audit_event` (`data_correction.vat_inclusive_basis`) records the run.
- Not touched: «مطاعم سند», the saving ledger rows (`saving_record` / `purchase_record`, as the owner decided), and
  the order-level «Order tax» field.

PO-000011 was submitted (owner's OK) only to open Record outcome. No outcome was saved.

## Not yet checked live: a fresh extraction

A new VAT-inclusive quote ([DH-26-1241-V](../../../setup/quotes/pps-122-2026-10-31/), generated with
`gen_quotes_review.py … 31/10/2026 1 -V`) was uploaded as quote `dc07bc5f`. Extraction could not start:
`POST /quotations/{id}/extract` returns 503 `{"dependency": "redis"}`, and the job failed with `redis_enqueue_failed`.

- The hosted API cannot reach Redis, the `shared-redis` container in the bunny workers app. Uploads extracted
  normally until 2026-10-30 21:47.
- It is infrastructure, not this change. The worker's detection is covered by
  `services/extraction-worker/tests/test_vat_basis*.py`, built on the real الذهبي / الوفرة texts.
- The check that the extraction image is live (`retry-extraction` producing «Prices include VAT 15%») waits for Redis.
  Once it is back, start extraction on `dc07bc5f` and expect the two flagged header fields at 0.80 confidence.

## Tests

- pytest:
  - `test_landed_cost_rules.py` / `_replay.py`: v2 inclusive, 4,830 → VAT 630, total 4,830.
  - `test_landed_cost_audit.py`: T049.
  - `test_po_vat_split.py`: exact totals, including the 10.00 × 3 drift case.
  - `test_savings_baseline_capture.py` and `test_saving_outcome_from_po.py`: net basis.
  - `test_quotation_vat_basis.py`, `test_landed_cost_one_per_decision.py`, `test_matching_queue.py`.
  - The extraction worker's `test_vat_basis*.py`.
- Karma: quote review (VAT field, inclusive arithmetic), `order-create` + `vat-split` (net + tax prefill, 4,830 exactly),
  Record outcome («Excludes tax» hint).
