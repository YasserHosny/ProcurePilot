# Azure Document Intelligence fixtures

The JSON responses in this directory are hand-built from the committed PDF text layer and the
known hosted reproduction. They are not recordings from Azure Document Intelligence. In
particular, the demo `.invoice.json` files intentionally reproduce the collapsed single-item
`Items` response, and the `.layout.json` files model table responses using the garbled Arabic
forms present in the text layer.

To replace/add recorded responses when Azure credentials are available, set
`AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` and run
`python services/extraction-worker/scripts/record_azure_fixtures.py`. That script analyzes each
source document with `prebuilt-invoice` and `prebuilt-layout` and writes each SDK response using
`.as_dict()`. It has deliberately not been run for this offline change.
