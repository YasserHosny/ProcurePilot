import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { ApiError } from '../../core/api/models';

export type { ApiError };

export type IngestionEmailStatus =
  | 'received'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'duplicate'
  | 'rejected';

export type SupplierMatchMethod = 'address' | 'domain' | 'thread' | 'manual';

export type CatalogueImportStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type CatalogueImportFormat = 'csv' | 'xlsx';

export interface TenantEmailConfig {
  id: string;
  forwarding_address: string;
  enabled: boolean;
  domain_allowlist: string[] | null;
  daily_limit: number;
  daily_count: number;
  daily_count_date: string;
  spf_dkim_required: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantEmailConfigUpdate {
  enabled?: boolean | null;
  domain_allowlist?: string[] | null;
  daily_limit?: number | null;
  spf_dkim_required?: boolean | null;
}

export interface IngestionEmailLog {
  id: string;
  message_id: string;
  from_address: string;
  from_domain: string;
  subject: string | null;
  received_at: string;
  processed_at: string | null;
  status: IngestionEmailStatus;
  error_message: string | null;
  attachment_count: number;
  quotation_id: string | null;
  supplier_id: string | null;
  match_method: SupplierMatchMethod | null;
  created_at: string;
}

export interface IngestionEmailLogList {
  items: IngestionEmailLog[];
  next_cursor: string | null;
}

export interface ListEmailLogsParams {
  cursor?: string;
  limit?: number;
  status?: IngestionEmailStatus;
  from_domain?: string;
  date_from?: string;
  date_to?: string;
}

export interface CatalogueImportErrorDetail {
  row: number | null;
  column: string | null;
  error: string;
}

export interface CatalogueImportSummary {
  id: string;
  supplier_id: string;
  file_name: string;
  file_path: string;
  file_size_bytes: number;
  file_format: CatalogueImportFormat;
  status: CatalogueImportStatus;
  total_rows?: number | null;
  imported_rows?: number | null;
  skipped_rows?: number | null;
  error_rows?: number | null;
  error_details?: CatalogueImportErrorDetail[];
  column_mapping?: Record<string, unknown>;
  created_at: string;
  completed_at?: string | null;
  created_by: string;
}

export interface CatalogueImportSummaryList {
  items: CatalogueImportSummary[];
  next_cursor: string | null;
}

export interface ListCatalogueImportsParams {
  cursor?: string;
  limit?: number;
}

export interface IngestionStats {
  emails_received_today: number;
  emails_received_week: number;
  emails_received_month: number;
  capture_uploads_total: number;
  catalogue_imports_total: number;
  supplier_match_rate: number;
  extraction_success_rate: number;
  active_quotation_count: number;
  integration_sourced_quotation_count: number;
  integration_sourced_share: number;
  purchase_history_days: number;
  g3_history_ready: boolean;
  active_refresh_schedule_count: number;
  linked_refresh_schedule_count: number;
  refresh_pilot_ready: boolean;
}

export interface CaptureResult {
  quotation_id: string;
  status: string;
}

export interface CatalogueImportResult {
  id: string;
  supplier_id: string;
  status: string;
  total_rows: number;
  imported_rows: number;
  skipped_rows: number;
  error_rows: number;
  error_details: CatalogueImportErrorDetail[];
}

@Injectable({ providedIn: 'root' })
export class IngestionApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /**
   * Fetches the tenant email forwarding configuration.
   * On failure, emits an error matching {@link ApiError}.
   */
  getEmailConfig(): Observable<TenantEmailConfig> {
    return this.http.get<TenantEmailConfig>(`${this.base}/tenants/email-config`);
  }

  /**
   * Updates the tenant email configuration settings (e.g. domain allowlist).
   * On failure, emits an error matching {@link ApiError}.
   */
  updateEmailConfig(
    payload: Partial<TenantEmailConfigUpdate>
  ): Observable<TenantEmailConfig> {
    return this.http.put<TenantEmailConfig>(`${this.base}/tenants/email-config`, payload);
  }

  /**
   * Enables tenant email ingestion.
   * On failure, emits an error matching {@link ApiError}.
   */
  enableEmailConfig(): Observable<TenantEmailConfig> {
    return this.http.post<TenantEmailConfig>(`${this.base}/tenants/email-config/enable`, {});
  }

  /**
   * Disables tenant email ingestion.
   * On failure, emits an error matching {@link ApiError}.
   */
  disableEmailConfig(): Observable<TenantEmailConfig> {
    return this.http.post<TenantEmailConfig>(`${this.base}/tenants/email-config/disable`, {});
  }

  /**
   * Lists email ingestion logs with cursor pagination and optional filters.
   * On failure, emits an error matching {@link ApiError}.
   */
  listEmailLogs(params?: ListEmailLogsParams): Observable<IngestionEmailLogList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.from_domain) query.set('from_domain', params.from_domain);
    if (params?.date_from) query.set('date_from', params.date_from);
    if (params?.date_to) query.set('date_to', params.date_to);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<IngestionEmailLogList>(`${this.base}/ingestion/emails${qs}`);
  }

  /**
   * Submits a captured quotation file via multipart/form-data.
   * Note: Do NOT set Content-Type header manually; browser will set multipart boundary.
   * On failure, emits an error matching {@link ApiError}.
   */
  submitCapture(
    file: File,
    supplierId?: string,
    notes?: string
  ): Observable<CaptureResult> {
    const formData = new FormData();
    formData.append('file', file);
    if (supplierId) {
      formData.append('supplier_id', supplierId);
    }
    if (notes) {
      formData.append('notes', notes);
    }
    return this.http.post<CaptureResult>(`${this.base}/capture`, formData);
  }

  /**
   * Submits a supplier catalogue import file (CSV or XLSX) via multipart/form-data.
   * Note: Do NOT set Content-Type header manually; browser will set multipart boundary.
   * On failure, emits an error matching {@link ApiError}.
   */
  submitCatalogueImport(
    supplierId: string,
    file: File
  ): Observable<CatalogueImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<CatalogueImportResult>(
      `${this.base}/suppliers/${encodeURIComponent(supplierId)}/catalogue-import`,
      formData
    );
  }

  /**
   * Lists catalogue import history for a specific supplier.
   * On failure, emits an error matching {@link ApiError}.
   */
  listCatalogueImports(
    supplierId: string,
    params?: ListCatalogueImportsParams
  ): Observable<CatalogueImportSummaryList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<CatalogueImportSummaryList>(
      `${this.base}/suppliers/${encodeURIComponent(supplierId)}/catalogue-imports${qs}`
    );
  }

  /**
   * Retrieves aggregate statistics for the ingestion dashboard.
   * On failure, emits an error matching {@link ApiError}.
   */
  getStats(): Observable<IngestionStats> {
    return this.http.get<IngestionStats>(`${this.base}/ingestion/stats`);
  }
}
