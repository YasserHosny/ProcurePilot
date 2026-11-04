import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams, HttpErrorResponse } from '@angular/common/http';
import { Observable } from 'rxjs';

import type { QuotationStatus, BasketSplitJob } from '../../core/api/models';
import { environment } from '../../../environments/environment';

export interface Rfq {
  reference_number?: number;
  id: string;
  tenant_id: string;
  created_by_membership_id: string;
  status: 'draft' | 'sent' | 'responded' | 'expired' | 'converted' | 'cancelled';
  needed_by_date: string;
  tenant_terms: string | null;
  idempotency_key: string;
  created_at: string;
  sent_at?: string | null;
  cancelled_at?: string | null;
}

export interface RfqLine {
  id: string;
  tenant_id: string;
  rfq_id: string;
  workspace_product_id: string;
  quantity: number | string;
  created_at: string;
  position?: number;
  product_name?: string | null;
  product_variant?: string | null;
}

export interface RfqRecipient {
  failure_reason?: 'delivery_error' | 'missing_contact_email' | null;
  send_attempts?: number;
  last_attempt_at?: string | null;
  id: string;
  tenant_id: string;
  rfq_id: string;
  supplier_id: string;
  status: 'draft' | 'sent' | 'failed';
  outbound_message_id: string | null;
  sent_at: string | null;
  created_at: string;
  supplier_name?: string | null;
  supplier_contact_email?: string | null;
  response_count?: number;
}

export interface RfqDetail {
  rfq: Rfq;
  lines: RfqLine[];
  recipients: RfqRecipient[];
  converted_purchase_request_ids?: string[];
  request_group_id?: string | null;
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
  product_name?: string | null;
  product_variant?: string | null;
  workspace_product_id: string | null;
  original_text: string;
  quoted_quantity: string;
  quoted_unit_price_amount: string;
  quoted_unit_price_currency: string;
  pending_match: boolean;
}

export interface RfqLandedCost {
  product_name?: string | null;
  product_variant?: string | null;
  workspace_product_id: string;
  total_amount: string;
  total_currency: string;
}

export interface RfqResponseComparison {
  supplier_name?: string | null;
  id: string;
  rfq_id: string;
  supplier_id: string;
  quotation_id: string;
  submitted_at: string;
  quotation_status: QuotationStatus;
  lines: RfqResponseLineComparison[];
  guardrail_evaluations?: RfqGuardrailEvaluation[];
  /** Landed cost for the RFQ's requested quantity of each priced product. */
  rfq_landed_costs?: RfqLandedCost[];
  /** Supplier has delivery-fee / minimum-order / tier terms in force. */
  supplier_terms_apply?: boolean;
}

export interface RfqGuardrailEvaluation {
  guardrail_id: string;
  fired: boolean;
  reason: string;
  purchase_request_id?: string | null;
}

export interface RfqGuardrail {
  id: string;
  tenant_id: string;
  created_by_membership_id: string;
  max_order_value_amount: string;
  max_order_value_currency: string;
  supplier_allowlist: string[] | null;
  category_allowlist: string[] | null;
  min_response_count: number;
  max_price_variance_pct: string;
  enabled: boolean;
  default_branch_id: string;
  default_cost_centre_id?: string | null;
  created_at: string;
}

export interface RfqGuardrailPayload {
  max_order_value_amount: string;
  max_order_value_currency: string;
  supplier_allowlist: string[];
  min_response_count: number;
  max_price_variance_pct: string;
  default_branch_id: string;
  default_cost_centre_id: string | null;
  enabled: boolean;
}

export interface RfqResponseComparisonList {
  items: RfqResponseComparison[];
}

export interface RfqSummary {
  reference_number?: number;
  id: string;
  created_by_membership_id: string;
  status: 'draft' | 'sent' | 'responded' | 'expired' | 'converted' | 'cancelled';
  needed_by_date: string;
  created_at: string;
  sent_at: string | null;
  cancelled_at?: string | null;
  recipient_count: number;
  response_count: number;
  converted_purchase_request_id: string | null;
  converted_purchase_request_ids?: string[];
  request_group_id?: string | null;
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

