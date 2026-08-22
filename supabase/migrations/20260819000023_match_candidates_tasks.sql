-- 20260819000023_match_candidates_tasks.sql — task T006
--
-- match_candidate — the evidence record per proposed product per line (Constitution Principle I:
-- confidence and reason, never a bare score). match_task — the standalone match-resolution queue
-- (Principle III: human review is an architectural concept, not a screen).

create table if not exists match_candidate (
  id                              uuid primary key default gen_random_uuid(),
  tenant_id                       uuid not null references tenant(id) on delete cascade,
  quotation_line_id               uuid not null references quotation_line(id) on delete cascade,
  candidate_workspace_product_id  uuid not null references workspace_product(id),

  confidence       numeric(5, 4) not null check (confidence between 0 and 1),
  -- Structured, not free prose: {alias_hit, gtin_match, supplier_code_match, lexical_similarity,
  -- semantic_similarity, feature_score:{...}}. See specs/004-matching-normalisation/data-model.md.
  reasons          jsonb not null,
  rank             integer not null check (rank > 0),
  scoring_version  text not null,
  embedding_model  text,

  created_at       timestamptz not null default now(),

  constraint match_candidate_unique_product_per_run
    unique (tenant_id, quotation_line_id, candidate_workspace_product_id, scoring_version),
  constraint match_candidate_unique_rank_per_run
    unique (tenant_id, quotation_line_id, scoring_version, rank)
);

create index if not exists match_candidate_tenant_idx on match_candidate (tenant_id);
create index if not exists match_candidate_line_idx on match_candidate (quotation_line_id);

comment on table match_candidate is
  'One row per proposed product per quotation line. Deterministic candidates still get a row with
   confidence and reason — Principle I requires evidence even for the obvious match.';

-- ---------------------------------------------------------------------------
-- match_task — not a view over candidates/decisions. Its own status, priority and reason, so
-- queue work survives candidate regeneration and stays independent of a single quotation page.
-- ---------------------------------------------------------------------------
create table if not exists match_task (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null references tenant(id) on delete cascade,
  quotation_line_id  uuid not null references quotation_line(id) on delete cascade,

  status    match_task_status not null default 'open',
  priority  match_task_priority not null default 'normal',
  reason    match_task_reason not null,

  created_at   timestamptz not null default now(),
  resolved_at  timestamptz,

  constraint match_task_resolved_at_only_when_resolved
    check ((status = 'resolved') = (resolved_at is not null))
);

-- One outstanding task per line at a time.
create unique index if not exists match_task_one_open_per_line
  on match_task (tenant_id, quotation_line_id)
  where status in ('open', 'in_progress');
create index if not exists match_task_tenant_idx on match_task (tenant_id, status, priority);
