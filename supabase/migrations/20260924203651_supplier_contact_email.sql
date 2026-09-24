-- R4.3 Automated RFQ Sourcing
-- Add contact_email to supplier (T006)

alter table supplier add column contact_email text;
