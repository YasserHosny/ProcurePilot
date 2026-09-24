-- R4.3 Automated RFQ Sourcing
-- Foundational Tables (T005)

create table rfq (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  created_by_membership_id uuid not null,
  status                text not null check (status in ('draft', 'sent', 'responded', 'expired', 'converted')),
  needed_by_date        date not null,
  idempotency_key       uuid not null,
  created_at            timestamptz not null default now(),

  constraint rfq_tenant_id_key unique (tenant_id, id),
  constraint rfq_idempotency_key_unique unique (tenant_id, idempotency_key),
  constraint rfq_created_by_membership_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id)
);

create table rfq_line (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  rfq_id                uuid not null,
  workspace_product_id  uuid not null,
  quantity              numeric(18,6) not null check (quantity > 0),
  created_at            timestamptz not null default now(),

  constraint rfq_line_tenant_id_key unique (tenant_id, id),
  constraint rfq_line_rfq_fkey
    foreign key (tenant_id, rfq_id) references rfq (tenant_id, id) on delete cascade,
  constraint rfq_line_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id)
);

create table rfq_recipient (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  rfq_id                uuid not null,
  supplier_id           uuid not null,
  status                text not null check (status in ('draft', 'sent', 'failed')),
  outbound_message_id   text,
  sent_at               timestamptz,
  created_at            timestamptz not null default now(),

  constraint rfq_recipient_tenant_id_key unique (tenant_id, id),
  constraint rfq_recipient_rfq_fkey
    foreign key (tenant_id, rfq_id) references rfq (tenant_id, id) on delete cascade,
  constraint rfq_recipient_supplier_fkey
    foreign key (tenant_id, supplier_id) references supplier (tenant_id, id)
);

-- Note: quotation does not have unique (tenant_id, id) explicitly if it wasn't used in a composite key yet.
-- Let's add it if not present, just in case.
alter table quotation drop constraint if exists quotation_tenant_id_key;
alter table quotation add constraint quotation_tenant_id_key unique (tenant_id, id);

create table rfq_response (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  rfq_recipient_id      uuid not null,
  quotation_id          uuid not null,
  created_at            timestamptz not null default now(),

  constraint rfq_response_tenant_id_key unique (tenant_id, id),
  constraint rfq_response_rfq_recipient_fkey
    foreign key (tenant_id, rfq_recipient_id) references rfq_recipient (tenant_id, id) on delete cascade,
  constraint rfq_response_quotation_fkey
    foreign key (tenant_id, quotation_id) references quotation (tenant_id, id)
);



create table auto_preparation_guardrail (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null references tenant(id) on delete cascade,
  created_by_membership_id  uuid not null,
  max_order_value_amount    numeric(18,4) not null check (max_order_value_amount > 0),
  max_order_value_currency  text not null references supported_currency(code),
  supplier_allowlist        uuid[],
  category_allowlist        text[],
  min_response_count        integer not null check (min_response_count > 0),
  max_price_variance_pct    numeric(5,4) not null check (max_price_variance_pct >= 0),
  enabled                   boolean not null default false,
  created_at                timestamptz not null default now(),

  constraint auto_preparation_guardrail_tenant_id_key unique (tenant_id, id),
  constraint auto_preparation_guardrail_created_by_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id)
);

create table auto_preparation_event (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  guardrail_id          uuid not null,
  rfq_response_id       uuid not null,
  purchase_request_id   uuid,
  created_at            timestamptz not null default now(),

  constraint auto_preparation_event_tenant_id_key unique (tenant_id, id),
  constraint auto_preparation_event_guardrail_fkey
    foreign key (tenant_id, guardrail_id) references auto_preparation_guardrail (tenant_id, id),
  constraint auto_preparation_event_rfq_response_fkey
    foreign key (tenant_id, rfq_response_id) references rfq_response (tenant_id, id)
);

do $$
begin
  -- ensure purchase_request has the unique constraint if not present
  if not exists (select 1 from pg_constraint where conname = 'purchase_request_tenant_id_key') then
    alter table purchase_request add constraint purchase_request_tenant_id_key unique (tenant_id, id);
  end if;
end $$;

alter table auto_preparation_event
  add constraint auto_preparation_event_purchase_request_fkey
  foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id);

-- Enable forced RLS
do $$
declare
  t text;
begin
  foreach t in array array['rfq', 'rfq_line', 'rfq_recipient', 'rfq_response', 'auto_preparation_guardrail', 'auto_preparation_event'] loop
    execute format('alter table %I enable row level security', t);
    execute format('alter table %I force row level security', t);
  end loop;
