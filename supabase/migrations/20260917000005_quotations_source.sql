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
  add column if not exists ingestion_email_id uuid;

alter table quotation
  add constraint quotation_source_valid check (source in ('upload', 'email', 'capture'));

-- Composite pin into ingestion_email_log's own (tenant_id, id) key — unlike quotation itself
-- (which has no such key yet, so every OTHER FK into it stays bare — see
-- ingestion_email_log_supplier_fkey's comment), ingestion_email_log was created with one in the
-- same wave, so there is no excuse for a bare reference here.
--
-- Found by PR review: plain `on delete set null` on this multi-column FK would null BOTH
-- referencing columns on delete, including tenant_id — which is `not null` on quotation, so
-- deleting the referenced ingestion_email_log row would fail outright instead of just clearing
-- ingestion_email_id. PG17's column-targeted form fixes this (see
-- ingestion_email_log_supplier_fkey's own comment for the same fix, verified empirically there).
alter table quotation
  add constraint quotation_ingestion_email_fkey
    foreign key (tenant_id, ingestion_email_id) references ingestion_email_log (tenant_id, id)
    on delete set null (ingestion_email_id);

create index if not exists quotation_tenant_source_idx
  on quotation (tenant_id, source);

create index if not exists quotation_ingestion_email_idx
  on quotation (tenant_id, ingestion_email_id)
  where ingestion_email_id is not null;

comment on column quotation.source is
  'Channel through which quotation arrived: manual upload, forwarded email, or mobile capture (R3.0).';
comment on column quotation.ingestion_email_id is
  'Reference to inbound email record in ingestion_email_log when source = email.';
