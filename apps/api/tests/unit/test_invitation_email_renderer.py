from datetime import UTC, datetime

import pytest

from procurepilot_api.modules.members.invitation_email import render_invitation_email
from procurepilot_api.shared.i18n import t


@pytest.mark.parametrize(
    "locale,lang,direction", [("en", "en", "ltr"), ("ar", "ar", "rtl"), ("fr", "en", "ltr")]
)
def test_invitation_email_is_localized_and_escapes_values(
    locale: str, lang: str, direction: str
) -> None:
    workspace = '<script>alert("x")</script>'
    result = render_invitation_email(
        workspace_name=workspace,
        inviter_email="owner<test>@example.test",
        role="buyer",
        expires_at=datetime(2026, 10, 25, tzinfo=UTC),
        accept_url='https://app.example.test/?token=test&other="value"',
        locale=locale,
    )
    assert result.locale == lang
    assert f'<html lang="{lang}" dir="{direction}">' in result.html
    assert "<script>" not in result.html
    assert "&lt;script&gt;" in result.html
    assert '<span dir="ltr">owner&lt;test&gt;@example.test</span>' in result.html
    assert 'href="https://app.example.test/?token=test&amp;other=&quot;value&quot;"' in result.html
    assert workspace in result.text
    assert t("common.roles.buyer", lang) in result.text
    assert result.subject == t("team.invitationEmail.subject", lang, workspace=workspace)
    assert ("٢٥" if lang == "ar" else "25") in result.text
