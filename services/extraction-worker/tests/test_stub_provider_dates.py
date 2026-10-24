"""The CI stub provider's quotation must still be valid on the day the e2e suite runs.

Smart Compare hides expired offers by default, and offers now carry the quotation's expiry
(PPS-50). A fixed expiry date silently turned into a past date and broke the canonical path.
"""

from datetime import date

from procurepilot_extraction_worker.providers import FakeExtractionProvider


def test_stub_quotation_is_issued_in_the_past_and_not_yet_expired() -> None:
    result = FakeExtractionProvider().extract(
        document_id="doc", mime_type="application/pdf", storage_path="tenants/t/q/doc"
    )
    today = date.today()
    issue = date.fromisoformat(str(result.header["issue_date"].value))
    expiry = date.fromisoformat(str(result.header["expiry_date"].value))

    assert issue <= today < expiry
