from paths import *
from edl import FULL,VERT
import json

def make_report():
 text=['# ProcurePilot demo v2','',
 'All new files are under `edit/v2/`. No commits or git commands were made. Original sources, v1 scripts, raw recordings and original outros were read only. Copies of the reference scripts are in `reference/`.','',
 '## Changes and rebuild','',
 '- P1: opaque source-resolution identity masks, applied before crop/scale/setpts. The raw scan checks every encoded frame using visually inspected glyph templates, with actual `showinfo` source timestamps. `analysis/raw-email-audit.json` records detections; `analysis/mask-coverage.json` joins every detection in the EDL to its mask or excluded crop. Phone compact-list identity is checked separately and that layout is omitted.',
 '- P2: 460 EGP explicitly means this order versus last purchase-order prices; the 1,060 EGP ledger explicitly includes the earlier demo dry run. Counter animates for one second, then holds the final number for four seconds in landscape / three seconds in vertical.',
 '- P3: comparison is labelled oil ×8, rather than claiming that Smart Compare displays every RFQ line. The 12,880 vs 13,080 supplier comparison is separate from historical-baseline savings.',
 '- P4: first product shot at 3.00 s in landscape and 1.50 s in vertical. Most cards replaced by captions. Repeated typing/loading condensed; extracted total, recommendation, guardrail, approval, sent PO and ledger receive readable holds. The unrelated old request at the start of s3 is omitted. Illustrative notification card is removed.',
 '- P5: successive vertical views show the quote photo, extracted fields, recommendation, guardrail, submit control, phone approval, sent PO, outcome and ledger total. Active UI is fitted inside y=475..1515 and body captions start at y=275; key text avoids top 250 / bottom 350. Original outros remain as supplied.',
 '- English callouts translate the evidence and identify the interface as Arabic; body captions disclose demo data.',
 '- All cuts: 30 fps H.264, yuv420p, AAC 256 kb/s; same DayFox track, body gain -6.6 dB, 0.5 s fade-in, preserved outro mix, -3 dBFS limiter before AAC. Landscape music starts at 0:00; vertical at 2:00. The measured landscape pre-calibration export was -15.15 LUFS; a common +1.1 dB trim is applied to the joined body and outro before the -3 dBFS limiter. This retains their relative gain match while approaching -14 LUFS. Vertical common trim is 0 dB. Video packets are copied from the encoded body and original outro, avoiding a second video encode.','',
 'Run `./rebuild.sh`. Paths are at the top of `paths.py`. `build_v2.py` resumes completed segment files; remove the applicable **v2** segment cache before rebuilding changed shots. `qa.py` generates final-output proof PNGs every 0.25 s around masked slots, plus contact sheets every 3 s and audio logs.','',
 '## Tooling limits / work not done','',
 '- The requested Playwright HTML-to-PNG implementation is supplied as `render_cards_v2.cjs` and was attempted twice. Chrome failed at startup because the sandbox denies its socket operation. Executed exports therefore use `render_fallback.py` with Pillow + Raqm for shaped Arabic PNGs. This is a deviation from the requested overlay-rendering method. Failure evidence: `graphics.log`.',
 '- `ffprobe` is absent. Network/DNS restrictions prevented fetching it. Durations below are exact MP4 movie-header durations (`probe_duration.py`) cross-checked against ffmpeg input/decode logs; they must not be represented as ffprobe results.',
 '- No new s3b insert: captions were corrected instead. Holds use cloned endpoint frames, without artificial camera motion. No claims of an auditory seam review are made; the complete exports are measured and decoded.','',
 '## Source audit','']
 auditp=ROOT/'analysis/raw-email-audit.json'
 if auditp.exists():
  audit=json.loads(auditp.read_text());text+=['| Raw clip | Encoded frames checked | Frames with template matches | First / last detection (s) |','|---|---:|---:|---|']
  for name,v in audit.items():
   ds=v['detections'];times=f"{ds[0]['time']:.4f} / {ds[-1]['time']:.4f}" if ds else '—'
   text.append(f"| {name} | {v['frame_count']} | {len(ds)} | {times} |")
 extra=ROOT/'analysis/old-s6-audit.json'
 if extra.exists():
  v=json.loads(extra.read_text());text+=['',f"Retired old-s6-savings-pending: {v['frame_count']} encoded frames checked, {len(v['detections'])} email matches."]
 compact=ROOT/'analysis/phone-list-audit.json'
 if compact.exists():
  h=json.loads(compact.read_text());text+=['',f"Compact phone-list layout: {len(h)} matched frames, {h[0]['time']:.4f}–{h[-1]['time']:.4f} s. That entire layout is omitted from every cut."]
 for lang,vertical in [('ar',False),('en',False),('ar',True),('en',True)]:
  tag=f'{lang}-'+('9x16-60s' if vertical else '16x9');plan=VERT if vertical else FULL
  text+=['',f'## {tag}','', 'The EDL below is the executed v2 plan. Source spans are seconds in raw clips; freeze is additional cloned endpoint time. Speed applies only to the moving portion.','', '| Slot | Output interval | Source | Source span | Speed / treatment | Caption |','|---:|---|---|---|---|---|']
  offset=0;masks=[]
  for i,p in enumerate(plan):
   speed=(p['b']-p['a'])/(p['d']-p['freeze']);treatment=f"{speed:.3f}×"
   if p['freeze']:treatment+=f" + {p['freeze']:g} s hold"
   if p['crop']:treatment+=f"; crop x,y,w,h={p['crop']}"
   if p['src']=='counter':treatment='1 s count-up + final hold'
   text.append(f"| {i} | {offset:.2f}–{offset+p['d']:.2f} | {p['src']} | {p['a']:g}–{p['b']:g} | {treatment} | {p['cap'] or 'Historical-baseline saving'} |")
   if p['mask']:masks.append((i,offset,offset+p['d'],p))
   offset+=p['d']
  text+=['',f'Body: {offset:.2f} s, followed by the original {"vertical" if vertical else "landscape"} {lang} outro.','', 'Exact mask enable intervals (whole output slots, including frozen frames; intervals are half-open):','', '| Slot | Output mask interval | Source mask x,y,w,h,color | Visibility |','|---:|---|---|---|']
  for i,a,b,p in masks:
   vis='Identity field retained and covered'
   if p['crop']:
    cx,cy,cw,ch=p['crop'];mx,my,mw,mh,_=p['mask']
    if mx+mw<=cx or mx>=cx+cw or my+mh<=cy or my>=cy+ch:vis='Source masked; identity panel is also outside retained crop'
   text.append(f"| {i} | {a:.3f}–{b:.3f} s | {p['mask']} | {vis} |")
  qp=ROOT/'analysis'/f'qa-{tag}.json'
  if qp.exists():
   q=json.loads(qp.read_text());l=q['loudnorm'];text+=['',f"Measured finished duration: **{q['duration']:.3f} s**. Integrated loudness: **{l['input_i']} LUFS**. True peak: **{l['input_tp']} dBTP** (loudnorm input measurement). See `analysis/loudness-{tag}.log` and `analysis/decode-ebur128-{tag}.log`.",'',f"Mask proof: {len(q['proof_frames'])} final-output full-size PNGs, every 0.25 s with 0.5 s context on either side of each masked slot. Inspection sheets: "+', '.join(f'`{p}`' for p in q['proof_sheets'])+'. Exact filenames are listed in `proof/INSPECTED_FRAMES.txt`.']
  else:text+=['','Export / QA measurement pending.']
 (ROOT/'CHANGES.md').write_text('\n'.join(text)+'\n')
if __name__=='__main__':make_report()
