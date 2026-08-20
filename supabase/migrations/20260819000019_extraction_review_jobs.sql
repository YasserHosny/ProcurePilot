-- 20260819000019_extraction_review_jobs.sql — task T009
--
-- The constitutional evidence record (field_extraction), the async job resource behind
-- /jobs/{job_id} (extraction_job), and the standalone review queue (review_task).

-- ---------------------------------------------------------------------------
-- field_extraction — one row per extracted FIELD, never per line or per quotation.
--
-- Constitution Principle I: confidence, source location, extraction method and model version are
-- first-class data for every value the product derives, not a metadata blob and not an aggregate.
-- A human correction is a distinct fact recorded alongside the original — review does not
-- overwrite the evidence it is reviewing (FR-013).
-- ---------------------------------------------------------------------------
create table if not exists field_extraction (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenant(id) on delete cascade,
  quotation_id      uuid not null references quotation(id) on delete cascade,

  -- Polymorphic target: quotation.id or quotation_line.id per entity_type. Cannot carry a single
  -- FK for that reason; application code must verify the target belongs to this tenant and this
  -- quotation in the same transaction that writes this row.
  entity_type       field_extraction_entity_type not null,
  entity_id         uuid not null,
  field_name        text not null,

  extracted_value   jsonb not null,
  confidence        numeric(5, 4) not null check (confidence between 0 and 1),
  source_page       integer check (source_page is null or source_page > 0),
  source_region     jsonb,
  extraction_method extraction_method not null,
  model_version     text not null,

  corrected_value   jsonb,
  corrected_by      uuid references membership(id),
  corrected_at      timestamptz,

  created_at        timestamptz not null default now(),

  constraint field_extraction_correction_fields_together
    check ((corrected_by is null) = (corrected_at is null))
);

create unique index if not exists field_extraction_unique_field
  on field_extraction (tenant_id, entity_type, entity_id, field_name);
create index if not exists field_extraction_tenant_idx on field_extraction (tenant_id);
create index if not exists field_extraction_quotation_idx on field_extraction (quotation_id);

comment on table field_extraction is
  'The evidence record Constitution Principle I requires: per-field confidence and provenance,
   never a single aggregate for a line or a quotation. See specs/003-quotation-inbox-extraction/
   research.md R5.';

-- ---------------------------------------------------------------------------
-- extraction_job — the persisted, user-visible job resource. Redis (added at implementation
-- time) only delivers work to the worker; this row is the durable source of truth /jobs/{job_id}
-- polls against.
-- ---------------------------------------------------------------------------
create table if not exists extraction_job (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenant(id) on delete cascade,
  quotation_id        uuid not null references quotation(id) on delete cascade,

  status              extraction_job_status not null default 'queued',
  attempted_provider  extraction_method,
  error               jsonb,

  created_at          timestamptz not null default now(),
  started_at          timestamptz,
  completed_at        timestamptz,

  constraint extraction_job_completed_at_only_terminal
    check ((status in ('succeeded', 'failed')) = (completed_at is not null))
);

-- One active extraction per quotation at a time.
create unique index if not exists extraction_job_one_active_per_quotation
  on extraction_job (tenant_id, quotation_id)
  where status in ('queued', 'running');
create index if not exists extraction_job_tenant_idx on extraction_job (tenant_id);

-- ---------------------------------------------------------------------------
-- review_task — the standalone review queue (FR-019, Constitution Principle III: "human review
-- is an architectural concept, not a screen"). Not a computed view over quotations.
-- ---------------------------------------------------------------------------
create table if not exists review_task (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenant(id) on delete cascade,
  quotation_id  uuid not null references quotation(id) on delete cascade,

  status        review_task_status not null default 'open',
  priority      review_task_priority not null default 'normal',
  reason        review_task_reason not null,

  created_at    timestamptz not null default now(),
  resolved_at   timestamptz,

  constraint review_task_resolved_at_only_when_resolved
    check ((status = 'resolved') = (resolved_at is not null))
);

-- One outstanding task per quotation at a time.
create unique index if not exists review_task_one_open_per_quotation
  on review_task (tenant_id, quotation_id)
  where status in ('open', 'in_progress');
create index if not exists review_task_tenant_idx on review_task (tenant_id, status, priority);
