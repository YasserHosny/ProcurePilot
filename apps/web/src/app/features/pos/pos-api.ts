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
}
