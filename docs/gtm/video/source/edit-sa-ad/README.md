# ProcurePilot Saudi ad — marketing cut with Saudi voiceover (PPS-220)

Requested by the owner on 2026-11-13 for the marketing and media-buying team. Unlike the demo cuts
([`../edit-v2.5/`](../edit-v2.5/)), this is an ad: a hook, a problem, the product as the answer, five benefit
chapters, the saving, and a call to action, carried by a Saudi-dialect voiceover. Script, timings and voice
direction: [`../../cuts/gcc-sa-ad-v1/script.md`](../../cuts/gcc-sa-ad-v1/script.md).

| Part | What |
|---|---|
| Picture | A new HTML engine (`index.html`, `ad.js`) rendered frame by frame with Playwright, 30 fps. Brand system from [`../../motion-style.md`](../../motion-style.md): Navy, Teal, Mist, Paper, Readex Pro, the Converge bars as wipes, the logo built from the official SVG. |
| Product | Real screens only: the round A screenshots of «مطاعم رواق» in [`../../../gcc/rounds/screens/ar/`](../../../gcc/rounds/screens/ar/) (email already masked), shown as plates with a camera and highlight rings. Nothing is redrawn or patched. The problem scene uses the round A quotes ([`../../../gcc/setup/quotes/round-A/`](../../../gcc/setup/quotes/round-A/)) and the Saudi opening animation ([`../../renders/sa/`](../../renders/sa/)). |
| Figures | From round A: الذهبي ١٬٥٢٠ ر.س against الوفرة ١٬٥٦٠ ر.س on 10 tins of oil (٤٠ ر.س), and ١٩٠ ر.س saved on the order against the last purchase price. |
| Voice | Generated, not recorded: ElevenLabs Eleven v4 through Higgsfield, preset voice «Callum», chosen by the owner from two auditions on 2026-11-13. It is one take of the nine lines with a performance direction on each, plus a separate re-take of line 7 (`vo/elevenlabs-full.mp3`, `vo/elevenlabs-line7.mp3`, text and directions in `vo/script.json`). `align_vo.py` cuts it into `vo/s1…s9.mp3` at the measured pauses and estimates word timings (the engine returns none): phrase starts are measured, words inside a phrase are spread by their relative lengths in `vo/reference-word-lengths.json`. `prep_vo.py` shortens long pauses and places the lines. The first build used the Microsoft voice `ar-SA-HamedNeural` (`vo_gen_edge.py`); the owner found it flat and machine-like. |
| Timing | Every scene and every kinetic line is placed from the word timings (`timeline.json`), so type lands on the spoken word. |
| Sync | Both streams start at 0 in the file. Phrase starts in the timeline are within 0.03 s of the voice's measured onsets, and picture cues lead the voice by 0.10 s (`LEAD` in `ad.js`), so a word is on screen just before it is heard (owner, 2026-11-13: the sound must not run ahead of the picture). Measured on the rendered 16:9 cut: «كم» 0.16 s, «قارن» 0.14 s and «اختار» 0.10 s ahead of the voice. |
| Music | «Antalya Beaches» by DayFox, the track the other cuts use ([`../../fetch-assets.sh`](../../fetch-assets.sh)). It is offset so its chorus (track 0:53.47) lands on «كم وفّرنا؟», ducked under the voice, and held lower through the chorus. |
| Sound effects | Synthesised in `audio.py` (whoosh, tick, pop, thump, chime, riser), placed on the same word timings. No third-party effect files. |
| Mix | −14 LUFS, true peak ≤ −1.4 dBFS. The voice is at least 9 dB above music and effects in every scene (measured per scene). |
| No-voiceover cuts | `audio.py` also writes `build/mix-novo.wav`: the music at one steady level (nothing to duck under) and the same effects, at −14 LUFS. `rebuild.sh` muxes it onto the rendered picture without re-encoding it, as `…-no-vo.mp4` beside each cut, so the picture is bit-identical to the voiced cut (owner, 2026-11-13). |
| Captions | `build/captions.srt`, copied beside the cuts, from the same word timings. |

## Rebuild

```bash
bash ../../fetch-assets.sh
```

```bash
mkdir -p fonts && curl -fsSL -o fonts/ReadexPro.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/readexpro/ReadexPro%5BHEXP%2Cwght%5D.ttf"
```

```bash
./rebuild.sh
```

`rebuild.sh h` or `rebuild.sh v` builds one format. The Pexels clips in `fetch-assets.sh` are not used here; if
they fail to download, the music line is the one that matters.

Write the text sent to the voice with vowel marks (تشكيل) wherever a word can be read two ways (owner,
2026-11-13): the first take read «الطلب يتجهّز لك مسودة» wrongly until it was marked. The marked text goes in
`vo/script.json` as `tts`; `text` stays unmarked for captions.

To replace the voiceover (a new take, or a recorded voice artist): put the one-take file at
`vo/elevenlabs-full.mp3` or the nine lines at `vo/s1…s9.mp3`, update the pause table in `align_vo.py` (or write
`vo/raw-timing.json` by hand: per word, start and length in seconds from the start of its line file), then
rebuild. The scenes follow the new timings. If the wording changes, `ad.js` addresses words by index, so check
each scene's `T(k)` calls against the new word list.

## Limits

- The voice is synthetic. The owner picked it by ear from a ten-second audition; the full take has not been
  listened to end to end by anyone when this was written. A recorded Saudi voice artist remains the surest way
  to a native read.
- Word timings inside a phrase are estimates (about a tenth of a second), so a kinetic word can land slightly
  early or late; phrase starts are measured.
- The screens are stills from the recorded round, so there is no live cursor; motion comes from the camera,
  the rings and the phone tap mark. Some stills carry the recording's own pointer.
- The end card uses the existing contact (WhatsApp +20 102 735 4140, iron-sys.com); a Saudi contact is still
  to come from the owner ([`../../../gcc/script-saudi.md`](../../../gcc/script-saudi.md)).
