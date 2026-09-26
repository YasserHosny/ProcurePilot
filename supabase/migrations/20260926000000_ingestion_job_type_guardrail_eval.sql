-- 20260926000000_ingestion_job_type_guardrail_eval.sql — deferred RFQ guardrail evaluation
-- Match decisions are created after asynchronous extraction and matching; guardrail evaluation
-- therefore runs as a retryable database-backed worker job.

alter type ingestion_job_type add value if not exists 'guardrail_eval';
