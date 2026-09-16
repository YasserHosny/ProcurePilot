-- 20260917000005_quotations_source.sql — task T005, chunk R3.0 (013-automated-ingestion)
--
-- Widens document_source_channel enum with 'email' and 'capture' channels, and adds
-- source tracking and email linkage to the quotation table.
--
-- IMPORTANT: ALTER TYPE ... ADD VALUE must run outside a transaction or be isolated
-- before values can be referenced by check constraints. Here, quotation.source uses
-- text with check constraint, and document_source_channel enum is widened for future use.

alter type document_source_channel add value if not exists 'email';
alter type document_source_channel add value if not exists 'capture';

alter table quotation
  add column if not exists source text not null default 'upload',
  add column if not exists ingestion_email_id uuid references ingestion_email_log(id) on delete set null;

alter table quotation
  add constraint quotation_source_valid check (source in ('upload', 'email', 'capture'));

create index if not exists quotation_tenant_source_idx
  on quotation (tenant_id, source);

create index if not exists quotation_ingestion_email_idx
  on quotation (tenant_id, ingestion_email_id)
  where ingestion_email_id is not null;

comment on column quotation.source is
  'Channel through which quotation arrived: manual upload, forwarded email, or mobile capture (R3.0).';
comment on column quotation.ingestion_email_id is
  'Reference to inbound email record in ingestion_email_log when source = email.';
