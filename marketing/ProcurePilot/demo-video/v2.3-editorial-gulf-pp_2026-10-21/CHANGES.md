# Editorial demo video, PP colours + Gulf wording + Iron Systems closing (2026-10-21)

Refinement of the approved v2.2 editorial cut. Only three changes:
1. Colours: ProcurePilot brand palette (Paper #F4F6F9, white cards, Mist #C9D6E3, Navy #0B2545 replaces black, Teal #12A594 replaces orange-red, Teal-on-dark #19B8A4 on navy). Halftone/paper textures shifted from warm to cool. Sting wordmark now two-tone (Procure navy, Pilot teal).
2. Wording (the video has no voice-over; all words are on-screen text): Egyptian phrases changed to Gulf: الموبايل→الجوال, وفّر الطلب ده→وفّر هالطلب, ثم→وبعدها (3 lines), وإحنا اللي هنجهّزه معاك→وإحنا نجهّزه وياك. Currency stays ج.م because the figures are the real demo data.
3. Iron Systems closing appended after the end card: 16:9 +4.5 s, 9:16 +4.0 s. Official metal logo PNGs from Branding/Identity-v3 unchanged, Iron Dark ground, "Developed by Iron Systems" in Inter. Audio: approved mix unchanged, ending rings out with a reverb tail of its last chord (tail.py).

Files: procurepilot-demo-ar-16x9-gulf-pp.mp4 (2:03), procurepilot-demo-ar-9x16-gulf-pp.mp4 (0:57). -14.1 / -14.3 LUFS, peaks -1.6 / -2.4 dBFS.
Source: drop source/* over a copy of docs/gtm/video/source/edit-editorial (plus is/ logo crops + Inter fonts) and render as in that README.

## 2026-11-16: company-only contact (owner)

At Yasser's request (2026-11-15) both files were updated in place, an exception to the never-overwrite rule for this
folder: the end card now shows the Iron Systems WhatsApp +20 10 5087 8238, www.iron-sys.com and hello@iron-sys.com
instead of the founder's name, his number and his personal email. The engine source was never committed, so the card's
contact lines were redrawn in place by `docs/gtm/video/source/contact-swap/gulf_patch.py`; everything else, including
the audio, is unchanged. The earlier files remain in git history.
