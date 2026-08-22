-- 20260819000014_product_alias.sql — task T004
--
-- What suppliers call things, per workspace.
--
-- This is the seed of the matching engine in chunk 4.4. It starts hand-fed — a human confirms that
-- a supplier's wording means a particular product — and becomes machine-fed once extraction exists.
-- Building the store now means 4.4 starts with a working memory rather than an empty one.

create table if not exists product_alias (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references tenant(id) on delete cascade,
  workspace_product_id uuid not null references workspace_product(id) on delete cascade,
  -- Which supplier used this wording. Nullable: a buyer may record an alias they have seen without
  -- attributing it to a supplier on file.
  supplier_id          uuid references supplier(id) on delete set null,
  alias_text           text not null check (char_length(alias_text) between 1 and 500),
  -- A human confirmed this mapping. Principle III: the machine proposes, a person decides.
  created_by           uuid references membership(id) on delete set null,
  created_at           timestamptz not null default now()
);

-- One meaning per wording per workspace. Two products claiming the same supplier description would
-- make resolution ambiguous, and an ambiguous match is worse than no match — it produces a
-- confident wrong answer.
create unique index if not exists product_alias_unique_per_tenant
  on product_alias (tenant_id, lower(alias_text));

create index if not exists product_alias_tenant_idx on product_alias (tenant_id);
create index if not exists product_alias_product_idx on product_alias (workspace_product_id);

comment on table product_alias is
  'Private to the workspace that recorded it (FR-027). One business''s vocabulary is not another''s,
   and sharing it would leak what they buy and from whom.';
