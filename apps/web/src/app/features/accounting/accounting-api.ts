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
}
