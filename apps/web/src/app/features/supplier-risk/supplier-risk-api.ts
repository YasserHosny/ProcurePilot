import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type SupplierRiskState = 'ready' | 'provisional' | 'insufficient_data';
export type SupplierRiskConfidence = 'high' | 'medium' | 'low';
export type SupplierRiskLevel = 'low' | 'medium' | 'high';
export type SupplierRiskReleasePosture = 'g3_unmet';
export type BriefItemKind =
  | 'price_trajectory'
  | 'alternatives'
  | 'service_performance'
  | 'concentration_volume'
  | 'payment_context'
  | 'purchase_pattern';
export type BriefStatus = 'prepared' | 'acknowledged' | 'dismissed';

export interface Money {
  amount: string;
  currency: string;
}

export interface SupplierRiskScore {
  total: string | null;
  components: Record<string, string | null>;
  weights: Record<string, string>;
}

export interface SupplierRiskSnapshot {
  id: string;
  supplier_id: string;
  supplier_name: string;
  window_start: string;
  window_end: string;
  state: SupplierRiskState;
  confidence: SupplierRiskConfidence;
  release_posture: SupplierRiskReleasePosture;
  valid_from: string;
  valid_until: string;
  source_fingerprint: string;
  observed_history_days: number;
  risk_score: SupplierRiskScore;
  risk_level: SupplierRiskLevel | null;
  computed_at: string;
}

export interface SupplierRiskList {
  items: SupplierRiskSnapshot[];
  next_cursor: string | null;
}

export interface SupplierRiskRecomputeResponse {
  generated_snapshots: number;
  release_posture: SupplierRiskReleasePosture;
}

export interface NegotiationBriefItem {
  kind: BriefItemKind;
  rank: number;
  value: string | null;
  amount: Money | null;
  confidence: SupplierRiskConfidence;
  risk: string | null;
  valid_from: string;
  valid_until: string;
  question_i18n_key: string;
  calculation_version: string;
  metric_id: string | null;
  evidence_ids: string[];
}

export interface NegotiationBrief {
  id: string;
  supplier_id: string;
  snapshot_id: string;
  brief_version: string;
  source_fingerprint: string;
  release_posture: SupplierRiskReleasePosture;
  valid_from: string;
  valid_until: string;
  status: BriefStatus;
  items: NegotiationBriefItem[];
}

export interface NegotiationBriefList {
  items: NegotiationBrief[];
  next_cursor: string | null;
}

@Injectable({ providedIn: 'root' })
export class SupplierRiskApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  listRisks(cursor?: string, limit = 50): Observable<SupplierRiskList> {
    const query = this.paginationQuery(cursor, limit);
    return this.http.get<SupplierRiskList>(`${this.base}/supplier-iq/risks${query}`);
  }

  recompute(): Observable<SupplierRiskRecomputeResponse> {
    return this.http.post<SupplierRiskRecomputeResponse>(
      `${this.base}/supplier-iq/recompute`,
      {},
      { headers: this.idempotencyHeaders() },
    );
  }

  prepareBrief(supplierId: string): Observable<NegotiationBrief> {
    return this.http.post<NegotiationBrief>(
      `${this.base}/suppliers/${encodeURIComponent(supplierId)}/negotiation-briefs`,
      {},
      { headers: this.idempotencyHeaders() },
    );
  }

  listBriefs(cursor?: string, limit = 50): Observable<NegotiationBriefList> {
    const query = this.paginationQuery(cursor, limit);
    return this.http.get<NegotiationBriefList>(`${this.base}/negotiation-briefs${query}`);
  }

  getBrief(briefId: string): Observable<NegotiationBrief> {
    return this.http.get<NegotiationBrief>(
      `${this.base}/negotiation-briefs/${encodeURIComponent(briefId)}`,
    );
  }

  acknowledgeBrief(briefId: string): Observable<NegotiationBrief> {
    return this.http.post<NegotiationBrief>(
      `${this.base}/negotiation-briefs/${encodeURIComponent(briefId)}/acknowledge`,
      {},
      { headers: this.idempotencyHeaders() },
    );
  }

  dismissBrief(briefId: string, reason: string): Observable<NegotiationBrief> {
    return this.http.post<NegotiationBrief>(
      `${this.base}/negotiation-briefs/${encodeURIComponent(briefId)}/dismiss`,
      { reason },
      { headers: this.idempotencyHeaders() },
    );
  }

  private paginationQuery(cursor: string | undefined, limit: number): string {
    const query = new URLSearchParams({ limit: String(Math.min(100, Math.max(1, limit))) });
    if (cursor) query.set('cursor', cursor);
    return `?${query.toString()}`;
  }

  private idempotencyHeaders(): HttpHeaders {
    return new HttpHeaders({ 'Idempotency-Key': crypto.randomUUID() });
  }
}
