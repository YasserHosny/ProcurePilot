"""The email that tells a guardrail's owner it drafted a purchase request (finding 38a)."""

from __future__ import annotations

import html

from pydantic import BaseModel

from procurepilot_api.shared.i18n import t


class RenderedAutoPreparedEmail(BaseModel):
    subject: str
    text: str
    html: str
    from_name: str
    locale: str


def render_auto_prepared_email(
    *,
    workspace_name: str,
    supplier_name: str,
    request_url: str,
    locale: str,
) -> RenderedAutoPreparedEmail:
    lang = "ar" if locale == "ar" else "en"
    direction = "rtl" if lang == "ar" else "ltr"
    prefix = "rfq.autoPreparedEmail"
    subject = t(f"{prefix}.subject", lang, supplier=supplier_name)
    greeting = t(f"{prefix}.greeting", lang)
    intro = t(f"{prefix}.intro", lang, workspace=workspace_name, supplier=supplier_name)
    review = t(f"{prefix}.review", lang)
    label = t(f"{prefix}.open", lang)
    why = t(f"{prefix}.why", lang)
    intro_html = t(
        f"{prefix}.intro",
        lang,
        workspace=html.escape(workspace_name),
        supplier=html.escape(supplier_name),
    )
    url = html.escape(request_url, quote=True)
    body = (
        f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
        f"<title>{html.escape(subject)}</title></head><body>"
        f"<p>{html.escape(greeting)}</p><p>{intro_html}</p><p>{html.escape(review)}</p>"
        f'<p><a href="{url}">{html.escape(label)}</a></p>'
        f'<p><span dir="ltr">{url}</span></p><p>{html.escape(why)}</p></body></html>'
    )
    return RenderedAutoPreparedEmail(
        subject=subject,
        text="\n\n".join([greeting, intro, review, label, request_url, why]),
        html=body,
        from_name=t(f"{prefix}.fromName", lang, workspace=workspace_name),
        locale=lang,
    )
