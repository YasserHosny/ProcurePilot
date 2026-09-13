-- 20260914000004_advanced_basket_job_snapshot.sql
--
-- R2.4 keeps basket optimisation advisory and asynchronous, but advanced requests need a
-- replayable request snapshot for constraints, weights, supplier terms, and rule version.

alter table basket_split_job
  drop constraint if exists basket_split_job_exactly_two_distinct_suppliers;

create or replace function uuid_array_has_unique_items(p_values uuid[])
returns boolean
language sql
immutable
as $$
  select cardinality(p_values) = count(distinct item)
  from unnest(p_values) as item;
$$;

alter table basket_split_job
  add constraint basket_split_job_two_to_ten_suppliers
    check (
      cardinality(supplier_ids) between 2 and 10
      and uuid_array_has_unique_items(supplier_ids)
    );

alter table basket_split_job
  add column if not exists request_snapshot jsonb;

comment on column basket_split_job.request_snapshot is
  'Replayable optimiser request snapshot. Legacy two-supplier jobs may leave this null; R2.4
   advanced jobs store rule_version, constraints, weights, supplier terms, and request metadata for
   the optimiser worker.';
