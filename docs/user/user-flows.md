# ProcurePilot User Flows

> Breadcrumb-style navigation paths for every user-facing page.
> Last updated: 6 Sep 2026.

---

## Access and Workspace Setup

- `/auth/sign-in` -> sign in -> `/home`
- `/auth/sign-in` -> **Forgot password?** -> `/auth/password-reset` -> email reset link
- `/auth/sign-in` -> **Create workspace** -> `/onboarding/signup` -> invitation token + workspace details -> `/onboarding/plan` -> `/home`
- `/onboarding/accept-invitation?token=...` -> accept member invitation -> `/home`
- Guarded page while signed out -> `/auth/sign-in?returnUrl=...` -> original page after sign-in

## Catalogue and Supplier Setup

- `/home` -> **Products** -> `/products` -> **New Product** -> `/products/new` -> save -> `/products/:id`
- `/home` -> **Products** -> `/products` -> row edit -> `/products/:id`
- `/home` -> **Products** -> `/products` -> **Import Products** -> `/import?kind=products` -> upload CSV -> preview -> commit -> `/products`
- `/home` -> **Suppliers** -> `/suppliers` -> **New Supplier** -> `/suppliers/new` -> save -> `/suppliers/:id`
- `/home` -> **Suppliers** -> `/suppliers` -> row edit -> `/suppliers/:id`
- `/home` -> **Suppliers** -> `/suppliers` -> **Import Suppliers** -> `/import?kind=suppliers` -> upload CSV -> preview -> commit -> `/suppliers`
- `/home` -> **Import Catalogue** -> `/import` -> choose Products or Suppliers -> upload CSV -> preview -> commit

## Quotation to Trusted Offer

- `/home` -> **Quotation Inbox** -> `/quotations` -> **Upload Quotation** -> `/quotations/upload` -> select file or sample -> extraction complete -> `/quotations/:id/review`
- `/quotations` -> search/filter/sort -> **Review & Authorize** -> `/quotations/:id/review`
- `/quotations/:id/review` -> inspect source evidence + fields + lines -> save corrections -> confirm and authorize
- `/quotations/:id/review` -> retry extraction, export CSV, archive, or create re-quote
- `/quotations/:id` redirects to `/quotations/:id/review`

## Matching, Comparison, and Savings

- `/home` -> **Match Resolution** -> `/matching` -> search/filter/sort -> **Resolve Match** -> `/matching/:id` -> choose outcome -> confirm
- `/matching/tasks/:id` redirects to `/matching/:id`
- `/home` -> **Smart Compare** -> `/offers/compare` -> select product + quantity -> compare landed costs -> **Record Purchase** -> `/savings/outcome-capture`
- `/offers/compare/:id` opens Smart Compare with a product preselected; `/compare` and `/compare/:id` are aliases
- `/home` -> **Smart Compare** -> `/offers/product-intelligence` -> select product/supplier/time window -> inspect historical prices
- `/offers/product-intelligence/:id` opens Product Price Intelligence with a product preselected
- `/home` -> **Basket Split** -> `/offers/basket-split` -> choose two suppliers + basket lines -> optimise -> `/offers/basket-split/:id`
- `/home` -> **Alerts Inbox** -> `/alerts` -> open alert action -> Smart Compare, supplier detail, or Product Price Intelligence
- `/home` -> **Savings Ledger** -> `/savings` -> **Record Purchase Outcome** -> `/savings/outcome-capture` -> compute saving -> `/savings/:id/evidence`
- `/savings` -> **View Evidence** -> `/savings/:id/evidence`; `/savings/:id` is an alias
- `/savings` -> **Export Savings** -> `/savings/export` -> generate export -> `/savings/export/:id`

## Requests, Approvals, and Administration

- `/home` -> **Purchase Requests** -> `/requests` -> **Save Draft** -> `/requests/new` -> save draft -> `/requests/:id`
- `/requests/:id` -> submit, withdraw, or return to the queue depending on status
- `/home` -> **Approval Queue** -> `/approvals` -> review routed requests when approval routing is available
- `/home` -> **Team Management** -> `/team` -> invite member -> pending invitation -> accept invitation flow
- `/home` -> **Settings** -> `/settings` -> manage branches, cost centres, and budgets
- Unknown routes redirect to `/`, then to `/home` for signed-in users.

---

For screen-by-screen details and screenshots, see [ProcurePilot User Documentation](user-documentation.md).
