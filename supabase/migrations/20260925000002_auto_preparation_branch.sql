alter table auto_preparation_guardrail add column default_branch_id uuid not null
  references branch(id);
alter table auto_preparation_guardrail add constraint
  auto_preparation_guardrail_tenant_default_branch_fkey
  foreign key (tenant_id, default_branch_id) references branch (tenant_id, id);
