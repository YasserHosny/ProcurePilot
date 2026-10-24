# ProcurePilot v2.4 — Ledger UI edit

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
ar/s0-phone-lowstock.mp4 frames=673 before_matching_frames=0 before_hits=0 after_hits=0
ar/s1-rfq.mp4 frames=1333 before_matching_frames=0 before_hits=0 after_hits=0
ar/s2-quote-photo.mp4 frames=982 before_matching_frames=481 before_hits=481 after_hits=0
ar/s3-guardrail-draft.mp4 frames=865 before_matching_frames=0 before_hits=0 after_hits=0
ar/s3c-smart-compare.mp4 frames=972 before_matching_frames=0 before_hits=0 after_hits=0
ar/s4-phone-approve.mp4 frames=482 before_matching_frames=304 before_hits=612 after_hits=0
ar/s5-po-savings.mp4 frames=1333 before_matching_frames=0 before_hits=0 after_hits=0
ar/s6-savings-close.mp4 frames=508 before_matching_frames=0 before_hits=0 after_hits=0
en/s0-phone-lowstock.mp4 frames=667 before_matching_frames=0 before_hits=0 after_hits=0
en/s1-rfq.mp4 frames=1339 before_matching_frames=0 before_hits=0 after_hits=0
en/s2-quote-photo.mp4 frames=978 before_matching_frames=484 before_hits=484 after_hits=0
en/s3-guardrail-draft.mp4 frames=856 before_matching_frames=0 before_hits=0 after_hits=0
en/s3c-smart-compare.mp4 frames=982 before_matching_frames=0 before_hits=0 after_hits=0
en/s4-phone-approve.mp4 frames=484 before_matching_frames=305 before_hits=606 after_hits=0
en/s5-po-savings.mp4 frames=1382 before_matching_frames=0 before_hits=0 after_hits=0
en/s6-savings-close.mp4 frames=506 before_matching_frames=0 before_hits=0 after_hits=0
TOTAL frames=14342 before_matching_frames=1574 after_hits=0
CONTROL ar/s2-quote-photo.mp4 frames=982 matching_frames=481 hits=481
AUDIO ar-h PCM_duration=110.749333s AAC_duration=00:01:50.75 I=-14.8_LUFS TP=-2.2_dBFS
AUDIO ar-v PCM_duration=59.512000s AAC_duration=00:00:59.51 I=-13.8_LUFS TP=-3.0_dBFS
AUDIO en-h PCM_duration=110.749333s AAC_duration=00:01:50.75 I=-14.8_LUFS TP=-2.2_dBFS
AUDIO en-v PCM_duration=59.512000s AAC_duration=00:00:59.51 I=-13.8_LUFS TP=-3.0_dBFS
FINAL_VIDEO_PROOF unavailable: Chrome setsockopt EPERM / SIGTRAP; no final MP4s or final-cut sheets generated
FILE_LIST proof/files-created-or-changed.txt
```

### Real per-clip command output — raw audit

```text
BEFORE ar/s0-phone-lowstock.mp4 frames 673 matching_frames 0 matches 0
BEFORE ar/s1-rfq.mp4 frames 1333 matching_frames 0 matches 0
BEFORE ar/s2-quote-photo.mp4 frames 982 matching_frames 481 matches 481
BEFORE ar/s3-guardrail-draft.mp4 frames 865 matching_frames 0 matches 0
BEFORE ar/s3c-smart-compare.mp4 frames 972 matching_frames 0 matches 0
BEFORE ar/s4-phone-approve.mp4 frames 482 matching_frames 304 matches 612
BEFORE ar/s5-po-savings.mp4 frames 1333 matching_frames 0 matches 0
BEFORE ar/s6-savings-close.mp4 frames 508 matching_frames 0 matches 0
BEFORE en/s0-phone-lowstock.mp4 frames 667 matching_frames 0 matches 0
BEFORE en/s1-rfq.mp4 frames 1339 matching_frames 0 matches 0
BEFORE en/s2-quote-photo.mp4 frames 978 matching_frames 484 matches 484
BEFORE en/s3-guardrail-draft.mp4 frames 856 matching_frames 0 matches 0
BEFORE en/s3c-smart-compare.mp4 frames 982 matching_frames 0 matches 0
BEFORE en/s4-phone-approve.mp4 frames 484 matching_frames 305 matches 606
BEFORE en/s5-po-savings.mp4 frames 1382 matching_frames 0 matches 0
BEFORE en/s6-savings-close.mp4 frames 506 matching_frames 0 matches 0
```

### Real per-clip command output — masked audit

```text
AFTER ar/s0-phone-lowstock.mp4 frames 673 matching_frames 0 matches 0
AFTER ar/s1-rfq.mp4 frames 1333 matching_frames 0 matches 0
AFTER ar/s2-quote-photo.mp4 frames 982 matching_frames 0 matches 0
AFTER ar/s3-guardrail-draft.mp4 frames 865 matching_frames 0 matches 0
AFTER ar/s3c-smart-compare.mp4 frames 972 matching_frames 0 matches 0
AFTER ar/s4-phone-approve.mp4 frames 482 matching_frames 0 matches 0
AFTER ar/s5-po-savings.mp4 frames 1333 matching_frames 0 matches 0
AFTER ar/s6-savings-close.mp4 frames 508 matching_frames 0 matches 0
AFTER en/s0-phone-lowstock.mp4 frames 667 matching_frames 0 matches 0
AFTER en/s1-rfq.mp4 frames 1339 matching_frames 0 matches 0
AFTER en/s2-quote-photo.mp4 frames 978 matching_frames 0 matches 0
AFTER en/s3-guardrail-draft.mp4 frames 856 matching_frames 0 matches 0
AFTER en/s3c-smart-compare.mp4 frames 982 matching_frames 0 matches 0
AFTER en/s4-phone-approve.mp4 frames 484 matching_frames 0 matches 0
AFTER en/s5-po-savings.mp4 frames 1382 matching_frames 0 matches 0
AFTER en/s6-savings-close.mp4 frames 506 matching_frames 0 matches 0
```

### Unmasked positive control

```text
CONTROL ar/s2-quote-photo.mp4 frames 982 matching_frames 481 matches 481
```

### Detector equivalence controls

```text
DETECTOR_EQUIVALENCE ar s2-quote-photo 8s matches=1
DETECTOR_EQUIVALENCE en s2-quote-photo 8s matches=1
DETECTOR_EQUIVALENCE ar s4-phone-approve 5s matches=2
DETECTOR_EQUIVALENCE en s4-phone-approve 5s matches=2
DETECTOR_EQUIVALENCE ar s4-phone-approve 9s matches=2
DETECTOR_EQUIVALENCE en s4-phone-approve 9s matches=2
DETECTOR_EQUIVALENCE ar s1-rfq 20s matches=0
PASS: seven native-resolution positive/negative controls; C and NumPy agree
```

## Edit decision lists

### AR 16:9

| Beat | Output start | Slot length | Source | Source span → subslot |
|---|---:|---:|---|---|
| 0 | 0 s | 4 s | opening-h | 0–4 s → 4 s |
| 1 | 4 s | 6 s | masked/ar/s5-po-savings.mp4 | 26–28 s → 3 s; 42–42 s → 3 s |
| 2 | 10 s | 7 s | masked/ar/s0-phone-lowstock.mp4 | 1.5–3.5 s → 1 s; 11–20.5 s → 4 s; 21.8–22.1 s → 2 s |
| 3 | 17 s | 11 s | masked/ar/s1-rfq.mp4 | 4–18 s → 3 s; 24–34 s → 3.5 s; 40.5–43.3 s → 3 s; 44.2–44.2 s → 1.5 s |
| 5 | 28 s | 5 s | masked/ar/s2-quote-photo.mp4 | 0.3–4.8 s → 5 s |
| 6 | 33 s | 12 s | masked/ar/s2-quote-photo.mp4 | 8–11 s → 3 s; 22–23 s → 3 s; 24–25 s → 4 s; 8.5–8.5 s → 2 s |
| 7 | 45 s | 5 s | masked/ar/s2-quote-photo.mp4 | 24.5–26.5 s → 3.5 s; 26.5–26.5 s → 1.5 s |
| 8 | 50 s | 11 s | masked/ar/s3c-smart-compare.mp4 | 10.5–14 s → 3 s; 20–27 s → 5.5 s; 29–29 s → 2.5 s |
| 10 | 61 s | 10 s | masked/ar/s3-guardrail-draft.mp4 | 5–10 s → 4 s; 16–22 s → 4 s; 22.5–24.1 s → 2 s |
| 11 | 71 s | 8 s | masked/ar/s4-phone-approve.mp4 | 5–5.5 s → 1 s; 7–8 s → 2 s; 13.5–15.4 s → 3 s; 15.8–15.8 s → 2 s |
| 12 | 79 s | 9 s | masked/ar/s5-po-savings.mp4 | 3–9 s → 2.5 s; 13–20 s → 2.5 s; 22–23.2 s → 2 s; 26–26 s → 2 s |
| 13 | 88 s | 7 s | masked/ar/s5-po-savings.mp4 | 32–35 s → 2 s; 36–38.5 s → 3 s; 42–42 s → 2 s |
| 14 | 95 s | 6 s | masked/ar/s6-savings-close.mp4 | 4–8 s → 6 s |
| 15 | 101 s | 9.75 s nominal | `../../renders/outro-16x9.mp4` | Full approved file, unchanged |

### AR 9:16

| Beat | Output start | Slot length | Source | Source span → subslot |
|---|---:|---:|---|---|
| 0 | 0 s | 3 s | opening-v | 0–3 s → 3 s |
| 1 | 3 s | 4 s | masked/ar/s5-po-savings.mp4 | 42–42 s → 4 s |
| 3 | 7 s | 6 s | masked/ar/s1-rfq.mp4 | 24–28 s → 3 s; 40.5–43.3 s → 1.5 s; 44.2–44.2 s → 1.5 s |
| 5 | 13 s | 3 s | masked/ar/s2-quote-photo.mp4 | 0.3–4.8 s → 3 s |
| 6 | 16 s | 7 s | masked/ar/s2-quote-photo.mp4 | 8–11 s → 2 s; 24–25 s → 3 s; 8.5–8.5 s → 2 s |
| 7 | 23 s | 3 s | masked/ar/s2-quote-photo.mp4 | 24.5–26.5 s → 1.5 s; 26.5–26.5 s → 1.5 s |
| 8 | 26 s | 7 s | masked/ar/s3c-smart-compare.mp4 | 20–27 s → 5 s; 29–29 s → 2 s |
| 10 | 33 s | 5 s | masked/ar/s3-guardrail-draft.mp4 | 5–10 s → 3 s; 20–23 s → 2 s |
| 11 | 38 s | 5 s | masked/ar/s4-phone-approve.mp4 | 7–8 s → 1 s; 13.5–15.4 s → 2 s; 15.8–15.8 s → 2 s |
| 12 | 43 s | 4 s | masked/ar/s5-po-savings.mp4 | 22–23.2 s → 2 s; 26–26 s → 2 s |
| 13 | 47 s | 4 s | masked/ar/s5-po-savings.mp4 | 36–38.5 s → 2 s; 42–42 s → 2 s |
| 15 | 51 s | 8.5 s nominal | `../../renders/outro-9x16.mp4` | Full approved file, unchanged |

### EN 16:9

| Beat | Output start | Slot length | Source | Source span → subslot |
|---|---:|---:|---|---|
| 0 | 0 s | 4 s | opening-h | 0–4 s → 4 s |
| 1 | 4 s | 6 s | masked/en/s5-po-savings.mp4 | 26–28 s → 3 s; 44.5–44.5 s → 3 s |
| 2 | 10 s | 7 s | masked/en/s0-phone-lowstock.mp4 | 1.5–3.5 s → 1 s; 11–20.5 s → 4 s; 21.8–22.1 s → 2 s |
| 3 | 17 s | 11 s | masked/en/s1-rfq.mp4 | 4–18 s → 3 s; 24–34 s → 3.5 s; 40.5–43.3 s → 3 s; 44.2–44.2 s → 1.5 s |
| 5 | 28 s | 5 s | masked/en/s2-quote-photo.mp4 | 0.3–4.8 s → 5 s |
| 6 | 33 s | 12 s | masked/en/s2-quote-photo.mp4 | 8–11 s → 3 s; 22–23 s → 3 s; 24–25 s → 4 s; 8.5–8.5 s → 2 s |
| 7 | 45 s | 5 s | masked/en/s2-quote-photo.mp4 | 24.5–26.5 s → 3.5 s; 26.5–26.5 s → 1.5 s |
| 8 | 50 s | 11 s | masked/en/s3c-smart-compare.mp4 | 10.5–14 s → 3 s; 20–27 s → 5.5 s; 29–29 s → 2.5 s |
| 10 | 61 s | 10 s | masked/en/s3-guardrail-draft.mp4 | 5–10 s → 4 s; 16–22 s → 4 s; 22.5–24.1 s → 2 s |
| 11 | 71 s | 8 s | masked/en/s4-phone-approve.mp4 | 5–5.5 s → 1 s; 7–8 s → 2 s; 13.5–15.4 s → 3 s; 15.8–15.8 s → 2 s |
| 12 | 79 s | 9 s | masked/en/s5-po-savings.mp4 | 3–9 s → 2.5 s; 13–20 s → 2.5 s; 22–23.2 s → 2 s; 26–26 s → 2 s |
| 13 | 88 s | 7 s | masked/en/s5-po-savings.mp4 | 32–35 s → 2 s; 38–40.3 s → 3 s; 44.5–44.5 s → 2 s |
| 14 | 95 s | 6 s | masked/en/s6-savings-close.mp4 | 4–8 s → 6 s |
| 15 | 101 s | 9.75 s nominal | `../../renders/outro-16x9-en.mp4` | Full approved file, unchanged |

### EN 9:16

| Beat | Output start | Slot length | Source | Source span → subslot |
|---|---:|---:|---|---|
| 0 | 0 s | 3 s | opening-v | 0–3 s → 3 s |
| 1 | 3 s | 4 s | masked/en/s5-po-savings.mp4 | 44.5–44.5 s → 4 s |
| 3 | 7 s | 6 s | masked/en/s1-rfq.mp4 | 24–28 s → 3 s; 40.5–43.3 s → 1.5 s; 44.2–44.2 s → 1.5 s |
| 5 | 13 s | 3 s | masked/en/s2-quote-photo.mp4 | 0.3–4.8 s → 3 s |
| 6 | 16 s | 7 s | masked/en/s2-quote-photo.mp4 | 8–11 s → 2 s; 24–25 s → 3 s; 8.5–8.5 s → 2 s |
| 7 | 23 s | 3 s | masked/en/s2-quote-photo.mp4 | 24.5–26.5 s → 1.5 s; 26.5–26.5 s → 1.5 s |
| 8 | 26 s | 7 s | masked/en/s3c-smart-compare.mp4 | 20–27 s → 5 s; 29–29 s → 2 s |
| 10 | 33 s | 5 s | masked/en/s3-guardrail-draft.mp4 | 5–10 s → 3 s; 20–23 s → 2 s |
| 11 | 38 s | 5 s | masked/en/s4-phone-approve.mp4 | 7–8 s → 1 s; 13.5–15.4 s → 2 s; 15.8–15.8 s → 2 s |
| 12 | 43 s | 4 s | masked/en/s5-po-savings.mp4 | 22–23.2 s → 2 s; 26–26 s → 2 s |
| 13 | 47 s | 4 s | masked/en/s5-po-savings.mp4 | 38–40.3 s → 2 s; 44.5–44.5 s → 2 s |
| 15 | 51 s | 8.5 s nominal | `../../renders/outro-9x16-en.mp4` | Full approved file, unchanged |

The shot clocks skip navigation/dead time; explicit static subslots hold decision results for at least 1.5 s. Beat 13
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
ar-h.wav Summary:

  Integrated loudness:
    I:         -14.8 LUFS
    Threshold: -24.8 LUFS

  Loudness range:
    LRA:         7.3 LU
    Threshold: -34.7 LUFS
    LRA low:   -19.1 LUFS
    LRA high:  -11.7 LUFS

  True peak:
    Peak:       -2.3 dBFS
ar-h.m4a Summary:

  Integrated loudness:
    I:         -14.8 LUFS
    Threshold: -24.9 LUFS

  Loudness range:
    LRA:         7.3 LU
    Threshold: -34.8 LUFS
    LRA low:   -19.1 LUFS
    LRA high:  -11.8 LUFS

  True peak:
    Peak:       -2.2 dBFS
ar-v.wav Summary:

  Integrated loudness:
    I:         -13.7 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.8 LU
    Threshold: -33.6 LUFS
    LRA low:   -17.2 LUFS
    LRA high:  -11.4 LUFS

  True peak:
    Peak:       -2.8 dBFS
ar-v.m4a Summary:

  Integrated loudness:
    I:         -13.8 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.9 LU
    Threshold: -33.7 LUFS
    LRA low:   -17.3 LUFS
    LRA high:  -11.5 LUFS

  True peak:
    Peak:       -3.0 dBFS
en-h.wav Summary:

  Integrated loudness:
    I:         -14.8 LUFS
    Threshold: -24.8 LUFS

  Loudness range:
    LRA:         7.3 LU
    Threshold: -34.7 LUFS
    LRA low:   -19.1 LUFS
    LRA high:  -11.7 LUFS

  True peak:
    Peak:       -2.3 dBFS
en-h.m4a Summary:

  Integrated loudness:
    I:         -14.8 LUFS
    Threshold: -24.9 LUFS

  Loudness range:
    LRA:         7.3 LU
    Threshold: -34.8 LUFS
    LRA low:   -19.1 LUFS
    LRA high:  -11.8 LUFS

  True peak:
    Peak:       -2.2 dBFS
en-v.wav Summary:

  Integrated loudness:
    I:         -13.7 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.8 LU
    Threshold: -33.6 LUFS
    LRA low:   -17.2 LUFS
    LRA high:  -11.4 LUFS

  True peak:
    Peak:       -2.8 dBFS
en-v.m4a Summary:

  Integrated loudness:
    I:         -13.8 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.9 LU
    Threshold: -33.7 LUFS
    LRA low:   -17.3 LUFS
    LRA high:  -11.5 LUFS

  True peak:
    Peak:       -3.0 dBFS
```

