"""Operator feedback digest email (spec 025 FR-024, research D9).

A short, plain summary for a ProcurePilot operator who opted in: for each new submission the
workspace, the category and a short excerpt, plus one link to the triage view. It never carries a
submitter's email address (the operator's own list of fields excludes it, and any address typed
into the feedback text is masked) and never an attachment reference. Strings come from
`packages/i18n` (`emails.feedbackDigest.*`) through `shared/i18n.t`.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

from procurepilot_api.shared.brand_footer import brand_footer
from procurepilot_api.shared.i18n import t

MAX_ITEMS = 20
EXCERPT_LENGTH = 140
TRIAGE_PATH = "/platform/feedback"

_EMAIL_RE = re.compile(r"[^\s@<>()\[\]]+@[^\s@<>()\[\]]+\.[^\s@<>()\[\]]+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DigestItem:
    workspace_name: str
    category: str | None
    text: str
    created_at: datetime


def make_excerpt(text: str, locale: str = "en") -> str:
    """Collapse whitespace, mask email addresses, and cut to a short excerpt."""
    masked = _EMAIL_RE.sub(t("emails.feedbackDigest.redacted", locale), text)
    collapsed = _WHITESPACE_RE.sub(" ", masked).strip()
    if len(collapsed) <= EXCERPT_LENGTH:
        return collapsed
    return collapsed[: EXCERPT_LENGTH - 1].rstrip() + "…"


def triage_url(web_base_url: str) -> str:
    return web_base_url.rstrip("/") + TRIAGE_PATH


def render_feedback_digest(
    items: list[DigestItem],
    locale: str = "en",
    web_base_url: str = "http://localhost:4200",
) -> tuple[str, str, str]:
    """Return ``(subject, html_body, plain_text_body)`` for the operator digest."""
    is_ar = str(locale).lower().startswith("ar")
    lang_code = "ar" if is_ar else "en"
    text_dir = "rtl" if is_ar else "ltr"

    total = len(items)
    shown = items[:MAX_ITEMS]
    hidden = total - len(shown)
    link = triage_url(web_base_url)

    subject = t("emails.feedbackDigest.subject", locale, count=total)
    title = t("emails.feedbackDigest.title", locale)
    summary = t("emails.feedbackDigest.summary", locale, count=total)
    workspace_label = t("emails.feedbackDigest.workspaceLabel", locale)
    category_label = t("emails.feedbackDigest.categoryLabel", locale)
    view_action = t("emails.feedbackDigest.viewAction", locale)
    footer = t("emails.feedbackDigest.footer", locale)
    more = t("emails.feedbackDigest.moreItems", locale, count=hidden) if hidden > 0 else ""

    def category_text(category: str | None) -> str:
        key = category if category in {"bug", "idea", "question", "other"} else "none"
        return t(f"emails.feedbackDigest.categories.{key}", locale)

    text_lines = [f"=== {title} ===", summary, ""]
    for item in shown:
        text_lines.append(f"* {workspace_label}: {item.workspace_name}")
        text_lines.append(f"  {category_label}: {category_text(item.category)}")
        text_lines.append(f"  {make_excerpt(item.text, locale)}")
        text_lines.append("")
    if more:
        text_lines.extend([more, ""])
    text_lines.extend([f"{view_action}: {link}", "", footer])
    brand_text, brand_html = brand_footer(locale)
    text_lines.extend(["", brand_text])
    plain_text = "\n".join(text_lines)

    cards: list[str] = []
    for item in shown:
        cards.append(
            "<div style='margin-bottom: 12px; padding: 10px 14px; background-color: #f8fafc; "
            "border: 1px solid #e2e8f0; border-radius: 8px;'>"
            "<div style='font-size: 13px; color: #475569;'>"
            f"<strong>{html.escape(workspace_label)}:</strong> "
            f"{html.escape(item.workspace_name)} &bull; "
            f"<strong>{html.escape(category_label)}:</strong> "
            f"{html.escape(category_text(item.category))}</div>"
            "<div style='margin-top: 6px; font-size: 14px; color: #0f172a;'>"
            f"{html.escape(make_excerpt(item.text, locale))}</div>"
            "</div>"
        )
    more_html = (
        f"<p style='font-size: 13px; color: #475569;'>{html.escape(more)}</p>" if more else ""
    )

    html_body = f"""<!DOCTYPE html>
<html lang="{lang_code}" dir="{text_dir}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Tahoma, Arial, \
sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px 12px; color: #0f172a; \
direction: {text_dir};">
  <div style="max-width: 640px; margin: 0 auto; background-color: #ffffff; \
border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
    <div style="padding: 20px 24px; background-color: #0f172a; color: #ffffff;">
      <h1 style="margin: 0 0 6px 0; font-size: 20px;">{html.escape(title)}</h1>
      <p style="margin: 0; font-size: 14px; color: #94a3b8;">{html.escape(summary)}</p>
    </div>
    <div style="padding: 24px;">
      {"".join(cards)}
      {more_html}
      <p style="margin-top: 16px;"><a href="{html.escape(link)}" \
style="color: #2563eb;">{html.escape(view_action)} &rarr;</a></p>
    </div>
    <div style="padding: 16px 24px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; \
font-size: 12px; color: #64748b; text-align: center;">
      <p style="margin: 0 0 8px 0;">{html.escape(footer)}</p>
      {brand_html}
    </div>
  </div>
</body>
</html>"""
    return subject, html_body, plain_text
