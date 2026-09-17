-- 20260917000006_suppliers_email_domains.sql — task T006, chunk R3.0 (013-automated-ingestion)
--
-- Adds email_domains text[] to supplier table with GIN index for fast email sender domain matching.
-- Used by the cascading supplier matcher service (T009) to attribute incoming emails to suppliers.

alter table supplier
  add column if not exists email_domains text[] not null default '{}';

-- GIN over tenant_id + email_domains together needs the btree_gin extension (uuid has no
-- default GIN operator class on its own — confirmed by actually applying this migration, which
-- fails with "data type uuid has no default operator class for access method gin" without it).
-- supplier_tenant_idx already covers tenant_id; Postgres bitmap-ANDs it with a plain GIN index
-- on email_domains for a query like `where tenant_id = $1 and email_domains && $2`, so there is
-- no need to pull the extension in just for this.
create index if not exists supplier_email_domains_gin_idx
  on supplier using gin (email_domains);

comment on column supplier.email_domains is
  'List of email domains (e.g. {almarai.com, almarai.sa}) associated with this supplier for
   automatic email ingestion matching (R3.0).';
