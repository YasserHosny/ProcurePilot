"""Two Arabic PDF quotes (SAR, 15% VAT included) for the 023/024 round-1 re-walk on «مطاعم رواق» (2026-10-30).

usage: python gen_quotes_rewalk.py <out dir> <DD/MM/YYYY>
Then: NODE_PATH=<web node_modules> node render_quotes_review.cjs <out dir>   (prints the two PDFs)

Same template and lines as gen_quotes_review.py, with the quantities and prices from the 023 spec: الذهبي
DH-26-1252 4,147 and الوفرة WF/2026/0781 4,137. الذهبي is cheaper on rice and flour, الوفرة on oil and sugar,
so the RFQ split comes to 4,063 (74 below the best single supplier): الذهبي 2,773 and الوفرة 1,290.
Names and numbers are fictional.
"""

import datetime as dt
import pathlib
import sys

import gen_quotes_review as review

review.QTY = {"rice": 25, "oil": 6, "sugar": 12, "flour": 8}  # the re-walk RFQ, in packs
review.QUOTES = {  # supplier: (quote no, per-pack prices incl. VAT)
    "dhahabi": ("DH-26-1252", {"rice": 85, "oil": 151, "sugar": 39, "flour": 81}),
    "wafra": ("WF/2026/0781", {"rice": 87, "oil": 145, "sugar": 35, "flour": 84}),
}

if __name__ == "__main__":
    review.build(pathlib.Path(sys.argv[1]), dt.datetime.strptime(sys.argv[2], "%d/%m/%Y").date())
