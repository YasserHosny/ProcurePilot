-- 0002_reference_tables.sql — task T012
--
-- Region, currency, and tax model are collected from the registrant at sign-up and validated
-- against these tables (FR-031, FR-032). They are DATA, not code: widening the supported set is
-- an insert or an is_enabled flip, never a migration and never a deploy.
-- Global, not tenant-scoped: readable by any authenticated user, writable by service role only.

create table if not exists supported_region (
  code        text primary key,
  label_en    text not null,
  label_ar    text not null,
  is_enabled  boolean not null default true,
  created_at  timestamptz not null default now()
);

create table if not exists supported_currency (
  code        text primary key check (code ~ '^[A-Z]{3}$'),   -- ISO 4217
  label_en    text not null,
  label_ar    text not null,
  minor_units smallint not null default 2,                    -- decimal places; JPY is 0
  is_enabled  boolean not null default true,
  created_at  timestamptz not null default now()
);

create table if not exists supported_tax_model (
  code        text primary key,
  label_en    text not null,
  label_ar    text not null,
  region_code text references supported_region(code),
  is_enabled  boolean not null default true,
  created_at  timestamptz not null default now()
);

alter table supported_region     enable row level security;
alter table supported_currency   enable row level security;
alter table supported_tax_model  enable row level security;

-- Readable by anyone signed in, and by anonymous callers: the sign-up screen must list the
-- options before an account exists (GET /reference/config-options is unauthenticated).
create policy reference_region_read   on supported_region    for select to anon, authenticated using (true);
create policy reference_currency_read on supported_currency  for select to anon, authenticated using (true);
create policy reference_tax_read      on supported_tax_model for select to anon, authenticated using (true);

-- No insert/update/delete policy for anon or authenticated: writes are service-role only,
-- and the service role bypasses RLS. Absence of a policy is the denial.
