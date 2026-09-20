import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { ApiError } from '../../core/api/models';

export type { ApiError };

export type AccountingProvider = 'quickbooks';

export type AccountingConnectionStatus = 'active' | 'needs_reauth' | 'disconnected';

export interface AccountingConnection {
  id: string;
  provider: 'quickbooks';
  display_name: string;
  status: 'active' | 'needs_reauth' | 'disconnected';
  connected_at: string;
  last_synced_at: string | null;
  disconnected_at: string | null;
}

export interface StartConnectionResponse {
  authorization_url: string;
}

export type BillProviderStatus = 'open' | 'paid' | 'void';

export type BillMatchStatus = 'matched' | 'unmatched';

export interface SyncedBill {
  id: string;
  vendor_name: string;
  matched_supplier_id: string | null;
  /**
   * Decimal string representation of the bill amount, never a number.
   * ProcurePilot handles all monetary values as decimal strings to prevent IEEE 754 precision loss.
   */
  amount: string;
  currency: string;
  bill_date: string;
  provider_status: 'open' | 'paid' | 'void';
  matched: boolean;
  purchase_record_id: string | null;
}

export interface SyncedBillList {
  items: SyncedBill[];
  next_cursor: string | null;
}

export interface ListBillsParams {
  cursor?: string;
  limit?: number;
  match_status?: 'matched' | 'unmatched';
}

export interface TriggerSyncResponse {
  status: 'enqueued';
}

export type DiscrepancyType =
  | 'amount_mismatch'
  | 'unmatched_bill'
  | 'unmatched_purchase'
  | 'missing_confirmation'
  | 'missing_receipt'
  | 'quantity_variance'
  | 'price_variance'
  | 'currency_mismatch'
  | 'invoice_without_order'
  | 'ambiguous_order'
  | 'over_billed_quantity'
  | 'over_billed_price';

export type DiscrepancyStatus = 'open' | 'resolved';

export interface SyncedBillDetail {
  vendor_name: string;
  amount: string;
  currency: string;
  bill_date: string;
}

export interface PurchaseRecordDetail {
  supplier_name: string;
  amount: string;
  currency: string;
  date: string;
}

export interface PurchaseOrderDetail {
  order_number: string;
  status: string;
  order_date: string;
}

export type ThreeWayMatchResult =
  | 'matched'
  | 'partial'
  | 'needs_review'
  | 'unmatched'
  | 'unavailable';

export interface ThreeWayMatchSummary {
  result: ThreeWayMatchResult;
  tolerance_ruleset_version: string;
  source_hash: string;
  evaluated_at: string;
  ordered_quantity: string | null;
  confirmed_quantity: string | null;
  received_quantity: string | null;
  invoiced_quantity: string | null;
  ordered_unit_price_amount: string | null;
  ordered_unit_price_currency: string | null;
  invoiced_unit_price_amount: string | null;
  invoiced_unit_price_currency: string | null;
  ordered_total_amount: string | null;
  ordered_total_currency: string | null;
  invoiced_total_amount: string | null;
  invoiced_total_currency: string | null;
}

export interface ReconciliationDiscrepancy {
  id: string;
  discrepancy_type: DiscrepancyType;
  synced_bill_id: string | null;
  purchase_record_id: string | null;
  status: DiscrepancyStatus;
  detected_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  synced_bill_detail?: SyncedBillDetail | null;
  purchase_record_detail?: PurchaseRecordDetail | null;
  three_way_match_id?: string | null;
  purchase_order_id?: string | null;
  evidence?: Record<string, unknown> | null;
  source_hash?: string | null;
  source_updated_at?: string | null;
  reopened_at?: string | null;
  three_way_match?: ThreeWayMatchSummary | null;
  purchase_order_detail?: PurchaseOrderDetail | null;
}

export interface ReconciliationDiscrepancyList {
  items: ReconciliationDiscrepancy[];
  next_cursor: string | null;
}

export interface ListDiscrepanciesParams {
  cursor?: string;
  limit?: number;
  status?: DiscrepancyStatus;
}

export interface ResolveDiscrepancyRequest {
  note?: string;
}

@Injectable({ providedIn: 'root' })
export class AccountingApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /**
   * Starts the QuickBooks OAuth authorization flow.
   * Returns the authorization URL that the client should redirect to.
   * On failure, emits an error matching {@link ApiError}.
   */
  startConnection(): Observable<StartConnectionResponse> {
    return this.http.post<StartConnectionResponse>(`${this.base}/accounting/connect`, {});
  }

  /**
   * Fetches current connection status.
   * Returns 404 if no connection has been created for the tenant.
   * On failure, emits an error matching {@link ApiError}.
   */
  getConnection(): Observable<AccountingConnection> {
    return this.http.get<AccountingConnection>(`${this.base}/accounting/connection`);
  }

  /**
   * Disconnects the active accounting connection.
   * On failure, emits an error matching {@link ApiError}.
   */
  disconnect(): Observable<AccountingConnection> {
    return this.http.post<AccountingConnection>(`${this.base}/accounting/disconnect`, {});
  }

  /**
   * Triggers an on-demand sync of bills and vendors with the connected accounting provider.
   * Emits HTTP 409 if a sync is already in progress, or 404 if no active connection exists.
   * On failure, emits an error matching {@link ApiError}.
   */
  triggerSync(): Observable<TriggerSyncResponse> {
    return this.http.post<TriggerSyncResponse>(`${this.base}/accounting/sync`, {});
  }

  /**
   * Lists synced bills with cursor pagination and optional match status filter.
   * Builds query parameters only for the ones actually provided.
   * On failure, emits an error matching {@link ApiError}.
   */
  listBills(params?: ListBillsParams): Observable<SyncedBillList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.match_status) query.set('match_status', params.match_status);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<SyncedBillList>(`${this.base}/accounting/bills${qs}`);
  }

  /**
   * Lists reconciliation discrepancies with cursor pagination and optional status filter.
   * When status is omitted, server defaults to 'open'.
   * On failure, emits an error matching {@link ApiError}.
   */
  listDiscrepancies(params?: ListDiscrepanciesParams): Observable<ReconciliationDiscrepancyList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ReconciliationDiscrepancyList>(`${this.base}/accounting/discrepancies${qs}`);
  }

  /**
   * Resolves a reconciliation discrepancy with an optional resolution note.
   * Emits HTTP 404 if not found or cross-tenant, or 409 if already resolved.
   * On failure, emits an error matching {@link ApiError}.
   */
  resolveDiscrepancy(
    discrepancyId: string,
    note?: string,
  ): Observable<ReconciliationDiscrepancy> {
    const body: ResolveDiscrepancyRequest = note !== undefined ? { note } : {};
    return this.http.post<ReconciliationDiscrepancy>(
      `${this.base}/accounting/discrepancies/${encodeURIComponent(discrepancyId)}/resolve`,
      body,
    );
  }
}
