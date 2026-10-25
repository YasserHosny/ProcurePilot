"""English supplier quotes for the all-English demo workspaces (PPS-64 Saudi, PPS-65 Ireland).

usage: python gen_quotes_en.py <profile sa-en|ie> <round D|E> <out dir> <DD/MM/YYYY>
  D = dry round (sets the last PO prices), E = recorded round, English UI.
Then: NODE_PATH=... node render_quotes_en.cjs <out dir>    (photo.png + the two supplier PDFs)
      python ../../../demo-tenant/round-5/quotes/photo.py <out>/photo.png <out>/IMG-<date>-WA00NN.jpg

The first supplier is the cheapest in every round and sends a phone photo; the other two send PDFs. Saudi quotes
state prices including 15% VAT in the total row; Irish quotes state prices excluding VAT, with a zero-rated VAT
line (most food is zero-rated in Ireland). All names, numbers and VAT registration numbers are fictional.
"""

import datetime as dt
import pathlib
import sys

PROFILES = {
    "sa-en": {
        "money": lambda x: f"SAR {x:,.2f}",
        "currency_label": "Saudi Riyal (SAR)",
        "to": "Rawaq Restaurant Group — Olaya Branch",
        "items": {"oil": ("Sunflower Oil", "18 L tin"), "rice": ("Basmati Rice", "10 kg bag"),
                  "tomato": ("Tomatoes", "6 kg carton")},
        "suppliers": {
            "golden": ("Golden Crescent Foodstuff", "Wholesale foodstuff — Al Sulay, Riyadh", "Tel: 011 467 3390",
                       "VAT No. 300512748600003", 10, "Fahad Al-Otaibi, Sales Manager"),
            "redsea": ("Red Sea Food Trading", "Industrial Area, Phase 3, Jeddah", "Tel: 012 921 0076",
                       "VAT No. 310284567900003", 11, None),
            "qassim": ("Qassim Fresh Produce", "Central Vegetable Market — Atiqa, Riyadh", "Mobile: 055 318 4402",
                       "VAT No. 302947851200003", 5, None),
        },
        "rounds": {
            "D": {"golden": {"oil": 158, "rice": 92, "tomato": 38}, "redsea": {"oil": 162, "rice": 94},
                  "qassim": {"tomato": 39}, "nos": ("GC-26-0412", "RS-2026-0318", "QF-7731")},
            "E": {"golden": {"oil": 148, "rice": 87, "tomato": 35}, "redsea": {"oil": 152, "rice": 89},
                  "qassim": {"tomato": 36}, "nos": ("GC-26-0437", "RS-2026-0342", "QF-7756")},
        },
        "vat_inclusive": True,
        "delivery": "Delivery to the Olaya Branch",
        "missing": "Tomatoes are not available from us at present.",
    },
    "ie": {
        "money": lambda x: f"€{x:,.2f}",
        "currency_label": "Euro (EUR)",
        "to": "Liffey Kitchen Group — Temple Bar",
        "items": {"oil": ("Sunflower Oil", "20 L drum"), "rice": ("Basmati Rice", "10 kg bag"),
                  "tomato": ("Tomatoes", "6 kg box")},
        "suppliers": {
            "brennan": ("Brennan & Walsh Wholesale", "Unit 7, Ballymount Industrial Estate, Dublin 12",
                        "Tel: 01 456 2290", "VAT No. IE 3456789TH", 10, "Sean Brennan, Sales"),
            "atlantic": ("Atlantic Fresh Foods Ltd", "Galway Road Business Park, Athlone, Co. Westmeath",
                         "Tel: 090 647 1185", "VAT No. IE 6388047V", 11, None),
            "kerrigan": ("Kerrigan Farm Produce", "Kenure Road, Rush, Co. Dublin", "Mobile: 087 318 4402",
                         "VAT No. IE 9812345K", 5, None),
        },
        "rounds": {
            "D": {"brennan": {"oil": 42.50, "rice": 21.80, "tomato": 13.20}, "atlantic": {"oil": 43.90, "rice": 22.40},
                  "kerrigan": {"tomato": 13.60}, "nos": ("BW-26-1184", "AFF-2026-0712", "KFP-5521")},
            "E": {"brennan": {"oil": 40.90, "rice": 20.95, "tomato": 12.60}, "atlantic": {"oil": 42.20, "rice": 21.60},
                  "kerrigan": {"tomato": 12.95}, "nos": ("BW-26-1219", "AFF-2026-0748", "KFP-5557")},
        },
        "vat_inclusive": False,
        "delivery": "Delivery to Temple Bar",
        "missing": "Tomatoes are not in our range at present.",
    },
}
QTY = {"oil": 10, "rice": 30, "tomato": 20}

