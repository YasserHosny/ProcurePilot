# Demo video cuts

Every rendered version of the «مطاعم سند» demo video, newest first. Each version has four cuts: Arabic and English, 16:9 (YouTube, LinkedIn, website) and 9:16 (Reels, TikTok, Shorts, WhatsApp status). App screens are Arabic in every cut; the English cuts translate the captions and callouts.

How each version was made: [`../generation-plan.md`](../generation-plan.md). Review that led to v2: [`../review-codex-2026-10-19.md`](../review-codex-2026-10-19.md).

| Version | Date | Cuts | Length (16:9 / 9:16) | What it is |
|---|---|---|---|---|
| **v2.1** (current candidate) | 2026-10-19 | [`v2.1/`](v2.1/) | 2:15 / 0:55 | v2.0 with the phone low-stock scene re-recorded after #195 (starts from the home-screen button, confirmation reads «١ لتر») and four vertical shots recropped to fill the frame. |
| v2.0 | 2026-10-19 | [`v2.0/`](v2.0/) | 2:15 / 0:55 | Codex's rebuild from its review: email masked, captions over footage instead of full-screen cards, product on screen by 3 s, decision holds, savings labelled by scope, comparison labelled as oil ×8, «بيانات تجريبية» on every caption. |
| v1 | 2026-10-19 | not in git | 3:00 / 0:59.85 | The first edit: seven full-screen cards, footage at up to 3–4×. **Shows the owner's email address** (quote review, request page, phone approval), so it stays on the recording machine (`~/Videos/pp-recording/edit/v1/`) and must not be posted. Its edit decision lists are in the generation plan and its scripts in [`../source/edit/`](../source/edit/). |

Files in each version folder: `procurepilot-demo-{ar,en}-{16x9,9x16-60s}.mp4`, H.264 30 fps + AAC 256 kb/s, about −14 LUFS integrated.

Both v2 versions were checked frame by frame for the email: `source/edit-v2/verify_output_masks.py` passes on all eight files, and v2.0's 344 proof frames were inspected by eye.

Third-party media inside the cuts: music «Antalya Beaches» by DayFox (Pixabay) and stock clips Pexels 4253325 and 31735802, used under the Pixabay and Pexels licences, which allow use inside a video; the source files themselves are not redistributed here (see [`../fetch-assets.sh`](../fetch-assets.sh)). The notification card is illustrative and the data is demo data.
