-- 20261104000600_delivery_receipt_line_note.sql
--
-- A receipt line can carry a short note: why a delivery was short, or a damage or quality
-- remark (PPS-212). Optional; the existing row-level security and grants cover the new column.

alter table delivery_receipt_line
  add column if not exists note text
  check (note is null or char_length(note) between 1 and 500);

comment on column delivery_receipt_line.note is
  'Optional reason for a short receipt, or a damage or quality remark, entered at receipt time.';
