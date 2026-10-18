from __future__ import annotations

import html
from datetime import datetime

from pydantic import BaseModel

from procurepilot_api.shared.i18n import t


class RenderedInvitationEmail(BaseModel):
    subject: str
    text: str
    html: str
    from_name: str
    locale: str


def render_invitation_email(
    *,
    workspace_name: str,
    inviter_email: str,
    role: str,
    expires_at: datetime,
    accept_url: str,
    locale: str,
) -> RenderedInvitationEmail:
    lang = "ar" if locale == "ar" else "en"
    direction = "rtl" if lang == "ar" else "ltr"
    day, year = str(expires_at.day), str(expires_at.year)
    if lang == "ar":
        digits = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
        day, year = day.translate(digits), year.translate(digits)
    date_label = f"{day} {t(f'rfq.email.months.{expires_at.month}', lang)} {year}"
    prefix = "team.invitationEmail"
    subject = t(f"{prefix}.subject", lang, workspace=workspace_name)
    greeting = t(f"{prefix}.greeting", lang)
    intro = t(f"{prefix}.intro", lang, workspace=workspace_name, inviter=inviter_email)
    role_line = t(f"{prefix}.role", lang, role=t(f"common.roles.{role}", lang))
    expiry = t(f"{prefix}.expiry", lang, date=date_label)
    label = t(f"{prefix}.accept", lang)
    ignore = t(f"{prefix}.ignore", lang)
    # Interpolate escaped values into the HTML translation independently so the email
    # address can retain its direction within Arabic prose without trusting caller markup.
    intro_html = t(
        f"{prefix}.intro",
        lang,
        workspace=html.escape(workspace_name),
        inviter=f'<span dir="ltr">{html.escape(inviter_email)}</span>',
    )
    url = html.escape(accept_url, quote=True)
    body = (
        f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
        f"<title>{html.escape(subject)}</title></head><body>"
        f"<p>{html.escape(greeting)}</p><p>{intro_html}</p>"
        f"<p>{html.escape(role_line)}</p><p>{html.escape(expiry)}</p>"
        f'<p><a href="{url}">{html.escape(label)}</a></p>'
        f'<p><span dir="ltr">{url}</span></p><p>{html.escape(ignore)}</p></body></html>'
    )
    return RenderedInvitationEmail(
        subject=subject,
        text="\n\n".join([greeting, intro, role_line, expiry, label, accept_url, ignore]),
        html=body,
        from_name=t(f"{prefix}.fromName", lang, workspace=workspace_name),
        locale=lang,
    )
