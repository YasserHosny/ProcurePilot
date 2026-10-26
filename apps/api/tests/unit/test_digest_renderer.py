from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from procurepilot_api.modules.digests.renderer import render_digest
from procurepilot_api.modules.digests.schemas import DigestView
from procurepilot_api.shared.i18n import t


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_digest_has_brand_footer_below_settings(locale: str) -> None:
    view = DigestView(
        subscription_id=UUID(int=1),
        period_start=date(2026, 10, 19),
        period_end=date(2026, 10, 26),
        sections=[],
        rendered_at=datetime(2026, 10, 26, tzinfo=UTC),
        delivery_status="succeeded",
    )
    _, html_body, text = render_digest(view, locale, "https://app.example.test")
    sent_with = t("emails.footer.sentWith", locale)
    website = t("emails.footer.website", locale)
    assert text.endswith(f"{sent_with} · {website}")
    assert text.index(t("digests.email.footer", locale)) < text.index(sent_with)
    assert html_body.index(t("digests.email.unsubscribe", locale)) < html_body.index(sent_with)
    assert 'href="https://www.iron-sys.com/" dir="ltr"' in html_body
    assert f">{website}</a>" in html_body
