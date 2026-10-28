-- PPS flow review 2026-10-28, R2: keep RFQ lines in the order the buyer entered them.
--
-- Every line of one save gets the same created_at (now() is the transaction start), so
-- "order by created_at" returned them in an undefined order on screen and in the supplier
-- email. The API now writes position (0-based, in request order) on create and on draft
-- update, and every read orders by position.
--
-- Column-only change: rfq_line keeps its ENABLE + FORCE row-level security and its existing
-- policies (20261018000007), and table-level grants (20261018000005) cover the new column.
-- The default 0 keeps inserts that do not name position (older fixtures) valid; ties fall
-- back to created_at, id in the readers.

alter table rfq_line
  add column position integer not null default 0
    constraint rfq_line_position_nonnegative check (position >= 0);

-- Existing RFQs: the best order still recoverable is created_at, then id.
update rfq_line l
set position = n.position
from (
  select id,
         (row_number() over (partition by rfq_id order by created_at, id) - 1)::integer
           as position
  from rfq_line
) n
where n.id = l.id;