Latest vertical mixes retain the complete approved audio tail (the nominal 8.5 s is rounded):

```text
ar-v.wav Summary:

  Integrated loudness:
    I:         -13.7 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.8 LU
    Threshold: -33.6 LUFS
    LRA low:   -17.2 LUFS
    LRA high:  -11.4 LUFS

  True peak:
    Peak:       -2.8 dBFS
ar-v.m4a Summary:

  Integrated loudness:
    I:         -13.8 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.9 LU
    Threshold: -33.7 LUFS
    LRA low:   -17.3 LUFS
    LRA high:  -11.5 LUFS

  True peak:
    Peak:       -3.0 dBFS
en-v.wav Summary:

  Integrated loudness:
    I:         -13.7 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.8 LU
    Threshold: -33.6 LUFS
    LRA low:   -17.2 LUFS
    LRA high:  -11.4 LUFS

  True peak:
    Peak:       -2.8 dBFS
en-v.m4a Summary:

  Integrated loudness:
    I:         -13.8 LUFS
    Threshold: -23.8 LUFS

  Loudness range:
    LRA:         5.9 LU
    Threshold: -33.7 LUFS
    LRA low:   -17.3 LUFS
    LRA high:  -11.5 LUFS

  True peak:
    Peak:       -3.0 dBFS
```

## Render blockers / unfulfilled proof

Chrome failed even with `--no-sandbox` and with crash reporting disabled. The sandbox returns
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
