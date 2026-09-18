# Data Model: Automated Ingestion

**Feature**: 013-automated-ingestion
**Created**: 2026-09-17
**Status**: Draft

## New Tables

### `ingestion_email_log`

Stores metadata for every inbound email processed by the ingestion worker. Used for
deduplication, audit, and replay.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | `uuid` | NOT NULL | | FK → `tenants.id`. RLS policy. |
| `message_id` | `text` | NOT NULL | | RFC 5322 Message-ID. Unique per tenant. |
| `from_address` | `text` | NOT NULL | | Sender email address (envelope from). |
| `from_domain` | `text` | NOT NULL | | Extracted domain from sender. Indexed. |
| `subject` | `text` | | | Email subject line. |
| `in_reply_to` | `text` | | | In-Reply-To header for thread tracking. |
| `references` | `text[]` | | | References header (array of Message-IDs). |
| `received_at` | `timestamptz` | NOT NULL | `now()` | When the email was received by SES/Mailgun. |
| `processed_at` | `timestamptz` | | | When the worker finished processing. |
| `status` | `text` | NOT NULL | `'received'` | `received`, `processing`, `completed`, `failed`, `duplicate`, `rejected` |
| `error_message` | `text` | | | Failure reason if status = `failed` or `rejected`. |
| `attachment_count` | `int` | NOT NULL | `0` | Number of attachments found. |
| `raw_email_ref` | `text` | | | S3/Storage key for the raw email (replay). |
| `quotation_id` | `uuid` | | | FK → `quotations.id`. Set after quotation creation. |
| `supplier_id` | `uuid` | | | FK → `suppliers.id`. Set if supplier identified. |
| `match_method` | `text` | | | How supplier was matched: `address`, `domain`, `thread`, `manual`, `null`. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | |

**Indexes**:
- `UNIQUE (tenant_id, message_id)` — deduplication constraint
- `(tenant_id, from_domain)` — supplier domain lookup
- `(tenant_id, status)` — operational monitoring
- `(tenant_id, received_at DESC)` — chronological listing

**RLS** (ENABLE + FORCE):
```sql
CREATE POLICY ingestion_email_log_tenant_isolation ON ingestion_email_log
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

### `ingestion_jobs`

Worker queue for ingestion processing tasks. Uses `FOR UPDATE SKIP LOCKED` pattern matching
existing workers (report_scheduler, digest_worker, export_worker).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | `uuid` | NOT NULL | | FK → `tenants.id`. RLS policy. |
| `job_type` | `text` | NOT NULL | | `email_ingest`, `capture_ingest`, `catalogue_import` |
| `status` | `text` | NOT NULL | `'pending'` | `pending`, `processing`, `completed`, `failed` |
| `payload` | `jsonb` | NOT NULL | | Job-specific data (SQS message ref, file path, etc.) |
| `attempts` | `int` | NOT NULL | `0` | Retry count. |
| `max_attempts` | `int` | NOT NULL | `3` | |
| `last_error` | `text` | | | Error message from last failed attempt. |
| `locked_by` | `text` | | | Worker instance ID holding the lock. |
| `locked_at` | `timestamptz` | | | When the lock was acquired. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | |
| `completed_at` | `timestamptz` | | | |

**Indexes**:
- `(status, created_at)` where `status = 'pending'` — worker polling
- `(tenant_id, job_type, status)` — operational monitoring

**RLS** (ENABLE + FORCE):
```sql
CREATE POLICY ingestion_jobs_tenant_isolation ON ingestion_jobs
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

### `tenant_email_config`

Per-tenant email ingestion configuration. One row per tenant.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | `uuid` | NOT NULL | | FK → `tenants.id`. Unique. RLS policy. |
| `forwarding_address` | `text` | NOT NULL | | `{slug}@ingest.procurepilot.com`. Unique. |
| `enabled` | `boolean` | NOT NULL | `true` | Owner can disable ingestion. |
| `domain_allowlist` | `text[]` | | | Optional: only accept from these domains. |
| `daily_limit` | `int` | NOT NULL | `100` | Max emails accepted per day. |
| `daily_count` | `int` | NOT NULL | `0` | Current day's count. Reset by scheduler. |
| `daily_count_date` | `date` | NOT NULL | `CURRENT_DATE` | Date of the current count. |
| `spf_dkim_required` | `boolean` | NOT NULL | `false` | Require SPF/DKIM pass. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | |
| `created_by` | `uuid` | NOT NULL | | FK → `members.id`. |

**Indexes**:
- `UNIQUE (tenant_id)`
- `UNIQUE (forwarding_address)`

