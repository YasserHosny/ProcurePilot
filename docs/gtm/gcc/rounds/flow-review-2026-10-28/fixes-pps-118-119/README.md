# Flow review 2026-10-28 — R13 and R14 fixes checked live (PPS-118, PPS-119)

The R13 and R14 fixes from [#348](https://github.com/YasserHosny/ProcurePilot/pull/348) were checked on hosted «مطاعم رواق» as
`pp-sa-owner` on 2026-10-30, after the backend and frontend deploys of `d773fd7e`. The check used a fresh request,
`f1203771` (flour × 4, sunflower oil × 6). It was created, submitted and approved as the owner through the API. Every
purchase-order step went through the UI. Email addresses are blurred.

## Why R13 happened

The hosted build was not older than the code: `submit()` has opened the new PO since #61. A frontend deploy landed while
the PO form was open:

- PO-000005 was created at 23:44:07Z on 2026-10-29, while Deploy Frontend for `c765a7fd` ran (23:41–23:44Z).
- The open tab still ran the old build. Its lazy chunk for the PO page (`orders/:id`) was gone from the new container.
- nginx's SPA fallback answered the missing `chunk-*.js` with `200 text/html`, so the dynamic import failed.
- `router.navigate()` rejected silently, after the success toast had shown and the button had been re-enabled.

Reproduced before the fix, in a tab that predated the 09:3x deploy, with request `3f054392`:

- One click logged «Order created successfully.» and then
  `Failed to fetch dynamically imported module: …/chunk-DGaPPpD8.js`. For 10 s the page stayed on `/orders/new`, with
  Create enabled.
- A second click got `409` (the API already refuses over-ordering), shown as «Request conflicts with the current state.»
- Only PO-000006 exists for that request.

## Seen live after the fix

| # | What | Seen | Screenshot |
|---|---|---|---|
| 1 | Approved request, nothing ordered | «Create purchase order», no purchase-orders row | [01](01-request-nothing-ordered-en.jpg) |
| 2 | Partial PO | Form filled with flour × 2 of 4 and oil × 3 of 6, «Still to order» chips | [02](02-po-form-partial-en.jpg) |
| 3 | Double-click on **Create Purchase Order** | One `POST /orders`, then the PO-000007 page opened (Draft, SAR 608) | [03](03-double-click-one-po-000007-en.jpg) |
| 4 | Request, partly ordered | «Purchase orders PO-000007» and the button still offered | [04](04-request-partly-ordered-en.jpg) |
| 5 | Order the rest | One `POST /orders`, then the PO-000008 page opened | — |
| 6 | Request, fully ordered | No button; «Purchase orders PO-000007 PO-000008»; "Everything on this request has been ordered." | [05](05-request-fully-ordered-en.jpg) |
| 7 | PO form opened for the fully ordered request (the list's cart icon goes here) | "Everything on this request has already been ordered." with both PO links, no lines, Create disabled | [06](06-po-form-nothing-left-en.jpg) |
| 8 | Request 34049121 from the review (R14) | No button; «Purchase orders PO-000005»; "Everything on this request has been ordered." | [07](07-request-34049121-po-000005-en.jpg) |
| 9 | Arabic | «أوامر الشراء PO-000007 PO-000008», «تم طلب كل ما في هذا الطلب.», and the PO-form notice read right to left | [08](08-request-fully-ordered-ar.jpg), [09](09-po-form-nothing-left-ar.jpg) |

Notes:

- The page reload after a deploy (the chunk-load recovery) was not triggered live, because that needs a deploy while a
  tab is open. Karma tests cover it:
  - a chunk error reloads the target URL once;
  - other errors don't reload;
  - a repeat within 30 s doesn't reload;
  - after the follow-up fix, there is no reload when `sessionStorage` is blocked (a review finding on #348).
- The «Product flows review» session cross-checked Order Tracking: PO-000007 and PO-000008 are each listed once, and
  no other POs were created.
- Test data left on «مطاعم رواق»:
  - request `3f054392` with PO-000006 (the pre-fix repro);
  - request `f1203771` with PO-000007 and PO-000008.

  All three POs are drafts.
- The language was switched to Arabic for screenshots 08 and 09, then back to English.
- Still open, not part of this fix: the Purchase Requests list keeps its cart icon on fully ordered requests. It opens
  the form in row 7, which offers nothing to order.
