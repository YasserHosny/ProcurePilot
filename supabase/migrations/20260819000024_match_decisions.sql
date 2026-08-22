-- 20260819000024_match_decisions.sql — task T007
--
-- match_decision — the immutable outcome for one quotation line. Append-only: this chunk never
-- updates or deletes an existing decision (Constitution Principle II). Correcting a previously
-- confirmed match is out of scope and needs its own supersession model later.

create table if not exists match_decision (
  id                             uuid primary key default gen_random_uuid(),
  tenant_id                      uuid not null references tenant(id) on delete cascade,
  quotation_line_id              uuid not null references quotation_line(id) on delete cascade,
  matched_workspace_product_id   uuid not null references workspace_product(id),
  selected_match_candidate_id    uuid references match_candidate(id),

  outcome        match_decision_outcome not null,
  is_automatic   boolean not null,
  decided_by     uuid references membership(id),
  decided_at     timestamptz not null default now(),
  confidence     numeric(5, 4) not null check (confidence between 0 and 1),
  alias_id       uuid references product_alias(id),

  created_at     timestamptz not null default now(),

  -- One final decision per line in this chunk. Correcting a match is a later chunk's concern.
  constraint match_decision_one_per_line unique (tenant_id, quotation_line_id),

  -- Automatic decisions have no human; human decisions must name one.
  constraint match_decision_human_or_automatic
    check (
      (is_automatic and decided_by is null)
      or (not is_automatic and decided_by is not null)
    ),

  -- no_match_new_product means "the newly created product is the match," not "unmatched" — every
  -- other outcome must reference the candidate the reviewer actually chose.
  constraint match_decision_candidate_required_unless_new_product
    check ((outcome = 'no_match_new_product') = (selected_match_candidate_id is null))
);

create index if not exists match_decision_tenant_idx on match_decision (tenant_id);
create index if not exists match_decision_product_idx on match_decision (matched_workspace_product_id);

comment on table match_decision is
  'Outcome history — append-only per Constitution Principle II. A later match correction needs its
   own supersession model, not an update to this row.';
