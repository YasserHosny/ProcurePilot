import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../../environments/environment';

export type DigestChannel = 'in_app' | 'email';
export type DigestStatus = 'active' | 'paused';
export type DeliveryStatus = 'succeeded' | 'failed' | 'email_unconfigured';

export type DigestSectionKind =
  | 'verified_savings'
  | 'pending_verifications'
  | 'pending_approvals'
  | 'anomalies'
  | 'expiring_validity';

export interface DigestMoney {
  amount: number;
  currency: string;
}

export interface DigestItem {
  label: string;
  money?: DigestMoney | null;
  evidence_ref?: string | null;
  deep_link: string;
}

export interface DigestSection {
  kind: DigestSectionKind;
  items: DigestItem[];
}

export interface DigestView {
  subscription_id: string;
  period_start: string;
  period_end: string;
  sections: DigestSection[];
  rendered_at: string;
  delivery_status: DeliveryStatus;
}

export interface DigestFilters {
  branch_id?: string | null;
}

export interface DigestSubscription {
  id: string;
  kind: 'weekly_digest';
  filters: DigestFilters;
  channel: DigestChannel;
  status: DigestStatus;
  locale: 'en' | 'ar';
  next_run_at: string;
  last_delivery_at?: string | null;
  last_delivery_status?: DeliveryStatus | null;
  email_configured: boolean;
  created_at: string;
  updated_at: string;
}

export interface DigestSubscriptionList {
  items: DigestSubscription[];
  next_cursor: string | null;
}

@Injectable({ providedIn: 'root' })
export class DigestsApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  getSubscriptions(params?: {
    cursor?: string;
    limit?: number;
  }): Observable<DigestSubscriptionList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<DigestSubscriptionList>(`${this.base}/digests/subscriptions${qs}`);
  }

  createSubscription(payload: {
    filters?: DigestFilters;
    locale?: 'en' | 'ar';
    channel?: DigestChannel;
  }): Observable<DigestSubscription> {
    return this.http.post<DigestSubscription>(`${this.base}/digests/subscriptions`, payload);
  }

  updateSubscription(
    id: string,
    payload: {
      filters?: DigestFilters;
      locale?: 'en' | 'ar';
      channel?: DigestChannel;
      status?: DigestStatus;
    }
  ): Observable<DigestSubscription> {
    return this.http.patch<DigestSubscription>(
      `${this.base}/digests/subscriptions/${id}`,
      payload
    );
  }

  deleteSubscription(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/digests/subscriptions/${id}`);
  }

  getLatestDigest(): Observable<DigestView> {
    return this.http.get<DigestView>(`${this.base}/digests/latest`);
  }
}
