-- 20260819000012_catalogue_products.sql — task T002
--
-- The product master. Three tables and one deliberate asymmetry.

-- ---------------------------------------------------------------------------
-- canonical_product — THE ONE TABLE IN THIS SCHEMA WITH NO tenant_id
--
-- Shared across workspaces on purpose. Roadmap §10.1 calls for a canonical spine so that
-- cross-tenant benchmarking stays reachable in year 3 without a migration over every customer's
-- catalogue. The split is what makes that safe: this table holds brand, name, variant, GTIN and
-- base unit and NOTHING that identifies a workspace — no naming preferences, no suppliers, no
-- substitutes. Those all live in workspace_product, which is tenant-scoped in the usual way.
--
-- If workspace data ever turns up somewhere it should not, CHECK THIS TABLE FIRST. It is the only
-- place the uniform Principle V pattern does not apply. See research.md R5 and the plan's
-- Complexity Tracking.
-- ---------------------------------------------------------------------------
create table if not exists canonical_product (
  id         uuid primary key default gen_random_uuid(),
  brand      text,
  name       text not null check (char_length(name) between 1 and 200),
  variant    text,
  -- GTIN-8/12/13/14. Shape only: we cannot verify that a syntactically valid code refers to the
  -- product someone claims. It is advisory, never a key.
  gtin       text check (gtin is null or gtin ~ '^[0-9]{8}$|^[0-9]{12,14}$'),
  base_unit  text not null references supported_base_unit(code),
  created_at timestamptz not null default now()
);

create unique index if not exists canonical_product_gtin_idx
  on canonical_product (gtin) where gtin is not null;
create index if not exists canonical_product_name_idx on canonical_product (lower(name));

-- ---------------------------------------------------------------------------
-- workspace_product — what a buyer actually sees and edits
-- ---------------------------------------------------------------------------
do $$ begin
  create type product_status as enum ('active', 'archived');
exception when duplicate_object then null; end $$;

create table if not exists workspace_product (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references tenant(id) on delete cascade,
  canonical_product_id uuid not null references canonical_product(id),
  tenant_name          text not null check (char_length(tenant_name) between 1 and 200),
  preferred_supplier_id uuid,   -- FK added in the supplier migration; that table does not exist yet
  status               product_status not null default 'active',
  created_at           timestamptz not null default now(),

  constraint workspace_product_one_view_per_canonical unique (tenant_id, canonical_product_id)
);

create index if not exists workspace_product_tenant_idx on workspace_product (tenant_id);
create index if not exists workspace_product_name_idx on workspace_product (tenant_id, lower(tenant_name));

-- Deliberately NOT unique on (tenant_id, lower(tenant_name)): a business legitimately buys
-- "gloves" from several suppliers in different specifications. Duplicates warn, they do not block.

-- ---------------------------------------------------------------------------
-- pack_definition — where Principle II gets its first real test
-- ---------------------------------------------------------------------------
create table if not exists pack_definition (
  id                   uuid primary key default gen_random_uuid(),
  -- Denormalised so the RLS policy is a column comparison rather than a join. Isolation should be
  -- cheap to enforce and obvious to read.
  tenant_id            uuid not null references tenant(id) on delete cascade,
  workspace_product_id uuid not null references workspace_product(id) on delete cascade,

  pack_count integer        not null check (pack_count > 0),
  unit_size  numeric(18, 6) not null check (unit_size > 0),

  -- GENERATED, not written. Nothing can set this independently, so it cannot drift from its
  -- inputs, and recomputation is not a second code path that might one day disagree with the
  -- original — which is exactly what "pure, versioned, replayable" asks for.
  --
  -- numeric, never double precision: binary floating point cannot represent 0.1, so 3 x 0.33
  -- would not reliably equal 0.99, and every landed-cost comparison in chunk 4.4 is downstream of
  -- this number. Six decimals covers millilitre-scale sizes without inviting false precision.
  base_quantity numeric(18, 6) generated always as (pack_count * unit_size) stored,

  created_at timestamptz not null default now()
);

create index if not exists pack_definition_tenant_idx on pack_definition (tenant_id);
create index if not exists pack_definition_product_idx on pack_definition (workspace_product_id);

-- ---------------------------------------------------------------------------
-- product_substitute
--
-- A table, not the data dictionary's uuid[]. An array cannot carry a foreign key, so a referenced
-- product could be archived or removed and the array would keep pointing at nothing.
-- ---------------------------------------------------------------------------
create table if not exists product_substitute (
  tenant_id             uuid not null references tenant(id) on delete cascade,
  workspace_product_id  uuid not null references workspace_product(id) on delete cascade,
  substitute_product_id uuid not null references workspace_product(id) on delete cascade,
  created_at            timestamptz not null default now(),

  primary key (tenant_id, workspace_product_id, substitute_product_id),
  constraint product_substitute_not_self check (workspace_product_id <> substitute_product_id)
);

comment on table canonical_product is
  'Shared across workspaces by design — the ONLY table here without tenant_id. Holds no
   workspace-identifying data. See specs/002-catalogue-suppliers/research.md R5.';
comment on column pack_definition.base_quantity is
  'Generated from pack_count * unit_size. Never written directly, so it cannot drift from its
   inputs (Constitution Principle II, SC-007).';
