-- Add Xero to the existing accounting provider enum without changing the table,
-- tenant RLS, FORCE RLS, policies, grants, or existing rows.
alter type accounting_provider add value if not exists 'xero';
