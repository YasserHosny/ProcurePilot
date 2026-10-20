# Editorial collage edit (v2.2-editorial)

Source for the Arabic-only editorial collage cuts in [`../../cuts/v2.2-editorial/`](../../cuts/v2.2-editorial/): the v2.2 storyboard and timing, restyled as a Contemporary Arabic Editorial Collage (oversized Arabic kinetic type, Swiss layouts, grayscale halftone photo cutouts, paper layers and grain, warm off-white / near-black / matte orange-red `#DD4F28`, shallow 2.5D with shadows falling lower-right, fast-in ease-out moves with motion blur only while moving, transitions built from paper and colour blocks). No neon, HUDs, glow, particles, glitch or SaaS cards.

App footage appears as grayscale printed "plates" cut from the v2.1 Arabic 16:9 cut (email already masked there), with v2.2's fixes applied in the edit: loading screens trimmed, no repeated PO pass, approval caption only after the toast, cut before the pointer reaches Reject.

## Files

| File | What it does |
|---|---|
| `engine.js` | Deterministic frame engine: `renderAt(t)` applies keyframe tracks (position, scale, rotation, opacity, clip insets, inner mask offsets), cubic-bezier eases, velocity-driven SVG motion blur, paper shadows and grain. `PLATE()` shows footage frames; `PM()` is a piecewise footage clock; `nb()` snaps a time to the nearest music beat. |
| `spec_h.js` / `spec_v.js` | The 16:9 (1:59) and 9:16 (0:53) timelines. All Arabic copy lives here. |
| `index.html` | Stage page; `#h` or `#v` picks the format. |
| `extract.py` | Cuts the 19 footage plates from the v2.1 cut into `plates/` (override the input with `PP_CUT`). |
| `make_data.py` | Writes `data.js` (beat map from `../../music/antalya-beaches-beats.csv` + plate index). |
| `make_textures.py` | Builds `tex/`: grain, halftone photos from the round-4 quote photos and a kitchen still, paper quotes from the round-4 PDFs. |
| `fetch_fonts.sh` | Downloads Readex Pro 300–700 into `fonts/`. |
| `render.cjs` | Playwright frame renderer: `node render.cjs <h|v> <outdir> <from> <to>` (frames at 30 fps). |
| `sheet.py` | Contact sheet of rendered frames for review. |

Generated folders (`plates/`, `tex/`, `fonts/`, `data.js`, frames, audio, mp4) are git-ignored.

## Rebuild

```bash
cd docs/gtm/video/source/edit-editorial
python3 extract.py && python3 make_data.py && python3 make_textures.py && ./fetch_fonts.sh
# 16:9: 3569 frames, split across 4 processes
for i in 0 1 2 3; do node render.cjs h frames-h $((i*893)) $(( (i+1)*893 > 3569 ? 3569 : (i+1)*893 )) & done; wait
# audio = v2.1 cut audio with the removed passage taken out
ffmpeg -i ../../cuts/v2.1/procurepilot-demo-ar-16x9.mp4 -filter_complex \
  "[0:a]atrim=0:109.2,asetpts=N/SR/TB[a];[0:a]atrim=start=125.4,asetpts=N/SR/TB[b];[a][b]concat=n=2:v=0:a=1,alimiter=limit=0.7:level=disabled" audio_h.wav
ffmpeg -framerate 30 -i frames-h/%05d.jpg -i audio_h.wav -c:v libx264 -crf 21 -tune grain -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart procurepilot-demo-ar-16x9.mp4
```

The vertical cut is the same with `v`, 1602 frames, and audio from `../../cuts/v2.1/procurepilot-demo-ar-9x16-60s.mp4` trimmed at `[0, 44.9] + [46.512, end]`. The limiter keeps the 16:9 peak near -1.3 dBFS after AAC encoding; without it the joined v2.1 audio clips at about +0.3 dBFS. The vertical audio peaks at -3.1 dBFS and needs none. Set `PP_PLAYWRIGHT` / `PP_CHROME` if Playwright or Chromium live elsewhere.

## Known gaps

- Arabic only; no English editorial cut yet.
- Footage comes from the v2.1 cut, not the v2.2 source clips, so it is one encode generation softer. Re-extracting plates from the v2.2 masked raw clips would sharpen it.
- The paper quotes in the opening are the round-4 demo quotes, whose prices differ from the round shown in the recorded app.
