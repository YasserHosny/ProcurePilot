# Flow review 2026-10-28 — R12 checked live (PPS-125)

R12: the Approval Queue's Requester column showed the owner's Gmail plus-address. The long address also wrapped the
Branch and Cost Centre cells. Fixed in [#359](https://github.com/YasserHosny/ProcurePilot/pull/359) and checked
on hosted «مطاعم رواق» as `pp-sa-owner` on 2026-10-31, after the deploy of `341265fc` and migration
`20261030000000_membership_display_name`. Arabic UI (the account's language). The owner's email is blurred in
screenshot 02.

**Cause.** Members had no name. `membership` had no name column, and the API never filled `requester_name` or
`approval_step.assigned_name`, so the queue fell back to the email.

**Fix.** `membership.display_name` (and `member_invitation.display_name`) are set at sign-up and from the
invitation, and can be edited in Team Management. Requests carry `requester_name` and `assigned_name`. A member
without a name shows the email's local part on one line, with the full address in a tooltip.

| # | Step | Seen live | Screenshot |
|---|---|---|---|
| 1 | Team Management before | Name column reads «بلا اسم» (no name) for the owner | — |
| 2 | Edit name → «المالك» → Save | The row shows «المالك». Joined date unchanged (٢٠٢٦/١٠/٢٥; hosted `created_at` 2026-10-24 22:10 UTC = 25 Oct in Riyadh) | [02](02-team-name-column-ar.jpg) |
| 3 | A one-line request (basmati rice ×1, فرع العليا) saved and submitted | Approval Queue: Requester column reads «المالك», with no email and no tooltip | [01](01-approval-queue-requester-name-ar.jpg) |
| 4 | The test request `daa275a0` withdrawn | Request is `withdrawn` | — |

Notes:

- `pp-sa-buyer` (named in the Saudi demo plan) has no membership or invitation on hosted, so there was no second
  member to name. The owner chose «المالك» for `pp-sa-owner`.
- The test request was withdrawn after the screenshot, but the Approval Queue still lists it. That is a separate
  bug from before this change: withdrawing a submitted request sets its status to `withdrawn` and leaves its
  approval step `pending`, and the queue lists pending steps. It is not part of R12.
- The request page's approval line still shows the approver's email («معيّن إلى»), not `assigned_name`. The API
  now returns the name, and the web does not use it there yet. Not part of R12.
