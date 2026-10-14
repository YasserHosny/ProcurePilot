-- Spec 022 FR-011: a quotation whose currency the document does not evidence is routed to
-- review with its own reason instead of being given a guessed currency.
alter type review_task_reason add value if not exists 'currency_unresolved';
