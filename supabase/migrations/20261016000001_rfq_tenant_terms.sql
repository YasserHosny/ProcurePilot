-- Persist the buyer's terms entered on the RFQ create form.
--
-- Until now `tenant_terms` was accepted by POST /rfqs and silently dropped: there was no column,
-- so the outbound supplier email could never include it. Nullable, so existing RFQs are
-- unaffected. `rfq` already has ENABLE + FORCE row-level security with USING and WITH CHECK
-- policies on tenant_id; a new column on an existing row inherits them, no policy change needed.
alter table rfq
  add column if not exists tenant_terms text
    check (tenant_terms is null or char_length(tenant_terms) <= 4000);
