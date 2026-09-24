import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
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
}
