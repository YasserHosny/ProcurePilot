"""Shared branding for emails sent to workspace staff."""

from html import escape

from procurepilot_api.shared.i18n import t


def brand_footer(locale: str) -> tuple[str, str]:
    """Return the localized text line and an escaped, email-safe HTML footer."""
    sent_with = t("emails.footer.sentWith", locale)
    website = t("emails.footer.website", locale)
    text = f"{sent_with} · {website}"
    html = (
        '<p style="font-size: 12px; color: #64748b;">'
        f"{escape(sent_with)} · "
        '<a href="https://www.iron-sys.com/" dir="ltr" '
        f'style="color: inherit;">{escape(website)}</a></p>'
    )
    return text, html
