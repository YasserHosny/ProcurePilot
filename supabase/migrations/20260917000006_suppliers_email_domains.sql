-- 20260917000006_suppliers_email_domains.sql — task T006, chunk R3.0 (013-automated-ingestion)
--
-- Adds email_domains text[] to supplier table with GIN index for fast email sender domain matching.
-- Used by the cascading supplier matcher service (T009) to attribute incoming emails to suppliers.

alter table supplier
  add column if not exists email_domains text[] not null default '{}';

create index if not exists supplier_email_domains_gin_idx
  on supplier using gin (tenant_id, email_domains);

comment on column supplier.email_domains is
  'List of email domains (e.g. {almarai.com, almarai.sa}) associated with this supplier for
   automatic email ingestion matching (R3.0).';
