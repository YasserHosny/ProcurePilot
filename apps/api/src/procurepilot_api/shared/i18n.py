from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# Search candidates for packages/i18n directory across local dev, tests, and Docker containers
_LOCALE_DIR_CANDIDATES = [
    Path(__file__).resolve().parents[5] / "packages" / "i18n",
    Path(__file__).resolve().parents[4] / "packages" / "i18n",
    Path.cwd() / "packages" / "i18n",
    Path("/app/packages/i18n"),
]


@lru_cache(maxsize=1)
def find_i18n_dir() -> Path:
    for candidate in _LOCALE_DIR_CANDIDATES:
        if (candidate / "en.json").is_file():
            return candidate
    return _LOCALE_DIR_CANDIDATES[0]


@lru_cache(maxsize=4)
def load_translations(locale: str) -> dict[str, Any]:
    norm_locale = "ar" if str(locale).lower().startswith("ar") else "en"
    i18n_dir = find_i18n_dir()
    target_file = i18n_dir / f"{norm_locale}.json"
    if not target_file.is_file():
        target_file = i18n_dir / "en.json"
    if not target_file.is_file():
        return {}
    with open(target_file, encoding="utf-8") as f:
        return json.load(f)


def t(key: str, locale: str = "en", **kwargs: object) -> str:
    """Translate a dotted key using packages/i18n, falling back to English and then raw key."""
    translations = load_translations(locale)
    parts = key.split(".")
    curr: Any = translations
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            curr = None
            break

    if curr is None and not str(locale).lower().startswith("en"):
        en_trans = load_translations("en")
        curr = en_trans
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                curr = None
                break

    if curr is None or not isinstance(curr, str):
        return key

    result = curr
    for k, v in kwargs.items():
        result = result.replace(f"{{{{{k}}}}}", str(v))
    return result


def get_export_column_headers(kind: str, locale: str = "en") -> list[str]:
    """Return declared business column headers for export kind in the requested locale."""
    columns_map = {
        "savings_ledger": [
            "id",
            "recorded_at",
            "branch_name",
            "supplier_name",
            "product_name",
            "unit",
            "quantity",
            "baseline_total",
            "actual_total",
            "delta_amount",
            "currency",
            "evidence_ref",
        ],
        "spend_by_supplier": [
            "supplier_name",
            "tax_number",
            "currency",
            "total_spend",
            "order_count",
            "realised_savings",
            "primary_branch",
        ],
        "alerts_summary": [
            "id",
            "triggered_at",
            "alert_type",
            "severity",
            "supplier_name",
            "product_name",
            "branch_name",
            "exposure_amount",
            "currency",
            "status",
            "dismissed_by",
            "dismissal_reason",
        ],
    }

    cols = columns_map.get(kind, columns_map["savings_ledger"])
    return [t(f"reports.exportColumns.{kind}.{col}", locale=locale) for col in cols]
