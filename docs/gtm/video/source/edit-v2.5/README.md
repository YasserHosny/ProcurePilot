# ProcurePilot v2.5: problem chapter, logo turn, saving page, recap (every market)

Owner-approved on 2026-10-27 after review rounds on the Egyptian Arabic 16:9 cut (PPS-83). This one build
makes all twelve v2.5 cuts. Each market keeps its own footage and beats 1–14 exactly as its v1 fork cut them.
The fork's committed `timeline.json` is the source of spans and caption cards:

| Market | v1 fork | Languages | Cuts |
|---|---|---|---|
| `eg`: «مطاعم سند» | [`../edit-v2.4/`](../edit-v2.4/) | ar, en | [`../../cuts/v2.5/`](../../cuts/v2.5/) |
| `sa`: «مطاعم رواق» | [`../edit-sa/`](../edit-sa/) | ar, en | [`../../cuts/gcc-sa-v2/`](../../cuts/gcc-sa-v2/) |
| `sa-en`: Rawaq Restaurant Group | [`../edit-sa-en/`](../edit-sa-en/) | en | [`../../cuts/gcc-sa-en-v2/`](../../cuts/gcc-sa-en-v2/) |
| `ie`: Liffey Kitchen Group | [`../edit-ie/`](../edit-ie/) | en | [`../../cuts/eu-en-v2/`](../../cuts/eu-en-v2/) |

## What v2.5 adds

| Scene | 16:9 | 9:16 | What |
|---|---|---|---|
| Problem 1 | 2.5 s | 2.5 s | Paper quotes and WhatsApp photos from the market's own rounds (`tex/<market>/`, from `make_textures.py`), with «عروض في كل صيغة…» / "Quotes in every format…". |
| Opening (beat 0) | 5 s | 3 s | The opening animation as a framed plate beside the caption panel (above it in 9:16), so no copy covers the sheet. Caption: «…وكل سعر بتكتبه بإيدك في الإكسيل.» |
| Problem 3 | 3.5 s | 3 s | Three pain lines (lines wrap in 9:16). |
| Turn | 3.5 s | 3 s | Navy. The Converge mark builds from its official 64-unit geometry: grey bars, then the teal bar, then the arrowhead. Next the wordmark is revealed beside it, then «لمشتريات المطاعم» and «بيحلّها كلها.» with the teal bar. This is the brand's first appearance, so beat 1 drops its "ProcurePilot …" name card. |
| Beat 1 | as v1 | as v1 | Opens on the fix caption. The bridge says who the PO goes to: «…لأمر شراء تبعته للموردين…» (Saudi «ترسله للموردين»). |
| Saving page | inside beat 13, +2.5 s, 2.8 s | +2.5 s, 2.3 s (beat 13 is 1.5 s longer) | Full-page saving, counter from 0: ج.م / EGP / ر.س / SAR, or the € sign on the number. |
| Recap | 6 s | 5 s | «كل مشكلة وعندنا حلها» / "Every pain, solved": five struck pains, each with its fix. Ireland's fix reads "Per pack, delivery included" (ex-VAT quotes). |

Also:
- the 'Real run · demo data' pill is removed (the description carries the disclosure);
- the body music crossfades into the outro over 1.5 s (qsin) instead of cutting.

Bodies are 119.5 s for 16:9 and 65.97 s for 9:16 in every market. Each outro is the v2 one from
`../../renders/`, muxed unchanged.

The copy is in `make_data.py`. Egyptian Arabic and English were approved in chat. The Saudi lines are the
same copy in Saudi dialect («تدوّر على كل مورد لحاله», «اعتماد من الجوال», «كل مشكلة ولها حل»).

## Build

```bash
./rebuild.sh                 # all twelve cuts
./rebuild.sh eg-ar-h ie-en-v # just these (job = market-lang-fmt)
```

The build needs, locally:
- the plate links `plates-eg`, `plates-sa`, `plates-sa-en` and `plates-ie`, each pointing at a v1 fork's
  `plates/` (already masked; not in git);
- the fonts link to `../edit-v2.4/fonts`;
- Chrome, with Playwright on `NODE_PATH`.

`render.cjs <market> <fmt> <lang> <outDir> <f0> <f1>` renders frames. `audio.py` and `finish.py` take
`--only`. Refactoring the build to cover every market was checked against the approved review cut: Egyptian
Arabic 16:9 frames rendered before and after match pixel for pixel, within JPEG noise.
