# Brand editorial edit (v2.3)

Source for [`../../cuts/v2.3-brand/`](../../cuts/v2.3-brand/): the v2.2-editorial timeline (same story,
copy and timing) re-art-directed to the binding motion direction in
[`../../motion-style.md`](../../motion-style.md). Forked from [`../edit-editorial/`](../edit-editorial/),
which stays as it was so v2.2-editorial can still be rebuilt.

## What changed from v2.2-editorial

| Area | v2.2-editorial | v2.3 brand editorial |
|---|---|---|
| Palette | invented: warm off-white, near-black, orange-red `#DD4F28` | official: Paper `#F4F6F9`, Navy `#0B2545`, Mist `#C9D6E3`, Teal `#12A594` (`#19B8A4` on navy, `#0C7A6E` for small text) |
| Colour meaning | orange on any emphasis | **one teal hit per scene, always the better choice or the positive outcome**: "to all suppliers", the winning price's bar, "the manager decides", the approval, the saving, the verified ledger. Problems and neutral facts are navy; planes are Mist or Navy |
| Footage plates | grayscale with a warm multiply | navy duotone (`screen` blend of navy over grayscale), white cards, navy-tinted shadows |
| Photos and paper quotes | warm grayscale halftone | navy duotone halftone (`make_textures.py`) |
| Transitions | paper and colour planes | plus `PASS()`, the Converge mark as a wipe: navy / teal + arrowhead / navy bars cross the frame **left to right** (the arrow's "forward", unmirrored per the brand rules), at the cuts into S1, S5 and S7 |
| Logo | mark redrawn and recoloured (orange/ink), wordmark typed | the mark builds from its official geometry and colours, then the **official lockup SVG** is revealed over it (`procurepilot-horizontal.svg` 16:9, `procurepilot-stacked.svg` 9:16); the end card uses `procurepilot-horizontal-dark.svg` on a navy panel |
| Disclosure | grey text | Mist-backed pill, readable over navy and teal |
| Grain | soft-light 55 % | 35 %, cleaner for the brand |

## Rebuild

Same steps as [`../edit-editorial/README.md`](../edit-editorial/README.md), in this folder:

```bash
cd docs/gtm/video/source/edit-v2.3-brand
python3 extract.py && python3 make_data.py && python3 make_textures.py && ./fetch_fonts.sh
for i in 0 1 2 3; do node render.cjs h frames-h $((i*893)) $(( (i+1)*893 > 3569 ? 3569 : (i+1)*893 )) & done; wait
for i in 0 1 2 3; do node render.cjs v frames-v $((i*401)) $(( (i+1)*401 > 1602 ? 1602 : (i+1)*401 )) & done; wait
```

Audio and mux are unchanged from v2.2-editorial: the v2.1 cut's audio with the removed passage taken out
(16:9 `[0,109.2]+[125.4,end]` through `alimiter=limit=0.7:level=false`; 9:16 `[0,44.9]+[46.512,end]`), then
`libx264 -crf 21 -tune grain`, AAC 256 kb/s. Measured: 16:9 1:59.0, −13.9 LUFS, peak −2.0 dBFS;
9:16 0:53.4, −14.1 LUFS, peak −2.9 dBFS.

The logo SVGs are read from `../../../../brand/logo/`, so render from inside the repo.

## Privacy

The footage plates are crops of the v2.1 Arabic cut, whose email masks are already burned in (see
[`../../cuts/README.md`](../../cuts/README.md)). The duotone maps white to white, so the opaque mask
boxes stay opaque; no unmasked source is used.

## Known gaps

- Arabic only. The English cut needs its own timeline from the English-UI round-5 footage (v2.2 English
  UI), with that round's figures. It will be built after the owner approves this look.
- Footage is one encode generation soft (inherited from v2.2-editorial).
