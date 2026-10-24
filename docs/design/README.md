# Design system

The web app's design system and the proposals it was chosen from. Open the HTML files in a
browser; each has English / العربية and light / dark toggles at the top. Brand rules (logo,
colours, type) live in [`docs/brand/README.md`](../brand/README.md) and take precedence.

| File | What it is |
|---|---|
| [`design-system.html`](design-system.html) | **The adopted system (P-10, PPS-32).** Look from the frontend-design proposal (Ledger: Paper ground, navy and teal, a double rule under verified totals only, status chips that differ by shape), the three-layer token structure from the design-system proposal (primitive → semantic → component), and impeccable's source stamp on every extracted number. Includes the Angular Material 22 theme, with screenshots of real Material 22.2.4 components rendered with it. |
| [`proposals/frontend-design.html`](proposals/frontend-design.html) | Proposal from the `frontend-design` skill. The base of the adopted system. |
| [`proposals/design-system.html`](proposals/design-system.html) | Proposal from the `design-system` skill. Source of the token structure. |
| [`proposals/impeccable.html`](proposals/impeccable.html) | Proposal from the `impeccable` skill. Source of the provenance stamp. |
| [`proposals/ui-ux-pro-max.html`](proposals/ui-ux-pro-max.html) | Proposal from the `ui-ux-pro-max` skill. Not adopted. |

All four proposals cover the same 11-item checklist and were brought onto the brand palette and
fonts, so they compare like for like; the banner at the top of each names its skill.

## Using it in `apps/web`

The Material SCSS in `design-system.html` targets **Angular Material 22** and does not compile on
19 (the tonal button arrived in Material 20). It is adopted after the Angular 22 upgrade (P-9,
PPS-17). Override key names change between Material releases: recompile the theme after any
Material upgrade, since an unknown key fails the build.

Figures that must line up in columns (money, quantities, totals) use **Noto Kufi Arabic** with
`tabular-nums`; everything else is Readex Pro. Readex Pro has no tabular figures — see the
exception in the brand README.
