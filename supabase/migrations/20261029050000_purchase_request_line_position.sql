-- PPS-99 (UX audit 2026-10-28, R1-M1): keep purchase request lines in the order they were given.
--
-- Every line of one save gets the same created_at (now() is the transaction start), so reads
-- ordered by created_at, id came back in uuid order: an RFQ entered as rice, oil, sugar, flour
-- showed as oil, sugar, rice, flour on the request and flour, rice, sugar, oil in approvals.
-- The API now writes position (0-based, in request order) and every read orders by position.
--
-- Column-only change: purchase_request_line keeps its ENABLE + FORCE row-level security and
-- its existing policies; table-level grants cover the new column. The default 0 keeps inserts
-- that do not name position valid; ties fall back to created_at, id in the readers.

alter table purchase_request_line
  add column position integer not null default 0
    constraint purchase_request_line_position_nonnegative check (position >= 0);

-- Existing requests: the best order still recoverable is created_at, then id.
update purchase_request_line l
set position = n.position
from (
  select id,
         (row_number() over (partition by purchase_request_id order by created_at, id) - 1)::integer
           as position
  from purchase_request_line
) n
where n.id = l.id;
