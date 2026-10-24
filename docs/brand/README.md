# ProcurePilot brand

**Logo: Converge** (adopted 2026-10-14). Three bars stand for supplier quotes compared side by
side; the teal one, the best quote, keeps going as an arrow, the decision moving forward. It
replaces the paper-plane mark, which read as Telegram's logo next to WhatsApp screenshots and
only said "send".

Exploration canvas (all directions, identity system, in-context mockups):
<https://claude.ai/artifact/CYVrF8484uFkpiJTqcGPdS>

## Files — `logo/`

| File | Use |
|---|---|
| `procurepilot-horizontal.svg` / `-1436px.png` | Default logo on light backgrounds |
| `procurepilot-horizontal-dark.svg` / `-1436px.png` | On navy or dark backgrounds |
| `procurepilot-arabic-horizontal.svg` / `-1436px.png` | Arabic logo «بروكيور بايلوت» (mark at the reading start, right) |
| `procurepilot-arabic-horizontal-dark.svg` / `-1436px.png` | Arabic logo on dark |
| `procurepilot-stacked.svg` / `-908px.png` | Square spaces (social avatars, video end card) |
| `procurepilot-mark.svg` / `-1024/512/192/32px.png` | Mark alone, full colour |
| `procurepilot-mark-reversed.svg` | Mark on navy |
| `procurepilot-mark-mono-navy.svg`, `-mono-white.svg` | One-colour printing, embossing, watermarks |
| `procurepilot-app-icon.svg` / `-1024/512/192/32px.png` | **Store and OS app icons** (iOS, Android adaptive, PWA): full-bleed opaque square, no transparency — the OS applies its own corner mask |
| `procurepilot-app-icon-rounded.svg` / `-1024/512/192/32px.png` | Rounded icon for avatars, favicons, slides and marketing (transparent corners) |

All SVG lettering is converted to outlines, so the files need no font installed.

## Colours

| Name | Hex | Use |
|---|---|---|
| Navy | `#0B2545` | Primary text, compared bars, dark backgrounds |
| Teal | `#12A594` | The winning bar and arrow, "Pilot", accents — large text and graphics only |
| Teal (text) | `#0C7A6E` | Teal for small text on white (meets 4.5:1) |
| Teal on dark | `#19B8A4` | Teal on navy |
| Mist | `#C9D6E3` | Compared bars on dark backgrounds |
| Paper | `#F4F6F9` | Page backgrounds |

## Type

**Readex Pro** (one family designed for Arabic and Latin), SIL Open Font License, from
[Google Fonts](https://fonts.google.com/specimen/Readex+Pro). Wordmark: weight 600, tracking −2%.
Body text: 400–500.

**Figures in tables: Noto Kufi Arabic** (exception, adopted 2026-10-24). Readex Pro has no
tabular figures: even with `font-variant-numeric: tabular-nums`, "1111" and "8888" differ in width
(80 px vs 93 px at 40 px), for Latin and Arabic-Indic digits alike, so money columns do not line up.
[Noto Kufi Arabic](https://fonts.google.com/noto/specimen/Noto+Kufi+Arabic) (SIL Open Font License)
has tabular 0–9 and ٠–٩ of its own and is kufi like Readex Pro's Arabic. Use it, with
`tabular-nums`, only where digits must align vertically: numeric and money table columns, totals
rows, money inputs. Headline figures, prose, chips and headings stay Readex Pro. Monospace fonts were
rejected: they read as code and carry no Arabic-Indic digits.

## Rules

- Keep the mark unmirrored in Arabic layouts: the arrow means "forward", not reading direction.
- Clear space around any logo: at least the height of one bar of the mark (1/8 of the mark).
- Below 24 px, use the mark or app icon alone, never the full logo.
- Do not recolour the bars, outline the mark, or add effects.

## Rebuilding the outlined SVGs

`source/build_lockups.py` regenerates the five logo SVGs from the mark geometry and Readex Pro.
It needs `fonttools` and `uharfbuzz` and the variable font file `ReadexPro.ttf` (the font file is
not committed):

```bash
pip install fonttools uharfbuzz
curl -L -o ReadexPro.ttf "https://github.com/google/fonts/raw/main/ofl/readexpro/ReadexPro%5BHEXP%2Cwght%5D.ttf"
mkdir -p final && python docs/brand/source/build_lockups.py   # writes into ./final/
```

## Archive

The previous paper-plane identity (flat logo, 3D renders, turntable, `.glb` model) is kept
unchanged in `archive/paper-plane/`.
