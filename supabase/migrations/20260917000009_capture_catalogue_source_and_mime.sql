-- 20260917000009_capture_catalogue_source_and_mime.sql — Wave 3 (T015/T017), chunk R3.0
-- (013-automated-ingestion)
--
-- Adds 'catalogue_import' as a document/quotation source channel (a genuinely distinct
-- provenance from upload/email/capture, not a mislabel of any of them), and widens
-- document.mime_type to accept image/heic — common for phone-camera capture uploads (R8) and
-- not previously accepted by document_mime_type_check (which Wave 2 already widened once for
-- text/plain).

alter type document_source_channel add value if not exists 'catalogue_import';

alter table document drop constraint document_mime_type_check;
alter table document add constraint document_mime_type_check check (mime_type in (
  'application/pdf', 'image/png', 'image/jpeg', 'image/tiff', 'image/heic',
  'text/csv', 'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/plain'
));

alter table quotation drop constraint quotation_source_valid;
alter table quotation add constraint quotation_source_valid
  check (source in ('upload', 'email', 'capture', 'catalogue_import'));
