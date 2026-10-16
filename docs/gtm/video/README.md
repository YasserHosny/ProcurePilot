# Demo video — spec and decisions (PP-6)

Status 2026-10-15: **logo sting + end card rendered and approved** (`renders/`); the 3-minute screencast and the
60-second cut are not recorded yet — they wait on the demo tenant (PP-5), which waits on #73-era
product work being verified on hosted.

Design source for every animated element (logo sting, end cards):
<https://claude.ai/artifact/CYVrF8484uFkpiJTqcGPdS> — boards 5–13 (10–13 are the English versions).

## Formats

| Cut | Ratio | Length | Use |
|---|---|---|---|
| Full | 16:9, 1920×1080, 30 fps | 3:00 | DM attachment, YouTube/LinkedIn |
| Short | 9:16, 1080×1920, 30 fps | 0:60 | WhatsApp Status, Reels, LinkedIn mobile |

## Style (decided)

- **Whole video:** screencast of the real product (web + phone) as the backbone, with a 2D
  motion-graphics layer — zoom-ins, highlights, Arabic text cards, an animated counter for the
  saving. **No 3D, no voice-over.** Text + music, because WhatsApp/LinkedIn/Reels autoplay muted.
- **Phone scenes:** the Flutter app running as a web build in Chrome at 390×844, placed in a
  phone frame in the edit (no Android emulator: not installed, root disk too full). Push
  notifications don't exist on web → a text card «وصل إشعار للمدير» then the approval screen.
- **Opening shot:** free real stock footage (Pexels/Pixabay) of a kitchen/storeroom, not AI video.
- **Honesty rules:** RFQs are *sent by a person*; guardrail auto-prep creates a *draft purchase
  request*; mobile approves the *request*; the PO is generated on web. Every number on screen comes
  from the demo tenant's real savings report.

## Storyboard (3:00) and music map

Music: **Antalya Beaches — DayFox** (below). Its sections line up with the story:

| Video | Scene | Music section |
|---|---|---|
| 0:00–0:25 | Pain: WhatsApp quotes + Excel; promise line | Intro, calm (0:00–0:09) → section A |
| 0:25–1:05 | Low-stock report on phone → RFQ built → sent to 3 suppliers in one click | Section A, building |
| 1:05–1:40 | Quotes arrive (email + forwarded WhatsApp photo), extracted, incl. ج.م | **Chorus 1 (0:52–1:26)** |
| 1:40–2:20 | Line-by-line comparison, saving in EGP; guardrail drafts the request | Breakdown (1:28–2:20) |
| 2:20–2:50 | Manager approves on phone → PO generated → savings report | **Chorus 2 (2:20–2:46)** |
| **2:50.25–2:54.75** | **Logo sting** | Outro |
| 2:54.75–3:00 | **End card** (CTA, 5.23 s) | Track's natural end at 3:00 |

60-second cut: uses the track's last minute (2:00 → 3:00); fast sting on the beat at track
**2:51.34** (0:51.3 into the cut), end card 5.5 s — the outro ends at 0:59.8, inside the cut.

## Logo sting (decided)

- Converge mark animation, 2D vector motion graphics: grey bars slide in → teal bar grows past
  them → arrowhead pops (one small overshoot) with a two-ghost speed trail → "ProcurePilot"
  revealed left-to-right, pushed by the arrow.
- **Tagline «قارن. اختار. وفّر.»**, one word per bar (mask slide-up, right-to-left order); «وفّر.»
  in teal. **No English line in the Arabic video** — the English version is a separate render (below).
- **Beat-locked** to the track (112.35 BPM, beat = 0.5341 s), cycle 4.5 s:

| Beat | Time | Visual | Sound |
|---|---|---|---|
| 1 | 0.534 s | first grey bar + «قارن.» | tick |
| 1.5 | 0.801 s | second grey bar | tick |
| 1.5→2.5 | 0.80–1.34 s | teal bar grows + «اختار.» | rising swish (at 1.9 beats) |
| **3** | **1.602 s** | **arrow pop + trail + «وفّر.»** | **pop** (loudest; music dips 3 dB) |
| 3.5→5 | 1.87–2.67 s | name reveal | soft whoosh |
| **5** | **2.671 s** | name complete | **chime** (brand sound) |
| 8 | 4.27 s | hold ends, fade | — |

- **Fast version (60-s cut):** same keyframes at 2/3 duration (3.0 s cycle) — pop on beat 2.
- Measured on the render: the pop transient lands within 8 ms of its beat in both versions.

## End card (decided)

