# Azure Document Intelligence fixtures

The JSON responses in this directory are hand-built from the committed PDF text layer and the
known hosted reproduction. They are not recordings from Azure Document Intelligence. In
particular, the demo `.invoice.json` files intentionally reproduce the collapsed single-item
`Items` response, and the `.layout.json` files model table responses using the garbled Arabic
forms present in the text layer.

`round1-dh-26-1252.layout.json` (الذهبي, `DH-26-1252`) and
`round1-wf-2026-0781.layout.json` (الوفرة, `WF/2026/0781`) are hand-built from the
round-1 quote template's columns in `docs/gtm/gcc/setup/quotes/gen_quotes.py`:
«م | الصنف | العبوة | الكمية | سعر العبوة (ر.س) | الإجمالي (ر.س)».
They retain the round-1 rice, oil, sugar and flour rows and their printed packs; the generator's
current round configurations use different items and prices. Totals are SAR 4,147.00 and
SAR 4,140.00 respectively. These fixtures reproduce R1-M9 (the dropped pack column) without
Azure calls, credentials or a dependency on model output. No Azure call was made, and these
are synthetic layout responses, not recorded OCR evidence. The tests load layouts directly,
so no `.invoice.json` partners or generated PDFs are needed.

To replace/add recorded responses when Azure credentials are available, set
`AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` and run
`python services/extraction-worker/scripts/record_azure_fixtures.py`. That script analyzes each
source document with `prebuilt-invoice` and `prebuilt-layout` and writes each SDK response using
`.as_dict()`. It has deliberately not been run for this offline change.
