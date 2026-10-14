# Quickstart: verify 022

1. `docker compose up`; sign in as owner of a tenant; Settings → Home currency → EGP (audit row appears).
2. Open PO create, guardrails, quotation review (currency-less quote), supplier min-order/delivery-fee: EGP preselected; switch one PO to USD and save → stays USD.
3. Submit the 5 Egyptian sample quotes (incl. Arabic-Indic digits, one unmarked) → EGP; the unmarked one shows the currency flagged for review.
4. `pnpm --filter web exec playwright test <spec>` for the EGP-default flow; `pytest` for worker `currency.py`; `flutter test` for `money_format`.
5. Mobile approval queue shows `EGP 12,500.00`; Arabic locale renders RTL; 12.5 KWD shows 3 decimals.
