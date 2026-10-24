"""Build the supplier quote HTML for round 6 or 7 from the round-5 templates.

Usage: python make_round.py <6|7> <out dir> [DD/MM/YYYY]
Then: node ../../round-5/quotes/render.cjs <out dir>   (prints amana.png and the two PDFs)
      python ../../round-5/quotes/photo.py <out dir>/amana.png <out dir>/IMG-<date>-WA00NN.jpg

Prices sit just under the previous round's PO prices (الأمانة won every round), so each round saves
against the last PO price. render.cjs writes round-5 PDF names; rename them to the numbers below.
"""

import datetime as dt
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / "round-5" / "quotes"

# Per round: quote numbers and unit prices. Quantities stay oil 8, rice 12, onions 80 kg.
ROUNDS = {
    6: {
        "amana_no": "AM-2026-0768", "nour_no": "NR-26/0447", "sayed_no": "QS-2026-1104",
        "amana": {"oil": 1575, "rice": 895, "onion": 16.25},
        "nour": {"oil": 1600, "rice": 910},
        "sayed": {"onion": 16.75},
    },
    7: {
        "amana_no": "AM-2026-0781", "nour_no": "NR-26/0459", "sayed_no": "QS-2026-1117",
        "amana": {"oil": 1560, "rice": 890, "onion": 16.00},
        "nour": {"oil": 1585, "rice": 900},
        "sayed": {"onion": 16.50},
    },
}
QTY = {"oil": 8, "rice": 12, "onion": 80}
R5 = {  # round-5 strings replaced in the templates
    "amana": {"no": "AM-2026-0752", "valid": "30/10/2026",
              "lines": {"oil": ("1,595.00", "12,760.00"), "rice": ("905.00", "10,860.00"),
                        "onion": ("16.50", "1,320.00")}, "total": "24,940.00"},
    "nour": {"no": "NR-26/0433", "valid": "31/10/2026",
             "lines": {"rice": ("915.00", "10,980.00"), "oil": ("1,620.00", "12,960.00")},
             "total": "23,940.00"},
    "sayed": {"no": "QS-2026-1089", "valid": "25/10/2026",
              "lines": {"onion": ("16.90", "1,352.00")}, "total": "1,352.00"},
}
VALID_DAYS = {"amana": 10, "nour": 11, "sayed": 5}


def money(x: float) -> str:
    return f"{x:,.2f}"


def build(rnd: int, out: pathlib.Path, date: dt.date) -> None:
    cfg = ROUNDS[rnd]
    out.mkdir(parents=True, exist_ok=True)
    for sup in ("amana", "nour", "sayed"):
        html = (SRC / f"{sup}.html").read_text(encoding="utf-8")
        old = R5[sup]
        html = html.replace("20/10/2026", date.strftime("%d/%m/%Y"))
        valid = date + dt.timedelta(days=VALID_DAYS[sup])
        html = html.replace(old["valid"], valid.strftime("%d/%m/%Y"))
        html = html.replace(old["no"], cfg[f"{sup}_no"])
        total = 0.0
        for item, (unit, line) in old["lines"].items():
            price = cfg[sup][item]
            amount = price * QTY[item]
            total += amount
            row_old = f"<td>{unit}</td><td>{line}</td>"
            assert row_old in html, (sup, item)
            html = html.replace(row_old, f"<td>{money(price)}</td><td>{money(amount)}</td>")
        assert old["total"] in html, sup
        html = html.replace(old["total"], money(total))
        (out / f"{sup}.html").write_text(html, encoding="utf-8")
        print(f"round {rnd} {sup}: {cfg[f'{sup}_no']} total {money(total)} EGP")


if __name__ == "__main__":
    r = int(sys.argv[1])
    d = dt.datetime.strptime(sys.argv[3], "%d/%m/%Y").date() if len(sys.argv) > 3 else dt.date.today()
    build(r, pathlib.Path(sys.argv[2]), d)
