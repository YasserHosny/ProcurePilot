from pathlib import Path
p=Path('render_fallback.py').read_text().replace("for lang in ('ar','en'):","for lang in ('en',):")
p=p.replace('Demo data · Arabic interface','Demo data').replace('460*f/30','200*f/30').replace('Compared with last purchase-order prices','This order vs last purchase-order prices').replace('oil +240 · rice +180 · onions +40','oil +120 · rice +60 · onions +20')
p=p.replace("texts={m[0]:[m[1],m[2]] for m in re.findall", "texts={m[0]:[m[1],m[2]] for m in re.findall")
p=p.replace('def font(n,b=False)',"texts['fields'][1]='EGP 24,940 · extracted total reconciles'\ntexts['prices'][1]='Oil ×8 · EGP 12,760 vs 12,960'\ntexts['sent'][1]='PO-000007 · purchase order submitted'\ntexts['ledger'][1]='EGP 1,260 · demo ledger, including earlier rounds'\ndef font(n,b=False)")
Path('render_fallback_en.py').write_text(p)
