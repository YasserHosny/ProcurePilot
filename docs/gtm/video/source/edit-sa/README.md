# ProcurePilot Saudi demo — «مطاعم رواق» edit (PPS-39)

The Saudi demo video, built from the v2.4 engine ([`../edit-v2.4/`](../edit-v2.4/), forked 2026-10-25 after the PPS-63
re-shoot). The structure, motion system, beat lengths and honesty rules are unchanged. These are the parts that differ:

| Part | Egypt (v2.4) | Saudi |
|---|---|---|
| Captions | [`../../cuts/v2.4-ledger/script.md`](../../cuts/v2.4-ledger/script.md) | [`../../../gcc/script-saudi.md`](../../../gcc/script-saudi.md) (owner-approved), parsed verbatim; its **[sa]** figures are filled per language in `make_data.py` (`FILL`) |
| Footage | rounds 6 (AR) / 7 (EN) on «مطاعم سند» | rounds A (AR) / E (EN) on «مطاعم رواق» ([record](../../../gcc/rounds/README.md)) |
| Source times | one table, English derived from Arabic | one table per language (`make_data.py`): the two rounds were recorded separately |
| Figures on screen | ج.م / EGP | ر.س / SAR, each from its own round: AR quote ٤٬٩١٠, compare gap ٤٠, saving ١٩٠, ledger ١٩٠; EN quote 4,790, gap 40, saving 120, ledger 310 |
| Opening | `opening-anim` (النور, الأمانة, الحاج سيد) | [`../opening/OpeningChaos-sa.html`](../opening/OpeningChaos-sa.html): الوفرة, الذهبي, القصيم, riyal prices, VAT mixed in and out; renders in [`../../renders/sa/`](../../renders/sa/) |
| Outro / end card | Egyptian contact | the same Egyptian outro for now (owner, 2026-10-25); a Saudi contact replaces it later |
| Privacy templates | Egyptian owner address | the Saudi owner address (`+pp-sa-owner`) wraps onto two lines: one template per line, plus one scroll corridor (24.6–26.4 s) on the review clip |
| Output | `../../cuts/v2.4*-ledger/` | [`../../cuts/gcc-sa-v1/`](../../cuts/gcc-sa-v1/), `procurepilot-demo-sa-{ar,en}-{16x9,9x16-60s}.mp4` |

Crops changed from v2.4:
- Beat 13: the outcome form hugs the reading edge (nav hidden), so its crop follows that edge in both languages.
- Beat 3: the 9:16 list crop applies to the final still, not to a fixed source time.

## Rebuild

Raw clips (not in git; several show the owner's email until masked) go in `raw/{ar,en}/` from
`~/Videos/pp-recording/sa/{ar,en}/`. The Saudi openings go in `raw/openings/` as `opening-anim-16x9.mp4` and
`opening-anim-9x16.mp4`. Then:

```bash
cd docs/gtm/video/source/edit-sa
bash rebuild.sh privacy
bash rebuild.sh prepare
bash rebuild.sh render
```

Privacy result (2026-10-25):
- The email was found in the review clips (546 / 547 frames) and the phone approval clips (296 / 299 frames).
- After masking, all 16 clips are at 0 matches, and the 4 result inserts are at 0.
- The control still detects the email in the unmasked Arabic review clip.

`check_detector.py` still checks the Egyptian template positions and is not part of this rebuild.

## Known limits

- English beat 3 ends on «RFQ sent. Suppliers emailed: 3» while the RFQ list is still loading. Re-recording it
  would email the suppliers again.
- The phone approval list row (beat 11, 1 s) looks near-empty because its requester email line is masked.
