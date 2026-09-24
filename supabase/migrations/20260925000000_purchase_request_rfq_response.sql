alter table purchase_request add column source_rfq_response_id uuid;
alter table purchase_request add constraint purchase_request_tenant_source_rfq_response_fkey
  foreign key (tenant_id, source_rfq_response_id) references rfq_response (tenant_id, id);
