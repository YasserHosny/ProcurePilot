-- Add reviewer notes column to quotation table
alter table quotation add column if not exists reviewer_notes text;
