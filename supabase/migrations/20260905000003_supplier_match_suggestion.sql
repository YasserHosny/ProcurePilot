alter type review_task_reason add value if not exists 'no_supplier_match';

alter table quotation
  add column if not exists suggested_supplier_id uuid,
  add column if not exists supplier_match_confidence numeric(4,3)
    check (supplier_match_confidence is null or supplier_match_confidence between 0 and 1);

alter table quotation
  add constraint quotation_suggested_supplier_id_fkey
  foreign key (suggested_supplier_id) references supplier(id) on delete set null;
