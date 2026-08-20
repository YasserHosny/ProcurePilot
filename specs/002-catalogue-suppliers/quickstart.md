# Quickstart: Catalogue and Suppliers

**Feature**: 002-catalogue-suppliers | **Date**: 2026-08-20

Assumes the chunk 4.1 environment is already working. If not, start with
[`../001-platform-foundation/quickstart.md`](../001-platform-foundation/quickstart.md) — the stack,
keys and seed data are identical and are not repeated here.

---

## 1. Bring the stack up

```bash
supabase start          # applies supabase/migrations, including this chunk's
pnpm db:seed            # reference data + a platform invitation token
```

Then the API and the web app in separate terminals, as in the chunk 4.1 quickstart.

## 2. Sign in as a role that may write

Catalogue and supplier mutations are **owner or buyer only** (FR-032). Signing in as a branch
manager, approver or viewer gives you a read-only catalogue — that is correct behaviour, not a
broken permission. If a create button is missing, check which role you are.

## 3. Create a product and watch normalisation happen

In the web app: Catalogue → New product. Enter a name, pick a base unit, and set a pack of
**6 × 5 litres**. The normalised quantity should read **30 litres** before you save.

That number is computed by the database, not the form. If the form's preview and the saved value
ever disagree, the form is wrong — `base_quantity` is a generated column and cannot be written.

## 4. Create a supplier with commercial terms

Suppliers → New supplier. Every monetary field asks for a currency alongside the amount, and will
not accept an amount without one. That is deliberate: there is no default currency, and inferring
one turns a £500 minimum order into a plausible, wrong number in another currency.

## 5. Import a catalogue

Catalogue → Import. A sample file lives at `apps/api/tests/fixtures/products_valid.csv`; a
deliberately broken one at `products_invalid.csv`.

Upload the broken one first. You should see:

- **nothing saved** — the catalogue is unchanged
- an error report naming each bad row **by its line number in your file**, with a specific reason
- missing or unrecognised columns reported separately from row errors

Then upload the valid file, review the preview, and confirm. Now everything saves, or nothing does.

## 6. Verify the guarantees

```bash
# Cross-workspace isolation, extended to the new tables
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres pnpm test:isolation

# Normalisation is reproducible and money always has a currency
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres pnpm test:api
```

`TEST_DATABASE_URL` is required, not optional. Without it the database-backed tests **skip**, which
in a summary line looks exactly like passing.

---

## Common problems

**A create button is missing.** You are signed in as branch manager, approver or viewer. Those roles
read the catalogue; they do not write it.

**An import reports "cannot determine decimal separator".** A number like `1,234` means 1234 in one
convention and 1.234 in another. The import refuses rather than guessing, because guessing wrong is
a thousand-fold error in a price. Write it unambiguously — `1234` or `1234.00`.

**A supplier will not delete.** Suppliers referenced by other records are archived, not deleted. A
savings claim in a later chunk has to stay explicable, which means the records it points at must
still resolve.

**The normalised quantity looks slightly off.** It should not — the column is `numeric`, not
floating point, precisely so `3 × 0.33` is exactly `0.99`. If you see a floating-point artefact,
that is a bug worth reporting rather than a rounding quirk to live with.

---

## What is deliberately absent

- Prices against products — offers arrive in chunk 4.4
- Document upload and extraction — chunk 4.3
- Automatic matching and confidence scores — chunk 4.4
- Any currency conversion, ever
