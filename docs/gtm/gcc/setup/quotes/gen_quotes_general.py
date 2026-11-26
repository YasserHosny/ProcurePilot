"""English supplier quotes for the general demo workspace Nuvara Group (EGP, prices include 14% VAT).

usage: py gen_quotes_general.py <round D|E> <out dir> <DD/MM/YYYY>
  D = dry round: Bayan only (sets the last PO prices).
  E = screenshot round: Arkan (PDF), Safwa (phone photo), Bayan (PDF). Delta gets the RFQ and does not reply.
Then: NODE_PATH=... node render_quotes_general.cjs <out dir>   (photo.png + the PDFs)
      py ../../../demo-tenant/round-5/quotes/photo.py <out>/photo.png <out>/IMG-<date>-WA00NN.jpg

Plan and expected totals: docs/gtm/demo-tenant/general/plan.md. All names, addresses, phone and tax numbers are
fictional demo data.
"""

import datetime as dt
import pathlib
import sys

from gen_quotes_en import PDF_CSS, PHOTO_CSS

TO = "Nuvara Group — Head Office, New Cairo"
ITEMS = {  # key: (label, pack, qty in packs)
    "paper": ("A4 Copy Paper 80 gsm", "box of 5 reams", 20),
    "toner": ("Laser Toner Cartridge, Black (3,000 pages)", "1 cartridge", 6),
    "cleaner": ("Floor Cleaner", "4 L", 24),
    "towels": ("Paper Towel Rolls", "carton of 12", 15),
    "tape": ("Packing Tape 48 mm", "carton of 36", 6),
}
SUPPLIERS = {  # key: (name, address, phone, tax no, valid days, signer)
    "arkan": ("Arkan Office Supplies", "14 Abbas El-Akkad St, Nasr City, Cairo", "Tel: 02 2274 5618",
              "Tax Reg. No. 512-847-309", 10, None),
    "safwa": ("Safwa Hygiene Supplies", "Industrial Zone 3, 10th of Ramadan City", "Mobile: 010 0555 0142",
              "Tax Reg. No. 538-120-774", 7, "Hany Mostafa, Sales"),
    "bayan": ("Bayan General Trading", "Industrial Area B, El-Obour City", "Tel: 02 4489 2210",
              "Tax Reg. No. 547-903-116", 14, None),
}
ROUNDS = {
    "D": {"bayan": ({"paper": 1350, "toner": 2500, "cleaner": 170, "towels": 500, "tape": 950}, "BGT-Q-26-0911")},
    "E": {
        "arkan": ({"paper": 1280, "toner": 2350, "cleaner": 175, "towels": 510, "tape": 940}, "AOS-2026-1147"),
        "safwa": ({"paper": 1340, "toner": 2480, "cleaner": 150, "towels": 455, "tape": 960}, "SH-7724"),
        "bayan": ({"paper": 1310, "toner": 2420, "cleaner": 160, "towels": 470, "tape": 890}, "BGT-Q-26-0958"),
    },
}
PHOTO_SUPPLIER = "safwa"


def money(x: float) -> str:
    return f"EGP {x:,.2f}"


def build(rnd: str, out: pathlib.Path, date: dt.date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    head = "<tr><th>#</th><th>Item</th><th>Pack</th><th>Qty</th><th>Price per pack</th><th>Amount</th></tr>"
    d = date.strftime("%d/%m/%Y")
    pdf_n = 0
    for sup, (prices, no) in ROUNDS[rnd].items():
        name, addr, phone, tax, valid_days, signer = SUPPLIERS[sup]
        rows, total = [], 0
        for i, (item, price) in enumerate(prices.items(), 1):
            label, pack, qty = ITEMS[item]
            total += price * qty
            rows.append(f"<tr><td>{i}</td><td class='n'>{label}</td><td>{pack}</td><td>{qty}</td>"
                        f"<td>{money(price)}</td><td>{money(price * qty)}</td></tr>")
        body_rows = "\n".join(rows)
        totals = f"<tr class='tot'><td colspan='5'>Total including VAT 14%</td><td>{money(total)}</td></tr>"
        valid = (date + dt.timedelta(days=valid_days)).strftime("%d/%m/%Y")
        meta = (f"<tr><td>Date: {d}</td><td>Valid until: {valid}</td></tr>"
                f"<tr><td>To: {TO}</td><td>Currency: Egyptian Pound (EGP)</td></tr>")
        if sup == PHOTO_SUPPLIER:
            html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{PHOTO_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div class="sub">{addr}</div><div class="sub">{phone} — {tax}</div></div><div class="title">QUOTATION<div style="font-size:24px;color:#222">No. {no}</div></div></div>
<table class="meta">{meta}</table>
<table class="items"><thead>{head}</thead><tbody>
{body_rows}
{totals}</tbody></table>
<div class="notes">Delivery to the Head Office within 24 hours of confirmation; delivery is free.<br>Payment within 30 days of receipt. All prices include 14% VAT.</div>
<div class="sig">{signer}<br><span class="ink">{signer.split(',')[0]}</span></div>
<div class="stamp">{name.split()[0]}<br>{' '.join(name.split()[1:])}</div>
<div class="foot">Orders and enquiries: {phone.split(': ')[1]} (WhatsApp) — thank you for your business</div>
</body></html>"""
            fname = "photo.html"
        else:
            pdf_n += 1
            html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{PDF_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div>{addr}</div><div>{phone} — {tax}</div></div><div style="text-align:right"><h1>Quotation</h1><div>No: {no}</div></div></div>
<table class="meta">{meta}</table>
<table><thead>{head}</thead><tbody>
{body_rows}
{totals}</tbody></table>
<p>Delivery to the Head Office, New Cairo within 2 working days. All prices include 14% VAT.</p><p>Kind regards,<br>{name}</p></body></html>"""
            fname = f"pdf{pdf_n}.html"
        (out / fname).write_text(html, encoding="utf-8")
        (out / (fname + ".name")).write_text(f"{name} quote {no}", encoding="utf-8")
        print(f"round {rnd} {name}: {no} total {money(total)}")


if __name__ == "__main__":
    build(sys.argv[1], pathlib.Path(sys.argv[2]), dt.datetime.strptime(sys.argv[3], "%d/%m/%Y").date())
