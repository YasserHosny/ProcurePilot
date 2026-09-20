import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type ForecastState = 'ready' | 'provisional' | 'insufficient_data';
export type ForecastConfidence = 'high' | 'medium' | 'low';
export type ProposalStatus = 'open' | 'prepared' | 'dismissed' | 'expired';

export interface ReorderProposal {
  id: string;
  demand_forecast_id: string;
  workspace_product_id: string;
  product_name: string;
  status: ProposalStatus;
  horizon_days: number;
  source_window_start: string;
  source_window_end: string;
  observed_history_days: number | null;
  expected_daily_demand: string | null;
  expected_demand: string | null;
  uncertainty_lower: string | null;
  uncertainty_upper: string | null;
  stock_on_hand: string | null;
  suggested_quantity: string | null;
  confidence: ForecastConfidence;
  state: ForecastState;
  release_posture: 'g3_unmet';
  valid_from: string;
  valid_until: string;
  purchase_request_id: string | null;
  prepared_branch_id: string | null;
  created_at: string;
}

export interface ReorderProposalList {
  items: ReorderProposal[];
  next_cursor: string | null;
}

export interface RecomputeResponse {
  generated_forecasts: number;
  open_proposals: number;
  release_posture: 'g3_unmet';
}

export interface PrepareRequestInput {
  branch_id: string;
  required_by_date: string;
  cost_centre_id?: string | null;
}

export interface PrepareRequestResponse {
  proposal: ReorderProposal;
  purchase_request_id: string;
}

@Injectable({ providedIn: 'root' })
export class ForecastingApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  recompute(): Observable<RecomputeResponse> {
    return this.http.post<RecomputeResponse>(`${this.base}/forecasting/recompute`, {});
  }

  listProposals(params?: { cursor?: string; limit?: number }): Observable<ReorderProposalList> {
    const query = new URLSearchParams();
    if (params?.cursor) query.set('cursor', params.cursor);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.http.get<ReorderProposalList>(
      `${this.base}/forecasting/reorder-proposals${qs}`,
    );
  }

  prepareRequest(
    proposalId: string,
    body: PrepareRequestInput,
  ): Observable<PrepareRequestResponse> {
    return this.http.post<PrepareRequestResponse>(
      `${this.base}/forecasting/reorder-proposals/${encodeURIComponent(proposalId)}/prepare-request`,
      body,
    );
  }
}
