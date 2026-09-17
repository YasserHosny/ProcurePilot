-- 20260917000008_document_mime_type_text_plain.sql — Wave 2 T011, chunk R3.0 (013-automated-ingestion)
--
-- Widens document.mime_type's CHECK to accept 'text/plain' — needed for spec acceptance
-- scenario 5 (013-automated-ingestion/spec.md): a text-only inbound email (no attachments)
-- stores its body as the primary source document. Without this, that scenario cannot be
-- implemented at all: every existing mime_type is a file format a text email body is not.
--
-- Verified the constraint's actual name empirically (document_mime_type_check, Postgres's
-- default column-CHECK naming) rather than assuming it, since 20260819000018 declared it
-- inline with no explicit name.

alter table document drop constraint document_mime_type_check;
alter table document add constraint document_mime_type_check check (mime_type in (
  'application/pdf', 'image/png', 'image/jpeg', 'image/tiff',
  'text/csv', 'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/plain'
));
