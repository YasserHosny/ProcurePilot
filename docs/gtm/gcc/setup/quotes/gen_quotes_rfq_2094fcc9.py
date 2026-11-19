"""Two Arabic PDF quotes (SAR, 15% VAT included) for RFQ 2094fcc9 on «مطاعم رواق» (2026-10-31).

usage: python gen_quotes_rfq_2094fcc9.py <out dir> <DD/MM/YYYY>
Then: NODE_PATH=<web node_modules> node render_quotes_review.cjs <out dir>   (prints the two PDFs)

Three lines in packs: basmati rice 10 kg ×3, sunflower oil 18 L ×5, chilled chicken 10 kg ×6. الذهبي DH-26-1270 2,000 is
cheaper on rice and chicken, الوفرة WF/2026/0790 2,018 on oil, so the split comes to 1,970 (30 below the best
single supplier). Names and numbers are fictional.
"""

import datetime as dt
import pathlib
import sys

import gen_quotes_review as review

review.QTY = {"rice": 3, "oil": 5, "chicken": 6}  # RFQ 2094fcc9, in packs
review.ITEMS = {**review.ITEMS, "chicken": ("دجاج مبرد", "كرتون 10 كجم")}
review.QUOTES = {  # supplier: (quote no, per-pack prices incl. VAT)
    "dhahabi": ("DH-26-1270", {"rice": 85, "oil": 151, "chicken": 165}),
    "wafra": ("WF/2026/0790", {"rice": 87, "oil": 145, "chicken": 172}),
}

if __name__ == "__main__":
    review.build(pathlib.Path(sys.argv[1]), dt.datetime.strptime(sys.argv[2], "%d/%m/%Y").date())
