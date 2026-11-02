# Publishing

**Lead:** `campaign-operations` · **Gate:** G-publish (explicit, per asset, per channel, per date)

Default: Claude prepares a **publish-ready package** and a person publishes it.

1. The asset is in `assets/approved/` with a G-asset row in `approvals.md`.
2. Prepare the package: final copy (EN/AR), media files, alt text, captions, UTM link, hashtags, target date and time, channel account.
3. Ask for G-publish in chat, naming the asset, channel and time. Without a clear "yes" for that action, stop at the package.
4. If authorised **and** a publishing tool is actually connected, publish exactly the approved package. Otherwise the owner publishes manually.
5. Log it in the publishing log in `distribution-plan.md` (date, channel, URL, who published).
6. Changes after publishing go back through review.

Live website changes follow `E-website-and-seo.md`. Accounts (for example Facebook, Instagram) are created by the owner.
