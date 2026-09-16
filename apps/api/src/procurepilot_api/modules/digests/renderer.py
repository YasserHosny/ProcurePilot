from __future__ import annotations

import html
from urllib.parse import urljoin

from procurepilot_api.modules.digests.schemas import DigestView
from procurepilot_api.shared.i18n import t


def render_digest(
    view: DigestView,
    locale: str = "en",
    web_base_url: str = "http://localhost:4200",
) -> tuple[str, str, str]:
    """Render weekly digest into (subject, html_body, plain_text_body).

    Complies with FR-009, FR-010, FR-015, FR-016:
    - Fixed section order with verified savings in the hero position.
    - Multipart HTML and plain text.
    - Explicit direction (dir) and lang attributes per locale with email-safe fonts.
    - All user-facing strings loaded from packages/i18n (en and ar).
    - Every monetary value has explicit currency.
    - Settings footer link and unsubscribe action.
    """
    is_ar = str(locale).lower().startswith("ar")
    lang_code = "ar" if is_ar else "en"
    text_dir = "rtl" if is_ar else "ltr"

    period_str = f"{view.period_start.isoformat()} – {view.period_end.isoformat()}"
    subject = t(
        "digests.subject",
        locale,
        periodStart=view.period_start.isoformat(),
        periodEnd=view.period_end.isoformat(),
    )
    title = t("digests.title", locale)
    subtitle = t("digests.subtitle", locale)

    settings_url = urljoin(web_base_url, "/reports/digest-settings")
    empty_label = t("digests.empty.noItems", locale)

    # Build Plain Text
    text_lines = [
        f"=== {title} ===",
        f"{period_str}",
        subtitle,
        "",
    ]

    for section in view.sections:
        sec_title = t(f"digests.sections.{section.kind}", locale)
        text_lines.append(f"--- {sec_title} ---")
        if not section.items:
            text_lines.append(f"  {empty_label}")
        else:
            for item in section.items:
                money_str = (
                    f" [{item.money.amount:,.2f} {item.money.currency}]" if item.money else ""
                )
                link = urljoin(web_base_url, item.deep_link)
                action_label = t("digests.settings.viewAction", locale)
                text_lines.append(f"  * {item.label}{money_str}")
                text_lines.append(f"    {action_label}: {link}")
        text_lines.append("")

    footer_text = t("digests.email.footer", locale)
    text_lines.append(f"{footer_text} {settings_url}")
    plain_text = "\n".join(text_lines)

    # Build HTML
    html_sections: list[str] = []
    for section in view.sections:
        sec_title = html.escape(t(f"digests.sections.{section.kind}", locale))
        is_hero = section.kind == "verified_savings"

        card_bg = "#f0fdf4" if is_hero else "#f8fafc"
        card_border = "#86efac" if is_hero else "#e2e8f0"
        header_color = "#166534" if is_hero else "#1e293b"

        items_html: list[str] = []
        if not section.items:
            items_html.append(
                f"<div style='color: #64748b; font-size: 14px; font-style: italic;'>"
                f"{html.escape(empty_label)}</div>"
            )
        else:
            for item in section.items:
                item_label = html.escape(item.label)
                item_url = html.escape(urljoin(web_base_url, item.deep_link))
                money_badge = ""
                if item.money:
                    amt = f"{item.money.amount:,.2f} {item.money.currency}"
                    badge_bg = "#dcfce7" if is_hero else "#e0f2fe"
                    badge_color = "#15803d" if is_hero else "#0369a1"
                    money_badge = (
                        f"<span style='display: inline-block; padding: 2px 8px; "
                        f"background-color: {badge_bg}; color: {badge_color}; "
                        f"border-radius: 4px; font-size: 13px; font-weight: 600; "
                        f"margin-inline-start: 8px;'>{amt}</span>"
                    )

                items_html.append(
                    "<div style='margin-bottom: 10px; padding: 8px 12px; "
                    f"background-color: #ffffff; border: 1px solid {card_border}; "
                    "border-radius: 6px;'>"
                    "<div style='display: flex; justify-content: space-between; "
                    "align-items: center;'>"
                    f"<span style='font-size: 14px; font-weight: 500; color: #334155;'>"
                    f"{item_label}</span>"
                    f"{money_badge}"
                    "</div>"
                    "<div style='margin-top: 4px; font-size: 12px;'>"
                    f"<a href='{item_url}' style='color: #2563eb; text-decoration: none;'>"
                    f"{html.escape(t('digests.settings.viewAction', locale))} &rarr;</a>"
                    "</div>"
                    "</div>"
                )

        rendered_items = "\n".join(items_html)
        html_sections.append(
            f"<div style='margin-bottom: 20px; padding: 16px; background-color: {card_bg}; "
            f"border: 1px solid {card_border}; border-radius: 8px;'>"
            f"<h3 style='margin: 0 0 12px 0; font-size: 16px; color: {header_color}; "
            f"font-weight: 600;'>{sec_title}</h3>"
            f"{rendered_items}"
            f"</div>"
        )

    all_sections_html = "\n".join(html_sections)
    manage_settings_label = html.escape(t("digests.email.manageSettings", locale))
    unsubscribe_label = html.escape(t("digests.email.unsubscribe", locale))

    html_content = f"""<!DOCTYPE html>
<html lang="{lang_code}" dir="{text_dir}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Tahoma, Arial, sans-serif;
      background-color: #f1f5f9;
      margin: 0;
      padding: 24px 12px;
      color: #0f172a;
      direction: {text_dir};
    }}
    .container {{
      max-width: 640px;
      margin: 0 auto;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      padding: 24px 24px 16px 24px;
      background-color: #0f172a;
      color: #ffffff;
    }}
    .header h1 {{
      margin: 0 0 6px 0;
      font-size: 20px;
      font-weight: 700;
    }}
    .header p {{
      margin: 0;
      font-size: 14px;
      color: #94a3b8;
    }}
    .content {{
      padding: 24px;
    }}
    .footer {{
      padding: 16px 24px;
      background-color: #f8fafc;
      border-top: 1px solid #e2e8f0;
      font-size: 12px;
      color: #64748b;
      text-align: center;
    }}
    .footer a {{
      color: #2563eb;
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{html.escape(title)}</h1>
      <p>{html.escape(period_str)} &bull; {html.escape(subtitle)}</p>
    </div>
    <div class="content">
      {all_sections_html}
    </div>
    <div class="footer">
      <p style="margin: 0 0 8px 0;">{html.escape(footer_text)}</p>
      <p style="margin: 0;">
        <a href="{html.escape(settings_url)}">{manage_settings_label}</a> &bull;
        <a href="{html.escape(settings_url)}">{unsubscribe_label}</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    return subject, html_content, plain_text
