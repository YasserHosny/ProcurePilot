alter table ingestion_email_log drop constraint if exists ingestion_email_log_match_method_check;
alter table ingestion_email_log add constraint ingestion_email_log_match_method_check 
  check (match_method in ('address', 'domain', 'thread', 'manual', 'rfq_reply'));