**RLS** (ENABLE + FORCE):
```sql
CREATE POLICY tenant_email_config_tenant_isolation ON tenant_email_config
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

### `catalogue_imports`

Records each supplier catalogue import operation and its results.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | `uuid` | NOT NULL | | FK → `tenants.id`. RLS policy. |
| `supplier_id` | `uuid` | NOT NULL | | FK → `suppliers.id`. |
| `file_name` | `text` | NOT NULL | | Original upload filename. |
| `file_path` | `text` | NOT NULL | | Storage key in Supabase Storage. |
| `file_size_bytes` | `bigint` | NOT NULL | | |
| `file_format` | `text` | NOT NULL | | `csv` or `xlsx`. |
| `status` | `text` | NOT NULL | `'pending'` | `pending`, `processing`, `completed`, `failed` |
| `total_rows` | `int` | | | Total data rows (excluding header). |
| `imported_rows` | `int` | | | Successfully imported rows. |
| `skipped_rows` | `int` | | | Rows skipped (duplicates, etc.). |
| `error_rows` | `int` | | | Rows with validation errors. |
| `error_details` | `jsonb` | | | Array of `{row, column, error}` objects. |
| `column_mapping` | `jsonb` | | | Resolved column mapping used. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | |
| `completed_at` | `timestamptz` | | | |
| `created_by` | `uuid` | NOT NULL | | FK → `members.id`. |

**Indexes**:
- `(tenant_id, supplier_id, created_at DESC)` — import history per supplier
- `(tenant_id, status)` — operational monitoring

**RLS** (ENABLE + FORCE):
```sql
CREATE POLICY catalogue_imports_tenant_isolation ON catalogue_imports
  FOR ALL
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

## Enum Extensions

### `document_source_channel`

Currently defined as `enum ('upload')` in migration `20260819000017_quotation_reference.sql`.
Extend with forward-only migration:

```sql
ALTER TYPE document_source_channel ADD VALUE 'email';
ALTER TYPE document_source_channel ADD VALUE 'capture';
```

The `document.source_channel` column will use these new values for ingested documents.
The existing `'upload'` value is preserved for manual file uploads.

---

## Modified Tables

### `quotations` — New columns

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `source` | `text` | NOT NULL | `'upload'` | `upload`, `email`, `capture`. Default preserves backward compatibility. |
| `ingestion_email_id` | `uuid` | | | FK → `ingestion_email_log.id`. Set when source = `email`. |

**Migration**: Add column with default, backfill existing rows to `'upload'`.

### `suppliers` — New columns

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `email_domains` | `text[]` | | | Domains associated with this supplier for email matching. Indexed with GIN. |

**Migration**: Add column, populate from existing `supplier_contacts` where available.

---

## New Storage Buckets

### `ingestion-raw`

Stores raw inbound emails for replay capability.

- **Path pattern**: `{tenant_id}/raw-email/{message_id}`
- **RLS**: tenant-scoped, service-role write only.
- **Retention**: 90 days (configurable per tenant).

### Existing `documents` bucket — Extended paths

Ingested attachments and capture uploads use the existing documents bucket with new path
prefixes:

- **Email attachments**: `{tenant_id}/ingestion/email/{quotation_id}/{filename}`
- **Capture uploads**: `{tenant_id}/ingestion/capture/{quotation_id}/{filename}`
- **Catalogue files**: `{tenant_id}/ingestion/catalogue/{import_id}/{filename}`

---

## New Audit Events

| Event | Outcome | Notes |
|---|---|---|
| `email_received` | `success` | Inbound email accepted and queued. |
| `email_rejected` | `refused` | Email rejected (rate limit, disabled, unsupported). |
| `email_duplicate` | `success` | Duplicate Message-ID detected, skipped. |
| `email_supplier_matched` | `success` | Supplier identified from email. |
| `email_supplier_unmatched` | `success` | No supplier match; routed to review queue. |
| `capture_uploaded` | `success` | File uploaded via capture endpoint. |
| `capture_rejected` | `refused` | Capture rejected (file size, type). |
| `catalogue_import_started` | `success` | Catalogue import initiated. |
| `catalogue_import_completed` | `success` | Catalogue import finished. |
| `catalogue_import_failed` | `refused` | Catalogue import failed. |

---

## State Machines

### Ingestion Email Status

```
received → processing → completed
                     → failed (retryable)
                     → duplicate (terminal)
                     → rejected (terminal)
```

### Ingestion Job Status

```
pending → processing → completed
                    → failed → pending (retry, if attempts < max_attempts)
                             → failed (terminal, if attempts >= max_attempts)
```

### Catalogue Import Status

```
pending → processing → completed
                    → failed
```
