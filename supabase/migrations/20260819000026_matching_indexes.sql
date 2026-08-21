-- 20260819000026_matching_indexes.sql — task T009
--
-- Semantic and lexical search support for matching, added to the existing catalogue tables rather
-- than a new table — see specs/004-matching-normalisation/research.md R3/R4 (corrected) and
-- data-model.md's "Matching search indexes" section.
--
-- Two embeddings, not one, to respect the canonical_product/workspace_product boundary chunk 4.2
-- established: canonical_product is the shared spine and must hold nothing workspace-specific.
-- `tenant_name` is workspace vocabulary, so its embedding lives on workspace_product; brand/name/
-- variant are shared, so their embedding lives on canonical_product and is computed once per
-- canonical product rather than once per tenant.

alter table canonical_product
  add column if not exists canonical_embedding vector(256),
  add column if not exists canonical_embedding_model text;

comment on column canonical_product.canonical_embedding is
  'Built ONLY from brand, name and variant — fields canonical_product already legitimately holds.
   Must never be derived from workspace_product.tenant_name or any other workspace-specific text,
   or the shared spine would leak tenant vocabulary. See research.md R4.';

alter table workspace_product
  add column if not exists tenant_name_embedding vector(256),
  add column if not exists tenant_name_embedding_model text;

comment on column workspace_product.tenant_name_embedding is
  'Built ONLY from this workspace''s own tenant_name — tenant-scoped because the text it embeds is
   workspace-specific vocabulary. Combined with canonical_embedding similarity at query time.';

-- Lexical (pg_trgm) search: expression indexes, not a stored mixed canonical/workspace column —
-- storing a combined search string would recreate the same boundary problem the two embedding
-- columns above were split to avoid.
-- concat_ws() is STABLE, not IMMUTABLE, in this Postgres version and cannot back an index
-- expression; coalesce() + || (backed by the IMMUTABLE textcat) gives the same "join non-null
-- parts with a space" result and is index-safe.
create index if not exists canonical_product_text_trgm_idx
  on canonical_product using gin (
    lower(coalesce(brand, '') || ' ' || coalesce(name, '') || ' ' || coalesce(variant, ''))
    gin_trgm_ops
  );

create index if not exists workspace_product_tenant_name_trgm_idx
  on workspace_product using gin (lower(tenant_name) gin_trgm_ops);

-- Semantic (pgvector) search: no ANN index yet. research.md R4: "for the first pilot
-- implementation, an exact vector scan is acceptable until benchmark volume proves the index is
-- needed." An HNSW (cosine) index can be added in a later migration once real catalogue size
-- demands it — adding an index is a cheap, additive migration; removing premature complexity is
-- not.
