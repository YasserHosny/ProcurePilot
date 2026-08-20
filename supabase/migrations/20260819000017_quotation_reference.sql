-- 20260819000017_quotation_reference.sql — task T007
--
-- Reference enums for the quotation inbox and extraction pipeline. No tenant data — just the
-- vocabulary the next two migrations build on.

do $$ begin
  create type document_source_channel as enum ('upload');
exception when duplicate_object then null; end $$;

do $$ begin
  create type document_status as enum ('uploaded', 'failed_to_read');
exception when duplicate_object then null; end $$;

do $$ begin
  create type quotation_status as enum (
    'pending', 'extracting', 'extracted', 'in_review', 'reviewed', 'refused'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type arithmetic_status as enum ('not_applicable', 'reconciled', 'mismatch');
exception when duplicate_object then null; end $$;

do $$ begin
  create type extraction_method as enum ('structured_parse', 'bedrock', 'azure_di');
exception when duplicate_object then null; end $$;

do $$ begin
  create type field_extraction_entity_type as enum ('quotation', 'quotation_line');
exception when duplicate_object then null; end $$;

do $$ begin
  create type extraction_job_status as enum ('queued', 'running', 'succeeded', 'failed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type review_task_status as enum ('open', 'in_progress', 'resolved');
exception when duplicate_object then null; end $$;

do $$ begin
  create type review_task_priority as enum ('low', 'normal', 'high');
exception when duplicate_object then null; end $$;

do $$ begin
  create type review_task_reason as enum (
    'low_confidence', 'arithmetic_mismatch', 'read_failure', 'review_required'
  );
exception when duplicate_object then null; end $$;

comment on type document_source_channel is
  'Upload only for this chunk. Email and API ingestion are reserved for a later chunk — extending
   an enum is a normal migration, so nothing is pre-added on speculation.';
