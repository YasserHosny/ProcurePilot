-- R4.2 Grounded Procurement Analyst: analyst_conversation, analyst_turn (append-only),
-- and analyst_turn_citation (typed, tenant-pinned, exactly one source per row).
--
-- RLS read policy: the creating member OR any member with role owner/buyer in the same tenant
-- (FR-009 oversight read, not self-only). analyst_turn_citation inherits select from turn.
-- analyst_turn is APPEND-ONLY: authenticated role receives INSERT/SELECT only.
-- analyst_turn_citation likewise: INSERT/SELECT only for authenticated.
--
-- Purely additive, same pattern as 20260823000042_workspace_product_landed_cost_composite_keys.sql:
-- quotation_line and saving_record predate the composite-tenant-FK convention and have never been
-- referenced from a composite-FK table before, so they need a (tenant_id, id) unique constraint
-- before analyst_turn_citation can reference them the same way it references the other five
-- citation kinds. No existing column, data, or behaviour change on either table.
alter table quotation_line add constraint quotation_line_tenant_id_key unique (tenant_id, id);
alter table saving_record  add constraint saving_record_tenant_id_key  unique (tenant_id, id);

create table analyst_conversation (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  creating_member_id    uuid not null,
  created_at            timestamptz not null default now(),

  constraint analyst_conversation_tenant_id_key unique (tenant_id, id),
  constraint analyst_conversation_creating_member_fkey
    foreign key (tenant_id, creating_member_id) references membership (tenant_id, id)
);

create index analyst_conversation_tenant_member_idx
  on analyst_conversation (tenant_id, creating_member_id, created_at desc);

create table analyst_turn (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  conversation_id       uuid not null,
  creating_member_id    uuid not null,
  question_text         text not null,
  category              text not null,
  answer_text           text not null,
  calculation_version   text not null,
  release_posture       text not null default 'g3_unmet' check (release_posture = 'g3_unmet'),
  next_step_url         text,
  created_at            timestamptz not null default now(),

  constraint analyst_turn_tenant_id_key unique (tenant_id, id),
  constraint analyst_turn_conversation_fkey
    foreign key (tenant_id, conversation_id)
    references analyst_conversation (tenant_id, id) on delete cascade,
  constraint analyst_turn_creating_member_fkey
    foreign key (tenant_id, creating_member_id) references membership (tenant_id, id),
  constraint analyst_turn_category_nonempty check (char_length(btrim(category)) > 0),
  constraint analyst_turn_question_nonempty check (char_length(btrim(question_text)) > 0)
);

create index analyst_turn_conversation_idx
  on analyst_turn (tenant_id, conversation_id, created_at asc);

-- analyst_turn_citation: exactly one typed, tenant-pinned source reference per row.
-- Mirrors supplier_scorecard_evidence's typed-reference-per-row pattern exactly.
-- One nullable FK column per source kind; check constraint enforces exactly one non-null.
create table analyst_turn_citation (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null references tenant(id) on delete cascade,
  turn_id                   uuid not null,
  -- One and only one of the following FK columns must be non-null:
  purchase_order_id         uuid,
  quotation_line_id         uuid,
  landed_cost_id            uuid,
  saving_record_id          uuid,
  supplier_scorecard_snapshot_id uuid,
  delivery_receipt_id       uuid,
  reorder_proposal_id       uuid,
  created_at                timestamptz not null default now(),

  constraint analyst_turn_citation_tenant_id_key unique (tenant_id, id),
  constraint analyst_turn_citation_turn_fkey
    foreign key (tenant_id, turn_id)
    references analyst_turn (tenant_id, id) on delete cascade,
  constraint analyst_turn_citation_purchase_order_fkey
    foreign key (tenant_id, purchase_order_id)
    references purchase_order (tenant_id, id),
  constraint analyst_turn_citation_quotation_line_fkey
    foreign key (tenant_id, quotation_line_id)
    references quotation_line (tenant_id, id),
  constraint analyst_turn_citation_landed_cost_fkey
    foreign key (tenant_id, landed_cost_id)
    references landed_cost (tenant_id, id),
  constraint analyst_turn_citation_saving_record_fkey
    foreign key (tenant_id, saving_record_id)
    references saving_record (tenant_id, id),
  constraint analyst_turn_citation_scorecard_snapshot_fkey
    foreign key (tenant_id, supplier_scorecard_snapshot_id)
    references supplier_scorecard_snapshot (tenant_id, id),
  constraint analyst_turn_citation_delivery_receipt_fkey
    foreign key (tenant_id, delivery_receipt_id)
    references delivery_receipt (tenant_id, id),
  constraint analyst_turn_citation_reorder_proposal_fkey
    foreign key (tenant_id, reorder_proposal_id)
    references reorder_proposal (tenant_id, id),
  -- Exactly one source per row (mirrors supplier_scorecard_evidence's pattern):
  constraint analyst_turn_citation_exactly_one_source check (
    num_nonnulls(
      purchase_order_id,
      quotation_line_id,
      landed_cost_id,
      saving_record_id,
      supplier_scorecard_snapshot_id,
      delivery_receipt_id,
      reorder_proposal_id
    ) = 1
  )
);

create index analyst_turn_citation_turn_idx
  on analyst_turn_citation (tenant_id, turn_id);

-- RLS, grants — three tables, consistent pattern.
do $$
declare
  t text;
begin
  foreach t in array array['analyst_conversation', 'analyst_turn', 'analyst_turn_citation'] loop
    execute format('alter table %I enable row level security', t);
    execute format('alter table %I force row level security', t);
  end loop;
end;
$$;

-- analyst_conversation: creator OR owner/buyer may read (FR-009).
create policy analyst_conversation_select on analyst_conversation
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      creating_member_id = current_membership_id()
      or current_member_role() in ('owner', 'buyer')
    )
  );

create policy analyst_conversation_insert on analyst_conversation
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and creating_member_id = current_membership_id()
  );

-- analyst_turn: creator OR owner/buyer may read (FR-009).
create policy analyst_turn_select on analyst_turn
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      creating_member_id = current_membership_id()
      or current_member_role() in ('owner', 'buyer')
    )
  );

create policy analyst_turn_insert on analyst_turn
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and creating_member_id = current_membership_id()
  );

-- analyst_turn_citation: inherits read from turn — same creator/owner/buyer rule.
create policy analyst_turn_citation_select on analyst_turn_citation
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from analyst_turn t
      where t.tenant_id = analyst_turn_citation.tenant_id
        and t.id = analyst_turn_citation.turn_id
        and (
          t.creating_member_id = current_membership_id()
          or current_member_role() in ('owner', 'buyer')
        )
    )
  );

create policy analyst_turn_citation_insert on analyst_turn_citation
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from analyst_turn t
      where t.tenant_id = analyst_turn_citation.tenant_id
        and t.id = analyst_turn_citation.turn_id
        and t.creating_member_id = current_membership_id()
    )
  );

-- Grants: analyst_turn is APPEND-ONLY — authenticated gets INSERT/SELECT only, no UPDATE/DELETE.
grant select, insert on analyst_conversation to authenticated;
grant select, insert, update, delete on analyst_conversation to service_role;
revoke update, delete, truncate on analyst_conversation from authenticated;

grant select, insert on analyst_turn to authenticated;
grant select, insert on analyst_turn to service_role;
revoke update, delete, truncate on analyst_turn from authenticated, service_role;

grant select, insert on analyst_turn_citation to authenticated;
grant select, insert on analyst_turn_citation to service_role;
revoke update, delete, truncate on analyst_turn_citation from authenticated, service_role;
