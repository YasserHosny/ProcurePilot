import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface Rfq {
  id: string;
  tenant_id: string;
  created_by_membership_id: string;
  status: 'draft' | 'sent' | 'responded' | 'expired' | 'converted';
  needed_by_date: string;
  idempotency_key: string;
  created_at: string;
}

export interface RfqLine {
  id: string;
  tenant_id: string;
  rfq_id: string;
  workspace_product_id: string;
  quantity: number | string;
  created_at: string;
}

export interface RfqRecipient {
  id: string;
  tenant_id: string;
  rfq_id: string;
  supplier_id: string;
  status: 'draft' | 'sent' | 'failed';
  outbound_message_id: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface RfqCreatePayload {
  lines: { workspace_product_id: string; quantity: string }[];
  recipient_supplier_ids: string[];
  needed_by_date: string;
  tenant_terms?: string;
}

export interface RfqCreateResponse {
  rfq: Rfq;
  lines: RfqLine[];
  recipients: RfqRecipient[];
  rejected_recipients: { supplier_id: string; reason: string }[];
}

export interface RfqSendResponse {
  rfq: Rfq;
  recipients: RfqRecipient[];
}

export interface RfqResponseLineComparison {
  workspace_product_id: string | null;
  quoted_quantity: string;
  quoted_unit_price_amount: string;
  quoted_unit_price_currency: string;
  pending_match: boolean;
}

export interface RfqResponseComparison {
  id: string;
  rfq_id: string;
  supplier_id: string;
  submitted_at: string;
  lines: RfqResponseLineComparison[];
}

export interface RfqResponseComparisonList {
  items: RfqResponseComparison[];
}

export interface RfqSummary {
  id: string;
  status: 'draft' | 'sent' | 'responded' | 'expired' | 'converted';
  needed_by_date: string;
  created_at: string;
  recipient_count: number;
  response_count: number;
  converted_purchase_request_id: string | null;
}

export interface RfqList {
  items: RfqSummary[];
  next_cursor: string | null;
}

export interface PrepareRequestPayload {
  rfq_response_id: string;
  branch_id: string;
  cost_centre_id?: string;
  required_by_date: string;
}

export interface PrepareRequestResponse {
  purchase_request_id: string;
}

@Injectable({
  providedIn: 'root',
})
export class RfqApi {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/rfq`;

  createRfq(payload: RfqCreatePayload): Observable<RfqCreateResponse> {
    const headers = new HttpHeaders({
      'Idempotency-Key': crypto.randomUUID(),
    });
    return this.http.post<RfqCreateResponse>(this.baseUrl, payload, { headers });
  }

  sendRfq(rfqId: string): Observable<RfqSendResponse> {
    const headers = new HttpHeaders({
      'Idempotency-Key': crypto.randomUUID(),
    });
    return this.http.post<RfqSendResponse>(`${this.baseUrl}/${rfqId}/send`, {}, { headers });
  }

  listResponses(rfqId: string): Observable<RfqResponseComparisonList> {
    return this.http.get<RfqResponseComparisonList>(`${this.baseUrl}/${rfqId}/responses`);
  }

  prepareRequest(rfqId: string, payload: PrepareRequestPayload): Observable<PrepareRequestResponse> {
    const headers = new HttpHeaders({ 'Idempotency-Key': crypto.randomUUID() });
    return this.http.post<PrepareRequestResponse>(
      `${this.baseUrl}/${rfqId}/prepare-request`, payload, { headers },
    );
  }

  listRfqs(status?: string, cursor?: string, limit?: number): Observable<RfqList> {
    let params = new HttpParams();
    if (status) params = params.set('status', status);
    if (cursor) params = params.set('cursor', cursor);
    if (limit) params = params.set('limit', limit.toString());

    return this.http.get<RfqList>(this.baseUrl, { params });
  }
}
