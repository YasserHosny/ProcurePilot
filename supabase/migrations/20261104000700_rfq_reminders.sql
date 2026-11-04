-- 20261104000700_rfq_reminders.sql — manual supplier reminders (PPS-176).
--
-- A buyer can remind a supplier that has not answered an open RFQ. Reminders are always a person's
-- click (never scheduled) and are limited per supplier per RFQ; the API enforces the rules
-- (first reminder 24 hours after the RFQ was sent, one per 24 hours, two per RFQ) and writes an
-- `rfq.reminder_sent` audit event. This migration only stores the counters those rules need:
--   * reminder_count    reminders sent to this recipient so far
--   * last_reminder_at  when the latest one was sent
-- The existing rfq_recipient_update policy (creator, or owner since 20261104000200) already covers
-- the write. No data change.
--
-- Forward-only.

alter table rfq_recipient
  add column reminder_count integer not null default 0,
  add column last_reminder_at timestamptz;

alter table rfq_recipient
  add constraint rfq_recipient_reminder_count_check check (reminder_count >= 0),
  add constraint rfq_recipient_last_reminder_check
    check ((reminder_count = 0) = (last_reminder_at is null));
