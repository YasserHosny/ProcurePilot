-- 20260821000033_plan_billing_account.sql
--
-- plan — a deliberate shared-reference-table exception, the same class as canonical_product
-- (chunk 4.2) and the supported_* tables: global product metadata, not workspace-specific, so
-- there is no tenant_id and the uniform tenant_isolation policy cannot apply. See research.md R5.
--
-- billing_account — the tenant-scoped seam between plan-gating logic and whichever concrete
-- billing provider backs it. provider='stub' this chunk; no real Stripe credentials exist yet
-- (spec.md Assumptions, user-approved decision). Swapping in a real provider later changes only
-- what populates this table, not the plan-gating logic that reads from it.

create table if not exists plan (
  code                 text primary key,
  name                 text not null,
  status               plan_status not null default 'active',
  monthly_price_amount   numeric(18, 4) not null,
  monthly_price_currency text not null references supported_currency(code),
  limits               jsonb not null,
  features             jsonb not null default '{}'::jsonb,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

comment on table plan is
  'Shared product-tier definitions, readable by every workspace, writable by none of them
   directly — mirrors canonical_product''s exception exactly. See research.md R4/R5.';

insert into plan (code, name, monthly_price_amount, monthly_price_currency, limits, features)
values
  ('starter', 'Starter', 0.0000, 'GBP',
   '{"active_catalogue_products": 100}'::jsonb, '{}'::jsonb),
  ('growth', 'Growth', 0.0000, 'GBP',
   '{"active_catalogue_products": 1000}'::jsonb, '{}'::jsonb)
on conflict (code) do nothing;

create table if not exists billing_account (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null unique references tenant(id) on delete cascade,
  plan_code                 text not null references plan(code),
  provider                  text not null default 'stub',
  provider_customer_id      text not null,
  provider_subscription_id  text,
  status                    billing_account_status not null default 'active',
  current_period_start      timestamptz,
  current_period_end        timestamptz,
  assigned_at               timestamptz not null default now(),
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now(),

  constraint billing_account_provider_stub_only
    check (provider = 'stub'),
  constraint billing_account_period_order
    check (
      current_period_end is null or current_period_start is null
      or current_period_end >= current_period_start
    )
);

create index if not exists billing_account_tenant_plan_idx
  on billing_account (tenant_id, plan_code);

comment on table billing_account is
  'One row per workspace, assigning it to a shared plan through the billing-provider abstraction.
   provider is restricted to ''stub'' until real Stripe credentials exist and a migration lifts
   this check. See research.md R4.';

comment on constraint billing_account_provider_stub_only on billing_account is
  'Deliberately narrow for this chunk — see spec.md Assumptions. Widen (do not drop) when a real
   provider is added.';
