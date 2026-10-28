# Workflow D: content production

**Lead:** `campaign-operations` · **Upstream skills (pick per asset):** `copywriting`, `copy-editing`, `social`, `video`, `image`, `content-strategy` · **Review:** `campaign-review` · **Gates:** G-asset, G-claims

1. Read the approved brief, the campaign messaging matrix and the product `proof-points.md`.
2. Write a brief per asset: `templates/content-brief-template.md`, `social-post-template.md`, `video-brief-template.md` or `landing-page-template.md`.
3. Produce channel-specific versions (EN and AR as planned) in `assets/drafts/`. File names: `<channel>-<format>-<slug>-<lang>-v<N>.<ext>`.
4. Keep brand voice and identity; use only approved claims; label synthetic data.
5. One call to action per piece, with a UTM-tagged link.
6. Move to `assets/in-review/` and run `campaign-review` (checks QC-01 to QC-11 in `config/workflow-rules.yaml`).
7. Fix findings and record the review result in `approvals.md`.
8. On G-asset approval, move to `assets/approved/`. Approved is **not** published (see `publishing.md`).

**Creative limits.** Claude can write scripts, storyboards, copy and design specs, and can lay out simple HTML/SVG
graphics with the supplied brand files. Rendering a finished video or generating images needs a tool that is
actually connected. Always say which one was delivered: a brief, a script, a layout, or a rendered file.