end;
$$;

-- RLS policies

-- rfq: creator OR owner/buyer may read
create policy rfq_select on rfq
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      created_by_membership_id = current_membership_id()
      or current_member_role() in ('owner', 'buyer')
    )
  );

create policy rfq_insert on rfq
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
  );

create policy rfq_update on rfq
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
  )
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
  );

create policy rfq_delete on rfq
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
  );

-- rfq_line: inherits read from rfq
create policy rfq_line_select on rfq_line
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and (
          r.created_by_membership_id = current_membership_id()
          or current_member_role() in ('owner', 'buyer')
        )
    )
  );

create policy rfq_line_insert on rfq_line
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

create policy rfq_line_update on rfq_line
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  )
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

create policy rfq_line_delete on rfq_line
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_line.tenant_id
        and r.id = rfq_line.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

-- rfq_recipient: inherits read from rfq
create policy rfq_recipient_select on rfq_recipient
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and (
          r.created_by_membership_id = current_membership_id()
          or current_member_role() in ('owner', 'buyer')
        )
    )
  );

create policy rfq_recipient_insert on rfq_recipient
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

create policy rfq_recipient_update on rfq_recipient
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and (
          r.created_by_membership_id = current_membership_id()
          or current_member_role() in ('owner', 'buyer')
        )
    )
  );

create policy rfq_recipient_delete on rfq_recipient
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq r
      where r.tenant_id = rfq_recipient.tenant_id
        and r.id = rfq_recipient.rfq_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

-- rfq_response: inherits read from rfq_recipient -> rfq
create policy rfq_response_select on rfq_response
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq_recipient rr
      join rfq r on r.tenant_id = rr.tenant_id and r.id = rr.rfq_id
      where rr.tenant_id = rfq_response.tenant_id
        and rr.id = rfq_response.rfq_recipient_id
        and (
          r.created_by_membership_id = current_membership_id()
          or current_member_role() in ('owner', 'buyer')
        )
    )
  );

create policy rfq_response_insert on rfq_response
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq_recipient rr
      where rr.tenant_id = rfq_response.tenant_id
        and rr.id = rfq_response.rfq_recipient_id
    )
  );

create policy rfq_response_update on rfq_response
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq_recipient rr
      where rr.tenant_id = rfq_response.tenant_id
        and rr.id = rfq_response.rfq_recipient_id
    )
  );

create policy rfq_response_delete on rfq_response
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from rfq_recipient rr
      join rfq r on r.tenant_id = rr.tenant_id and r.id = rr.rfq_id
      where rr.tenant_id = rfq_response.tenant_id
        and rr.id = rfq_response.rfq_recipient_id
        and r.created_by_membership_id = current_membership_id()
    )
  );

-- auto_preparation_guardrail: creator OR owner/buyer may read
create policy guardrail_select on auto_preparation_guardrail
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      created_by_membership_id = current_membership_id()
      or current_member_role() in ('owner', 'buyer')
    )
  );

create policy guardrail_insert on auto_preparation_guardrail
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() = 'owner'
  );

create policy guardrail_update on auto_preparation_guardrail
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  );

create policy guardrail_delete on auto_preparation_guardrail
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  );

-- auto_preparation_event: read by owner/buyer or creator of guardrail
create policy event_select on auto_preparation_event
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (
      current_member_role() in ('owner', 'buyer')
      or exists (
        select 1 from auto_preparation_guardrail g
        where g.tenant_id = auto_preparation_event.tenant_id
          and g.id = auto_preparation_event.guardrail_id
          and g.created_by_membership_id = current_membership_id()
      )
    )
  );

create policy event_insert on auto_preparation_event
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
  );

-- Grants
grant select, insert, update, delete on rfq to authenticated;
grant select, insert, update, delete on rfq to service_role;

grant select, insert, update, delete on rfq_line to authenticated;
grant select, insert, update, delete on rfq_line to service_role;

grant select, insert, update, delete on rfq_recipient to authenticated;
grant select, insert, update, delete on rfq_recipient to service_role;

grant select, insert, update, delete on rfq_response to authenticated;
grant select, insert, update, delete on rfq_response to service_role;

grant select, insert, update, delete on auto_preparation_guardrail to authenticated;
grant select, insert, update, delete on auto_preparation_guardrail to service_role;

grant select, insert on auto_preparation_event to authenticated;
grant select, insert on auto_preparation_event to service_role;
revoke update, delete, truncate on auto_preparation_event from authenticated, service_role;
