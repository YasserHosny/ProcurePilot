"""Record Azure DI responses for fixture documents (requires explicit Azure credentials)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "azure_layout"


def main() -> None:
    endpoint = os.environ["AZURE_DI_ENDPOINT"]
    key = os.environ["AZURE_DI_KEY"]
    client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
    for path in sorted((ROOT / "documents").glob("*")):
        content = path.read_bytes()
        for model in ("prebuilt-invoice", "prebuilt-layout"):
            result = client.begin_analyze_document(
                model, AnalyzeDocumentRequest(bytes_source=content)
            ).result()
            target = ROOT / f"{path.stem}.{model.removeprefix('prebuilt-')}.json"
            target.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
