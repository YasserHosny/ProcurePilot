"""End card v2: the approved end card (boards 5-13 of the logo canvas) with a real Iron Systems band.

Writes four standalone boards (EndCard{,En}{16x9,9x16}.html). Text, sizes and fade timing of the
original card are kept; only the closing "A product of Iron Systems" line becomes a company band with
the Iron Systems logo (from www.iron-sys.com), the website and the company's public address for new
business (hello@iron-sys.com, as listed on the site's contact section).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGO = (ROOT / 'iron-systems-logo.svg').read_text().replace('<svg ', '<svg aria-hidden="true" ', 1)
FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Readex+Pro:wght@400;500;600;700&display=swap" rel="stylesheet">')
PP_MARK = ('<svg aria-hidden="true" width="{s}" height="{s}" viewBox="0 0 64 64"><rect x="6" y="14" width="22" height="8" rx="4" fill="#C9D6E3"/>'
           '<rect x="6" y="28" width="34" height="8" rx="4" fill="#19B8A4"/><path d="M36 20 L58 32 L36 44 Z" fill="#19B8A4" stroke="#19B8A4" '
           'stroke-width="3" stroke-linejoin="round"/><rect x="6" y="42" width="16" height="8" rx="4" fill="#C9D6E3"/></svg>')
COPY = {
    'ar': dict(lang='ar', dir='rtl', head='جرّبه أسبوعين مجانًا', sub='وإحنا اللي هنجهّزه معاك.', wa='واتساب',
               founder='د. ياسر حسني — المؤسس', product='أحد منتجات'),
    'en': dict(lang='en', dir='ltr', head='Try it free for 2 weeks', sub='— we set it up with you.', wa='WhatsApp',
               founder='Dr. Yasser Hosny — Founder', product='A product of'),
}
CSS = """body{margin:0;background:#0B2545}
.in{animation:cardIn 6s cubic-bezier(.2,.8,.2,1) infinite both}
.d1{animation-delay:0s}.d2{animation-delay:.27s}.d3{animation-delay:.53s}.d4{animation-delay:.8s}.d5{animation-delay:1.07s}
@keyframes cardIn{0%{opacity:0;transform:translateY(18px)}10%,92%{opacity:1;transform:none}100%{opacity:0;transform:none}}
.iron svg{display:block;height:100%;width:auto;color:#FFFFFF}
.ltr{direction:ltr;unicode-bidi:isolate}"""


def card_16x9(c):
    return f"""<div dir="{c['dir']}" style="position:relative;width:1920px;height:1080px;box-sizing:border-box;background:#0B2545;font-family:'Readex Pro',sans-serif;color:#FFFFFF;padding:80px 160px 200px;display:flex;flex-direction:column;justify-content:center;gap:40px">
<div class="in d1" dir="ltr" style="display:flex;align-items:center;gap:18px;align-self:flex-start">{PP_MARK.format(s=64)}<span style="font-size:44px;font-weight:600;letter-spacing:-0.02em">Procure<span style="color:#19B8A4">Pilot</span></span></div>
<div style="display:flex;flex-direction:column;gap:18px">
<div class="in d2" style="font-size:104px;font-weight:700;line-height:1.15">{c['head']}</div>
<div class="in d3" style="font-size:46px;color:#D7E3F0">{c['sub']}</div>
</div>
<div class="in d4" style="display:flex;align-items:flex-end;gap:72px;padding-top:12px;border-top:2px solid #1F3D63">
<div style="display:flex;flex-direction:column;gap:6px;padding-top:28px"><span style="font-size:26px;color:#AFC3D9">{c['wa']}</span><span class="ltr" style="font-size:72px;font-weight:600;color:#19B8A4;letter-spacing:0.01em">+20 102 735 4140</span></div>
<div style="display:flex;flex-direction:column;gap:10px;padding-bottom:10px"><span style="font-size:34px;font-weight:500">{c['founder']}</span><span class="ltr" style="font-size:30px;color:#D7E3F0">yasser.hosny@iron-sys.com</span></div>
</div>
<div class="in d5" style="position:absolute;left:0;right:0;bottom:0;height:140px;box-sizing:border-box;padding:0 160px;background:#071A33;border-top:2px solid #1F3D63;display:flex;align-items:center;justify-content:space-between">
<div style="display:flex;align-items:center;gap:24px"><span style="font-size:28px;color:#AFC3D9">{c['product']}</span><span class="iron" style="height:64px">{LOGO}</span></div>
<div class="ltr" style="display:flex;align-items:center;gap:22px;font-size:32px"><span style="font-weight:600">www.iron-sys.com</span><span style="color:#5A7699">·</span><span style="color:#D7E3F0">hello@iron-sys.com</span></div>
</div>
</div>"""


def card_9x16(c):
    return f"""<div dir="{c['dir']}" style="width:1080px;height:1920px;box-sizing:border-box;background:#0B2545;font-family:'Readex Pro',sans-serif;color:#FFFFFF;padding:280px 96px 370px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:52px;text-align:center">
<div class="in d1" dir="ltr" style="display:flex;align-items:center;gap:16px">{PP_MARK.format(s=72)}<span style="font-size:52px;font-weight:600;letter-spacing:-0.02em">Procure<span style="color:#19B8A4">Pilot</span></span></div>
<div style="display:flex;flex-direction:column;gap:22px">
<div class="in d2" style="font-size:84px;font-weight:700;line-height:1.2;white-space:nowrap">{c['head']}</div>
<div class="in d3" style="font-size:46px;color:#D7E3F0">{c['sub']}</div>
</div>
<div class="in d4" style="display:flex;flex-direction:column;align-items:center;gap:12px">
<span style="font-size:30px;color:#AFC3D9">{c['wa']}</span>
<span class="ltr" style="font-size:76px;font-weight:600;color:#19B8A4">+20 102 735 4140</span>
<span style="font-size:36px;font-weight:500;padding-top:14px">{c['founder']}</span>
<span class="ltr" style="font-size:32px;color:#D7E3F0">yasser.hosny@iron-sys.com</span>
</div>
<div class="in d5" style="width:100%;box-sizing:border-box;padding:34px 40px;border-radius:24px;background:#071A33;border:2px solid #1F3D63;display:flex;flex-direction:column;align-items:center;gap:20px">
<div style="display:flex;align-items:center;gap:22px"><span style="font-size:30px;color:#AFC3D9">{c['product']}</span><span class="iron" style="height:68px">{LOGO}</span></div>
<div class="ltr" style="display:flex;align-items:center;gap:18px;font-size:32px"><span style="font-weight:600">www.iron-sys.com</span><span style="color:#5A7699">·</span><span style="color:#D7E3F0">hello@iron-sys.com</span></div>
</div>
</div>"""


def main():
    for lang, c in COPY.items():
        for aspect, build in (('16x9', card_16x9), ('9x16', card_9x16)):
            name = f"EndCard{'En' if lang == 'en' else ''}{aspect}.html"
            html = (f'<!doctype html><html lang="{c["lang"]}" dir="{c["dir"]}"><head><meta charset="utf-8">'
                    f'<title>ProcurePilot end card v2 — {aspect} {lang}</title>{FONT}<style>{CSS}</style></head>'
                    f'<body>{build(c)}</body></html>\n')
            (ROOT / name).write_text(html)
            print('wrote', name)


if __name__ == '__main__':
    main()