Navy, follows the sting seamlessly; elements fade up 0.27 s apart: logo · «جرّبه أسبوعين مجانًا» ·
«وإحنا اللي هنجهّزه معاك.» · WhatsApp **+20 102 735 4140** (large, teal, screenshot-able) ·
«د. ياسر حسني — المؤسس» · yasser.hosny@iron-sys.com · «أحد منتجات Iron Systems». The 9:16 card keeps
everything inside the WhatsApp/Reels safe area (top ~250 px, bottom ~350 px).

## English versions (for LinkedIn / non-Arabic viewers)

Same keyframes, beats, sound cues and mix as the Arabic outro — only the text changes:

- **Sting tagline:** "Compare. Choose. Save." — one word per bar, revealed left-to-right; "Save." in teal.
- **End card (LTR):** logo · **Try it free for 2 weeks** · "— we set it up with you." · WhatsApp
  **+20 102 735 4140** · "Dr. Yasser Hosny — Founder" · yasser.hosny@iron-sys.com · "A product of Iron Systems".
- Canvas boards 10–13 on the logo canvas (`AnimEn16x9`, `EndCardEn16x9`, `AnimEn9x16Fast`, `EndCardEn9x16`).
- Same placement as the Arabic outros (2:50.25 in the 3-minute cut, 0:51.34 in the 60-second cut).

## Audio (decided)

| Item | Choice | Source / licence |
|---|---|---|
| Music | Antalya Beaches — DayFox (3:07, soft house, 112.35 BPM) | [Pixabay](https://pixabay.com/music/soft-house-antalya-beaches-119047/) · Pixabay Content License · **Content ID registered** (YouTube may auto-claim; dispute with the licence) |
| Tick | Soft UI Pop – light, minimal click — humordome (first click only, 0.02–0.15 s) | [Pixabay](https://pixabay.com/sound-effects/technology-soft-ui-pop-light-minimal-click-451232/) |
| Swish | Short Swoosh Whoosh — biww | [Pixabay](https://pixabay.com/sound-effects/film-special-effects-short-swoosh-whoosh-sound-561933/) |
| Pop | Clean Minimal Pop — DRAGON-STUDIO | [Pixabay](https://pixabay.com/sound-effects/clean-minimal-pop-467466/) |
| Whoosh | Soft luxury air whoosh #8 — Sdanezis | [Pixabay](https://pixabay.com/sound-effects/film-special-effects-soft-luxury-air-whoosh-8-592506/) |
| Chime | Positive Notification — Universfield | [Pixabay](https://pixabay.com/sound-effects/film-special-effects-positive-notification-351299/) |

All Pixabay Content License: free commercial use, no attribution required. Audio files are not
committed (re-download from the links); `music/antalya-beaches-beats.csv` holds the 334 beat
times from librosa so alignment can be redone without re-analysing.

Mix: music −4 dB under cues; cue gains tick −6, swish −4, pop 0, whoosh −6, chime −3 dB; final
loudness ≈ −14 LUFS for the outros (social standard), peaks ≤ −1.6 dBFS on every file.

## Rendered files

| File | Length | Note |
|---|---|---|
| `outro-16x9.mp4` | 9.75 s | sting + end card, one continuous mix — **place at 2:50.25; ends at 3:00** |
| `outro-9x16.mp4` | 8.5 s | fast sting + end card — **place at 0:51.34 of the 60-s cut; ends at 0:59.8** |
| `logo-sting-16x9.mp4`, `end-card-16x9.mp4`, `logo-sting-9x16-fast.mp4`, `end-card-9x16.mp4` | — | separate pieces for flexible editing |
| `outro-16x9-en.mp4`, `outro-9x16-en.mp4` | 9.75 s / 8.5 s | English outros — same placement and audio as the Arabic ones |
| `logo-sting-16x9-en.mp4`, `end-card-16x9-en.mp4`, `logo-sting-9x16-fast-en.mp4`, `end-card-9x16-en.mp4` | — | English separate pieces |

Approved by the user 2026-10-15; in `renders/`. Re-rendered 2026-10-15 with the founder title
«د. ياسر حسني» / "Dr. Yasser Hosny"; English versions added the same day.

## Rebuilding

`source/render_frames.js` renders a canvas board frame-by-frame (Playwright + Chrome; pauses every
CSS animation and seeks it with the Web Animations API, 30 fps). `source/mix_audio.py` trims the
cues and mixes music + cues with ffmpeg (`imageio-ffmpeg`). Both scripts carry absolute scratch
paths from the session that made them — edit the paths at the top before reuse.

## Open

What is left before recording, with owners and status: [`production-tracker.md`](production-tracker.md).

- Record the screencast (needs PP-5 demo tenant + a full live run on hosted).
- Optional later: the same bars→winner→arrow motion as a Lottie loader in web/Flutter (code task).
