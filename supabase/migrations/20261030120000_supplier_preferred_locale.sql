-- 20261030120000_supplier_preferred_locale.sql — RFQ emails follow the supplier's language (PPS-134).
--
-- RFQ emails went out in coalesce(sender's membership.preferred_locale, tenant.default_locale),
-- so one buyer's English sign-in made every supplier email English (flow review R6, 2026-10-28).
-- Supplier-facing email now uses coalesce(supplier.preferred_locale, tenant.default_locale) and
-- never the sender's interface language.
--
--   * supplier.preferred_locale: 'en' or 'ar', the same values as tenant.default_locale and
--     membership.preferred_locale. Nullable: null means "the workspace default", which is what
--     every existing supplier gets.
--
-- No RLS or grant change: supplier keeps its tenant policies, and `authenticated` already has
-- table-level insert/update on supplier (contact_email was added the same way, 20260924203651).

alter table supplier
  add column preferred_locale text
  constraint supplier_preferred_locale_check
    check (preferred_locale is null or preferred_locale in ('en', 'ar'));

comment on column supplier.preferred_locale is
  'Language of emails sent to this supplier (RFQs): en or ar. Null follows
   tenant.default_locale. Never the sending member''s interface language. 20261030120000.';
