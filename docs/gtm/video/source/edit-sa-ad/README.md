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
| Voice | Generated, not recorded: Microsoft neural voice `ar-SA-HamedNeural` through `edge-tts` (`vo_gen.py`), one file per line in `vo/` with word timings in `vo/raw-timing.json`. `prep_vo.py` shortens long pauses and places the lines. |
| Timing | Every scene and every kinetic line is placed from the word timings (`timeline.json`), so type lands on the spoken word. |
| Music | «Antalya Beaches» by DayFox, the track the other cuts use ([`../../fetch-assets.sh`](../../fetch-assets.sh)). It is offset so its chorus (track 0:53.47) lands on «كم وفّرنا؟», ducked under the voice, and held lower through the chorus. |
| Sound effects | Synthesised in `audio.py` (whoosh, tick, pop, thump, chime, riser), placed on the same word timings. No third-party effect files. |
| Mix | −14 LUFS, true peak ≤ −1.4 dBFS. The voice is at least 9 dB above music and effects in every scene (measured per scene). |
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
they fail to download, the music line is the one that matters. To change the voiceover text, edit
`vo/script.json`, run `python3 vo_gen.py vo/script.json vo`, copy `vo/timing.json` over `vo/raw-timing.json`,
then rebuild: the scenes follow the new timings, but `ad.js` addresses words by index, so check each scene's
`T(k)` calls against the new word list.

## Limits

- The voice is synthetic. It reads Saudi-dialect copy in a Saudi voice, but nobody has listened to it for
  dialect and pronunciation in this build; the owner's ear is the check. A recorded Saudi voice artist can
  replace `vo/*.mp3` with the same line split.
- The screens are stills from the recorded round, so there is no live cursor; motion comes from the camera,
  the rings and the phone tap mark. Some stills carry the recording's own pointer.
- The end card uses the existing contact (WhatsApp +20 102 735 4140, iron-sys.com); a Saudi contact is still
  to come from the owner ([`../../../gcc/script-saudi.md`](../../../gcc/script-saudi.md)).
