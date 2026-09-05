-- 20260905000004_matching_append_only.sql
--
-- FR-017 (specs/004-matching-normalisation/spec.md): "Match and cost outcome history MUST be
-- append-only; a later computation or decision MUST NOT destructively overwrite an earlier one."
--
-- Migration 0027 gave match_candidate, match_task, match_decision and landed_cost a uniform
-- `for all` policy and `grant select, insert, update, delete` — correct for match_task (a working
-- queue item whose status legitimately transitions open -> in_progress -> resolved, exactly like
-- review_task elsewhere in this codebase), but wrong for the other three: application code only
-- ever inserts and selects match_candidate, match_decision and landed_cost (verified against
-- every `.table(...)` call site in the matching and landed_cost modules) — nothing legitimately
-- updates or deletes a recorded candidate, decision, or cost. Constitution non-negotiable #7 makes
-- the identical demand of audit_event; this migration applies that exact pattern here instead of
-- relying on application-code discipline, per docs/quality/matching-normalisation-audit.md §3.1.
--
-- tenant_id/quotation_line_id still cascade from tenant/quotation_line for tenant-teardown
-- purposes; quotation_line itself is soft-deleted in ordinary operation (see
-- 20260904000001_quotation_soft_delete.sql), so this cascade only fires on a full tenant
-- deletion, not on everyday business use — left unchanged.

do $$
declare t text;
begin
  foreach t in array array['match_candidate', 'match_decision', 'landed_cost'] loop
    execute format('drop policy if exists tenant_isolation on %I', t);

    execute format($f$
      create policy %I on %I
        for select
        to authenticated
        using (tenant_id = current_tenant_id())
    $f$, t || '_read', t);

    execute format($f$
      create policy %I on %I
        for insert
        to authenticated
        with check (tenant_id = current_tenant_id())
    $f$, t || '_append', t);

    execute format('revoke update, delete on %I from authenticated, anon, public', t);

    execute format(
      'comment on policy %I on %I is %L',
      t || '_append',
      t,
      'Insert only. No UPDATE or DELETE policy by design (FR-017) — matched and priced outcome '
        || 'history must not be rewritable.'
    );
  end loop;
end $$;
