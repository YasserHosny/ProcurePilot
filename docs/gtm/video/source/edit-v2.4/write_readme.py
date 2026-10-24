"""Generate a reviewable handoff from real proof outputs, never estimated validation."""
from privacy import ROOT
import json

def read(name):
    p=ROOT/'proof'/name
    return p.read_text() if p.exists() else 'PENDING — command has not completed.\n'

def main():
    tl=json.loads((ROOT/'timeline.json').read_text())
    text='''# ProcurePilot v2.4 — Ledger UI edit

**Handoff status: final video rendering is blocked by this sandbox.** Source masking, audit evidence,
timeline/spec files, offline build tooling and audio are supplied here. The four final MP4s and their
final-cut contact sheets are not represented as completed renders. No commit or push was made.

## Changes from v2.3

Forked `engine.js`, `index.html` and `render.cjs` from `../edit-v2.3-brand/`; that folder is untouched.
The frame-addressed kinetic type, asymmetrical card compositions, navy-tinted shadows, grain and Converge
bar/arrow wipes remain. Native full-colour round-6 Arabic and round-7 English plates replace the old
duotone plates. Readex Pro uses the staged local fonts. The approved v2.4 Markdown is parsed directly for
caption copy, without rewriting it. Names inside the English UI remain the tenant's Arabic data.
The original approved openings and outro media are used. Outro video is appended by stream copy.

Beats 4 (supplier email) and 9 (basket split) have no footage and are dropped under the approved cut plan.
Horizontal body: 101 s (3030 frames); vertical body: 51 s (1530 frames). Nominal totals including the
approved outros: 110.75 s and 59.5 s. Actual final container durations require rendering and ffprobe.

## Rebuild — offline, exact commands

From the repository root, using only staged assets and already installed tools:

```bash
cd docs/gtm/video/source/edit-v2.4
bash rebuild.sh privacy
bash rebuild.sh prepare
bash rebuild.sh render
```

The privacy phase audits all 16 native-resolution raw clips, burns masked copies, audits every frame of
all masked clips, and runs the unmasked Arabic quote clip again as a positive control. The `prepare`
phase refuses extraction unless the 16-clip zero-match masked audit exists. It extracts only `masked/`
plus the approved openings, builds data/textures, and creates PCM and AAC audio mixes. Nothing downloads.
`cc` compiles the local bit-parallel matcher with the same acceptance rule as the NumPy reference;
`check_detector.py` independently compares both implementations on seven known source positions.

To render on a host where Chrome can run, the exact remaining commands after preparation are:

```bash
export NODE_PATH=/home/yasserhosny/Work/Projects/ProcurePilot/apps/web/node_modules
export PP_CHROME=/usr/bin/google-chrome
node render.cjs h ar frames-ar-h 0 3030
node render.cjs v ar frames-ar-v 0 1530
node render.cjs h en frames-en-h 0 3030
node render.cjs v en frames-en-v 0 1530
/home/yasserhosny/Work/pp-video-env/bin/python finish.py
```

`render.cjs` passes `--no-sandbox`, resolves fonts locally and fails on timeline/page errors.
`finish.py` writes H.264 / yuv420p / 30 fps bodies, appends the approved outro video by stream copy,
stream-copies the measured AAC 256 kb/s preview, records ffprobe and final ebur128 proof, and makes one every-2-second review sheet per
cut in `sheets/`. Output filenames under `../../cuts/v2.4-ledger/`:

- `procurepilot-demo-ar-16x9.mp4`
- `procurepilot-demo-ar-9x16-60s.mp4`
- `procurepilot-demo-en-16x9.mp4`
- `procurepilot-demo-en-9x16-60s.mp4`

## Privacy method and limits

Six native glyph templates are sampled directly into RAM from known quote and phone source positions.
No address literal or template image is written by the detector. It tests every frame at full source
resolution, searching the complete frame, using 20 ink and 12 clear-background anchors followed by a
full binary-patch mismatch threshold below 12%. SHA-256-identical decoded frames share the same result
within each clip; every encoded frame is decoded and counted. Phone templates can both match the same
line, so template hit counts and matching-frame counts are reported separately.

Opaque source-resolution boxes track detected quote positions with a five-frame halo. Independent,
narrow quote-column scroll corridors cover transient/partial glyphs and the jump from y=880 to y=617.
Phone list and detail windows cover partial slide-in text, with background colour sampled from the clip
(RGB 243,244,249); quote masks use white. Unaffected clips are byte-for-byte copies. Private raw
inspection frames remain under ignored `raw/` only. All review images outside `raw/` come from masked
pixels. `proof/` and the staged media are git-ignored.

This is a native-glyph detector, not a general OCR guarantee for arbitrary future fonts or layouts.
The fixed transition windows are specific to these staged takes. A replacement take requires a new audit.

### Consolidated execution evidence

```text
'''+read('execution-report.log')+'```\n\n### Real per-clip command output — raw audit\n\n```text\n'+read('before-native.log')+'```\n\n### Real per-clip command output — masked audit\n\n```text\n'+read('after-native.log')+'```\n\n### Unmasked positive control\n\n```text\n'+read('control-native.log')+'```\n\n### Detector equivalence controls\n\n```text\n'+read('detector-check.log')+'```\n\n## Edit decision lists\n\n'
    for lang in ['ar','en']:
        for fmt in ['h','v']:
            text+=f'### {lang.upper()} {"16:9" if fmt=="h" else "9:16"}\n\n'
            text+='| Beat | Output start | Slot length | Source | Source span → subslot |\n|---|---:|---:|---|---|\n'
            for s in tl[fmt]['scenes']:
                spans='; '.join(f'{a:g}–{b:g} s → {dur:g} s' for n,a,b,dur in s['spans_by_language'][lang])
                names=', '.join(dict.fromkeys(n if n.startswith('opening') else 'masked/'+lang+'/'+n+'.mp4' for n,*_ in s['spans_by_language'][lang]))
                text+=f'| {s["beat"]} | {s["start"]:g} s | {s["duration"]:g} s | {names} | {spans} |\n'
            outro='outro-'+('16x9' if fmt=='h' else '9x16')+('' if lang=='ar' else '-en')+'.mp4'
            text+=f'| 15 | {tl[fmt]["body"]} s | {tl[fmt]["outro"]} s nominal | `../../renders/{outro}` | Full approved file, unchanged |\n\n'
    text+='''The shot clocks skip navigation/dead time; explicit static subslots hold decision results for at least 1.5 s. Beat 13
uses a kinetic counter (AR 300 EGP; EN 200 EGP), with the recorded per-line values in the plate. Quote
figures are AR 24,640 / EN 24,440; compare gap EGP 200; ledger AR 1,560 / EN 1,760.
The disclosure pill uses the approved copy from beat 1 until the outro. Vertical captions sit below
250 px and above the bottom 350 px platform-safe boundaries; the pill is at y=1500. Final visual QA
must confirm crop focus, reading size and transitions after Chrome rendering; static syntax checks
cannot certify those visual properties.

## Audio measurements — actual master and AAC preview output

Music starts at 0:00 for 16:9 and 2:00 for 9:16, at −6.6 dB with a 0.5 s fade-in, then the original
outro audio. A −3 dBFS sample limiter runs before AAC 256 kb/s. Measurements below are for the supplied
audio masters/previews, not nonexistent final video files. `proof/audio.json` retains numeric results.

```text
'''+read('audio.log')+'```\n\nLatest vertical mixes retain the complete approved audio tail (the nominal 8.5 s is rounded):\n\n```text\n'+read('audio-vertical-full-tail.log')+'```\n\n## Render blockers / unfulfilled proof\n\n'
    text+='''Chrome failed even with `--no-sandbox` and with crash reporting disabled. The sandbox returns
`setsockopt: Operation not permitted (1)` and Chrome exits with `SIGTRAP`. Full real launch output is
in `proof/chrome-check.log`; the actual v2.4 one-frame render attempt is in
`proof/render-attempt.log` and failed with the same error. No permission escalation or network access
was attempted.

`ffprobe` is also absent from this environment (`command -v ffprobe` returns no path). FFmpeg 7 is
available and used for decoding, masking, audio and measurements. The render host must supply ffprobe
to produce the requested final duration/resolution/fps/codec evidence. No final-cut ffprobe or loudness
output is invented; no final-cut review sheet is substituted with a source sheet.

Both quote sources end with the Authorise action still processing, rather than the approved
status chip requested in beat 7. The edit ends that beat on the real confirmation action and avoids a
fabricated approval chip or a frozen loading spinner. That specific result hold cannot be supplied
from these takes.

The approved script and motion-style files are unchanged. The missing final renders, contact sheets,
and final-file probe/loudness proof are the remaining work, covered by the explicit Chrome fallback.

## Files and evidence

Editable source: `privacy.py`, `matcher.c`, `check_detector.py`, `check_timeline.cjs`, `engine.js`, `index.html`, `compose.js`,
`spec_h.js`, `spec_v.js`, `render.cjs`, `extract.py`, `make_data.py`, `make_textures.py`, `timeline.json`,
`audio.py`, `finish.py`, `execution_report.py`, `review_sources.py`, `write_readme.py`, `rebuild.sh`, `.gitignore`, `README.md`.
Generated/ignored: `masked/{ar,en}/`, `proof/`, `plates/`, `data.js`, `tex/`, `audio/`, `tmp/`, Python
bytecode, and inspection PNGs under `raw/{ar,en}/`. Fonts and original MP4 inputs were already staged.
Structural scene-boundary and plate-path checks for all four cuts pass (`proof/timeline-check.log`);
these checks do not replace final visual review.
The complete generated-file inventory is in `proof/files-created-or-changed.txt`.
The orchestrator owns review and commit.
'''
    (ROOT/'README.md').write_text(text)
    print('README written from timeline and actual proof logs')
if __name__=='__main__':main()