PHOTO_CSS = """html,body{margin:0;background:#fff}
body{width:1240px;height:1754px;box-sizing:border-box;padding:90px 95px;font-family:'Noto Serif','Georgia',serif;font-size:27px;color:#151515;position:relative}
.hdr{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:4px double #6b4a12;padding-bottom:18px;margin-bottom:26px}
.hdr h1{font-size:44px;margin:0;color:#6b4a12}.hdr .sub{font-size:22px;color:#333}
.title{font-size:40px;color:#6b4a12;text-align:right}
.meta{width:100%;margin:6px 0 18px}.meta td{padding:4px 2px;font-size:24px}
table.items{width:100%;border-collapse:collapse}
.items th,.items td{border:2px solid #444;padding:12px 10px;text-align:center;font-size:25px}
.items th{background:#f3ead8}.items td.n{text-align:left}
.tot td{font-weight:bold;font-size:26px}
.notes{margin-top:30px;font-size:23px;line-height:1.7}
.stamp{position:absolute;right:150px;bottom:250px;width:230px;height:230px;border:6px solid rgba(120,80,20,.55);border-radius:50%;transform:rotate(-14deg);display:flex;align-items:center;justify-content:center;text-align:center;color:rgba(120,80,20,.6);font-size:19px;line-height:1.35;font-weight:bold;padding:0 22px}
.stamp:before{content:"";position:absolute;inset:14px;border:2px solid rgba(120,80,20,.5);border-radius:50%}
.sig{position:absolute;left:120px;bottom:265px;font-size:24px}
.sig .ink{font-family:'Brush Script MT','Segoe Script',cursive;font-size:46px;color:#5a3a10;transform:rotate(-6deg);display:inline-block;margin-top:6px}
.foot{position:absolute;bottom:70px;left:95px;right:95px;border-top:2px solid #6b4a12;padding-top:10px;font-size:20px;color:#444;text-align:center}"""
PDF_CSS = """@page{size:A4;margin:18mm} body{font-family:'Noto Sans','Helvetica',sans-serif;font-size:12.5pt;color:#111}
h1{font-size:20pt;margin:0} .hdr{display:flex;justify-content:space-between;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;margin-top:12px} th,td{border:1px solid #555;padding:6px 8px;text-align:center} th{background:#eee} td.n{text-align:left}
.tot td{font-weight:bold} .meta td{border:none;text-align:left;padding:2px 6px}"""


def build(profile: str, rnd: str, out: pathlib.Path, date: dt.date) -> None:
    cfg = PROFILES[profile]
    money = cfg["money"]
    rcfg = cfg["rounds"][rnd]
    out.mkdir(parents=True, exist_ok=True)
    keys = list(cfg["suppliers"])
    for idx, (sup, no) in enumerate(zip(keys, rcfg["nos"])):
        name, addr, phone, vat, valid_days, signer = cfg["suppliers"][sup]
        prices = rcfg[sup]
        rows, total = [], 0.0
        for i, (item, price) in enumerate(prices.items(), 1):
            label, pack = cfg["items"][item]
            line = price * QTY[item]
            total += line
            rows.append(f"<tr><td>{i}</td><td class='n'>{label}</td><td>{pack}</td><td>{QTY[item]}</td>"
                        f"<td>{money(price)}</td><td>{money(line)}</td></tr>")
        body_rows = "\n".join(rows)
        d = date.strftime("%d/%m/%Y")
        valid = (date + dt.timedelta(days=valid_days)).strftime("%d/%m/%Y")
        if cfg["vat_inclusive"]:
            head = "<tr><th>#</th><th>Item</th><th>Pack</th><th>Qty</th><th>Price per pack</th><th>Amount</th></tr>"
            totals = f"<tr class='tot'><td colspan='5'>Total including VAT 15%</td><td>{money(total)}</td></tr>"
            vat_note = "All prices include 15% VAT."
        else:
            head = ("<tr><th>#</th><th>Item</th><th>Pack</th><th>Qty</th><th>Price per pack (excl. VAT)</th>"
                    "<th>Amount</th></tr>")
            totals = (f"<tr class='tot'><td colspan='5'>Subtotal</td><td>{money(total)}</td></tr>"
                      f"<tr><td colspan='5'>VAT 0% (zero-rated food)</td><td>{money(0)}</td></tr>"
                      f"<tr class='tot'><td colspan='5'>Total</td><td>{money(total)}</td></tr>")
            vat_note = "Prices exclude VAT; all items are zero-rated."
        if idx == 0:
            html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{PHOTO_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div class="sub">{addr}</div><div class="sub">{phone} — {vat}</div></div><div class="title">QUOTATION<div style="font-size:24px;color:#222">No. {no}</div></div></div>
<table class="meta"><tr><td>Date: {d}</td><td>Valid until: {valid}</td></tr><tr><td>To: {cfg['to']}</td><td>Currency: {cfg['currency_label']}</td></tr></table>
<table class="items"><thead>{head}</thead><tbody>
{body_rows}
{totals}</tbody></table>
<div class="notes">{cfg['delivery']} within 48 hours of confirmation; delivery is free.<br>Payment within 30 days of receipt. {vat_note}</div>
<div class="sig">{signer}<br><span class="ink">{signer.split(',')[0]}</span></div>
<div class="stamp">{name.split()[0]}<br>{' '.join(name.split()[1:])}</div>
<div class="foot">Orders and enquiries: {phone.split(': ')[1]} (WhatsApp) — thank you for your business</div>
</body></html>"""
            fname = "photo.html"
        else:
            note = cfg["missing"] + " " if idx == 1 else ""
            html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{PDF_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div>{addr}</div><div>{phone} — {vat}</div></div><div style="text-align:right"><h1>Quotation</h1><div>No: {no}</div></div></div>
<table class="meta"><tr><td>Date: {d}</td><td>Valid until: {valid}</td></tr>
<tr><td>To: {cfg['to']}</td><td>Currency: {cfg['currency_label']}</td></tr></table>
<table><thead>{head}</thead><tbody>
{body_rows}
{totals}</tbody></table>
<p>{note}{cfg['delivery']} within {2 if idx == 1 else 1} working day(s). {vat_note}</p><p>Kind regards,<br>{name}</p></body></html>"""
            fname = f"pdf{idx}.html"
        (out / fname).write_text(html, encoding="utf-8")
        (out / (fname + ".name")).write_text(f"{name} quote {no}", encoding="utf-8")
        print(f"{profile} round {rnd} {name}: {no} total {money(total)}")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]), dt.datetime.strptime(sys.argv[4], "%d/%m/%Y").date())
