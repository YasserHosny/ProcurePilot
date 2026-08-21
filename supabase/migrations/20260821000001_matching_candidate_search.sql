-- 20260821000001_matching_candidate_search.sql
--
-- Server-side pg_trgm + pgvector candidate pre-filter for chunk 4.4 matching. Chunk 4.4's first
-- backend pass (Lane A) scored candidates entirely in Python — difflib for "lexical similarity"
-- and a hand-rolled cosine calculation recomputed from scratch on every call — and never read or
-- wrote canonical_product.canonical_embedding / workspace_product.tenant_name_embedding at all.
-- That defeats the whole point of research.md R3/R4 and the trigram/vector indexes migration
-- 20260819000026 built for this chunk: real pg_trgm and pgvector usage, not an approximation.
--
-- This function does the real thing: trigram similarity via pg_trgm's similarity(), cosine
-- similarity via pgvector's <=> operator against the persisted embedding columns, combined the
-- same way the (now-replaced) Python _semantic_similarity helper did: cos_sim mapped from
-- [-1, 1] to [0, 1] via (cos_sim + 1) / 2, canonical/tenant-name components blended 70/30.
--
-- security invoker (the default for SQL functions, not declared here): runs as the calling role,
-- so workspace_product's tenant_isolation RLS policy still applies -- callers only ever see their
-- own tenant's rows plus the shared canonical_product spine, exactly as if they had queried the
-- tables directly. No new policy is needed for that reason.
--
-- A missing embedding scores its semantic component at the neutral 0.5, per research.md R5
-- ("missing optional features score neutral 0.5, not 0") -- never treated as a perfect or a zero
-- match.

create or replace function match_candidate_search(
  p_line_text text,
  p_line_embedding vector(256),
  p_trigram_threshold real default 0.30,
  p_semantic_threshold real default 0.10,
  p_limit int default 5
)
returns table (
  workspace_product_id uuid,
  lexical_similarity real,
  semantic_similarity real
)
language sql
stable
as $$
  select
    wp.id as workspace_product_id,
    greatest(
      similarity(
        lower(coalesce(cp.brand, '') || ' ' || coalesce(cp.name, '') || ' ' || coalesce(cp.variant, '')),
        lower(p_line_text)
      ),
      similarity(lower(wp.tenant_name), lower(p_line_text))
    )::real as lexical_similarity,
    (
      0.7 * case
        when cp.canonical_embedding is null then 0.5
        else (1 - (cp.canonical_embedding <=> p_line_embedding)) / 2 + 0.5
      end
      + 0.3 * case
        when wp.tenant_name_embedding is null then 0.5
        else (1 - (wp.tenant_name_embedding <=> p_line_embedding)) / 2 + 0.5
      end
    )::real as semantic_similarity
  from workspace_product wp
  join canonical_product cp on cp.id = wp.canonical_product_id
  where
    similarity(
      lower(coalesce(cp.brand, '') || ' ' || coalesce(cp.name, '') || ' ' || coalesce(cp.variant, '')),
      lower(p_line_text)
    ) >= p_trigram_threshold
    or similarity(lower(wp.tenant_name), lower(p_line_text)) >= p_trigram_threshold
    or (cp.canonical_embedding is not null and (1 - (cp.canonical_embedding <=> p_line_embedding)) >= p_semantic_threshold)
    or (wp.tenant_name_embedding is not null and (1 - (wp.tenant_name_embedding <=> p_line_embedding)) >= p_semantic_threshold)
  order by lexical_similarity desc, semantic_similarity desc
  limit p_limit;
$$;

comment on function match_candidate_search is
  'Real pg_trgm + pgvector candidate pre-filter for chunk 4.4 matching (research.md R3/R4).
   Replaces an earlier in-process Python approximation that never touched these columns.
   Call via PostgREST as client.rpc("match_candidate_search", {...}) so RLS still applies.';
