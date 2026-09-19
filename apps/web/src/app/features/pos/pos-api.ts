import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { ApiError } from '../../core/api/models';

export type { ApiError };

export type PosProvider = 'square';

export type PosConnectionStatus = 'active' | 'needs_reauth' | 'disconnected';

export interface PosConnection {
  id: string;
  provider: 'square';
  display_name: string;
  status: 'active' | 'needs_reauth' | 'disconnected';
  connected_at: string;
  last_synced_at: string | null;
  disconnected_at: string | null;
}

export interface StartConnectionResponse {
  authorization_url: string;
}

export interface TriggerSyncResponse {
  status: 'enqueued';
}

export interface SyncedProductSignal {
  id: string;
  external_item_name: string;
  matched: boolean;
  matched_workspace_product_id: string | null;
  stock_on_hand: string | null;
  stock_synced_at: string | null;
  sales_velocity_per_day: string | null;
  velocity_window_days: number;
  velocity_window_days_observed?: number | null;
  velocity_computed_at: string | null;
}

export interface SyncedProductSignalList {
  items: SyncedProductSignal[];
  next_cursor: string | null;
}

export interface PosProductMatch {
  id: string;
  synced_product_signal_id: string;
  workspace_product_id: string;
  match_method: 'automatic' | 'manual';
  matched_at: string;
}

export interface ManualMatchRequest {
  workspace_product_id: string;
}

export interface ListSignalsParams {
  cursor?: string;
  limit?: number;
  matchStatus?: 'matched' | 'unmatched';
  match_status?: 'matched' | 'unmatched';
  workspaceProductId?: string;
  workspace_product_id?: string;
}

@Injectable({ providedIn: 'root' })
export class PosApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  /**
   * Starts the Square OAuth authorization flow.
   * Returns the authorization URL that the client should redirect to.
   * On failure, emits an error matching {@link ApiError}.
   */
  startConnection(): Observable<StartConnectionResponse> {
    return this.http.post<StartConnectionResponse>(`${this.base}/pos/connect`, {});
  }

  /**
   * Alias for startConnection() per T014 requirements.
   */
  connect(): Observable<StartConnectionResponse> {
    return this.startConnection();
  }

  /**
   * Fetches current connection status.
   * Returns 404 if no connection has been created for the tenant.
   * On failure, emits an error matching {@link ApiError}.
   */
  getConnection(): Observable<PosConnection> {
    return this.http.get<PosConnection>(`${this.base}/pos/connection`);
  }

  /**
   * Disconnects the active POS connection.
   * On failure, emits an error matching {@link ApiError}.
   */
  disconnect(): Observable<PosConnection> {
    return this.http.post<PosConnection>(`${this.base}/pos/disconnect`, {});
  }

  /**
   * Triggers an on-demand sync of sales transactions and inventory levels.
   * Emits HTTP 409 if a sync is already in progress, or 404 if no active connection exists.
   * On failure, emits an error matching {@link ApiError}.
   */
  triggerSync(): Observable<TriggerSyncResponse> {
    return this.http.post<TriggerSyncResponse>(`${this.base}/pos/sync`, {});
  }

  /**
   * Lists synced product signals with cursor pagination and optional filters.
   * On failure, emits an error matching {@link ApiError}.
   */
  listSignals(params?: ListSignalsParams): Observable<SyncedProductSignalList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const matchStatus = params?.matchStatus ?? params?.match_status;
    if (matchStatus) query.set('match_status', matchStatus);
    const wpId = params?.workspaceProductId ?? params?.workspace_product_id;
    if (wpId) query.set('workspace_product_id', wpId);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<SyncedProductSignalList>(`${this.base}/pos/signals${qs}`);
  }

  /**
   * Manually links an unmatched signal to a workspace product.
   * Emits HTTP 404 if not found or cross-tenant, or 409 if signal or product is already matched.
   * On failure, emits an error matching {@link ApiError}.
   */
  manuallyMatchSignal(
    signalId: string,
    workspaceProductId: string,
  ): Observable<PosProductMatch> {
    const body: ManualMatchRequest = { workspace_product_id: workspaceProductId };
    return this.http.post<PosProductMatch>(
      `${this.base}/pos/signals/${encodeURIComponent(signalId)}/match`,
      body,
    );
  }
}
