-- Spec 022 follow-up: preserve malformed extracted dates as evidence and route them to review.
alter type review_task_reason add value if not exists 'date_unparsed';