  cancelRfq(rfqId: string, idempotencyKey?: string): Observable<Rfq> {
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey ?? crypto.randomUUID(),
    });
    return this.http.post<Rfq>(`${this.baseUrl}/${rfqId}/cancel`, null, { headers });
  }

  createRfq(payload: RfqCreatePayload, idempotencyKey?: string): Observable<RfqCreateResponse> {
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey ?? crypto.randomUUID(),
    });
    return this.http.post<RfqCreateResponse>(this.baseUrl, payload, { headers });
  }

  getRfq(rfqId: string): Observable<RfqDetail> {
    return this.http.get<RfqDetail>(`${this.baseUrl}/${rfqId}`);
  }

  updateRfq(rfqId: string, payload: RfqCreatePayload, idempotencyKey?: string): Observable<RfqCreateResponse> {
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey ?? crypto.randomUUID(),
    });
    return this.http.put<RfqCreateResponse>(`${this.baseUrl}/${rfqId}`, payload, { headers });
  }

  sendRfq(rfqId: string, idempotencyKey?: string): Observable<RfqSendResponse> {
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey ?? crypto.randomUUID(),
    });
    return this.http.post<RfqSendResponse>(`${this.baseUrl}/${rfqId}/send`, {}, { headers });
  }

  listResponses(rfqId: string): Observable<RfqResponseComparisonList> {
    return this.http.get<RfqResponseComparisonList>(`${this.baseUrl}/${rfqId}/responses`);
  }

  prepareRequest(rfqId: string, payload: PrepareRequestPayload, idempotencyKey?: string): Observable<PrepareRequestResponse> {
    const headers = new HttpHeaders({ 'Idempotency-Key': idempotencyKey ?? crypto.randomUUID() });
    return this.http.post<PrepareRequestResponse>(
      `${this.baseUrl}/${rfqId}/prepare-request`, payload, { headers },
    );
  }

  splitRfq(rfqId: string, idempotencyKey?: string): Observable<BasketSplitJob> {
    const headers = new HttpHeaders({
      'Idempotency-Key': idempotencyKey || crypto.randomUUID(),
    });
    return this.http.post<BasketSplitJob>(`${this.baseUrl}/${rfqId}/split`, {}, { headers });
  }

  listRfqs(status?: string, cursor?: string, limit?: number, q?: string, sort?: string): Observable<RfqList> {
    let params = new HttpParams();
    if (q?.trim()) params = params.set('q', q.trim());
    if (sort && sort !== 'created_desc') params = params.set('sort', sort);
    if (status) params = params.set('status', status);
    if (cursor) params = params.set('cursor', cursor);
    if (limit) params = params.set('limit', limit.toString());

    return this.http.get<RfqList>(this.baseUrl, { params });
  }

  listGuardrails(): Observable<RfqGuardrail[]> {
    return this.http.get<RfqGuardrail[]>(`${this.baseUrl}/guardrails`);
  }

  createGuardrail(payload: RfqGuardrailPayload): Observable<RfqGuardrail> {
    return this.http.post<RfqGuardrail>(`${this.baseUrl}/guardrails`, payload);
  }

  updateGuardrail(id: string, payload: Partial<RfqGuardrailPayload>): Observable<RfqGuardrail> {
    return this.http.patch<RfqGuardrail>(`${this.baseUrl}/guardrails/${id}`, payload);
  }
}

/**
 * Component-local keys survive ambiguous failures until the logical action resolves.
 *
 * A key is only reused for the payload it was created for: the server answers a repeated key with
 * the result it stored the first time and ignores a changed body, so an edited payload must start a
 * new operation. Pass a fingerprint of the request body (e.g. its JSON) for actions that have one.
 */
export class RfqActionKeys {
  private readonly keys = new Map<string, { key: string; fingerprint: string | undefined }>();

  get(action: string, fingerprint?: string): string {
    const current = this.keys.get(action);
    if (current && (fingerprint === undefined || current.fingerprint === fingerprint)) {
      return current.key;
    }
    const key = crypto.randomUUID();
    this.keys.set(action, { key, fingerprint });
    return key;
  }

  clear(action: string): void { this.keys.delete(action); }

  onError(action: string, error: unknown): void {
    // Timeouts and rate limits are retryable, like network and server failures.
    if (error instanceof HttpErrorResponse && error.status >= 400 && error.status < 500
      && error.status !== 408 && error.status !== 429) {
      this.clear(action);
    }
  }
}

/** Stable display identifier; older API deployments may omit the number. */
export function formatRfqReference(n: number | null | undefined): string {
  return n == null ? '' : `RFQ-${String(n).padStart(6, '0')}`;
}
