import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type AnalystCategory =
  | 'spend_savings'
  | 'supplier_performance_risk'
  | 'orders_quotations'
  | 'reorder_forecasts';

export type CitationSourceKind =
  | 'purchase_order'
  | 'quotation_line'
  | 'landed_cost'
  | 'saving_record'
  | 'supplier_scorecard_snapshot'
  | 'delivery_receipt'
  | 'reorder_proposal';

export interface Money {
  amount: string;
  currency: string;
}

export interface CalculationDetail {
  inputs: Record<string, unknown>[];
  formula: string;
  result: Money | string | null;
}

export interface AnalystCitation {
  id: string;
  turn_id: string;
  source_kind: CitationSourceKind;
  source_id: string;
  created_at: string;
}

export interface AnalystTurn {
  id: string;
  conversation_id: string;
  creating_member_id: string;
  question_text: string;
  category: AnalystCategory;
  answer_text: string;
  calculation_version: string;
  release_posture: 'g3_unmet';
  calculation: CalculationDetail | null;
  citations: AnalystCitation[];
  next_step_url: string | null;
  created_at: string;
}

export interface AnalystConversation {
  id: string;
  tenant_id: string;
  creating_member_id: string;
  created_at: string;
  turns: AnalystTurn[];
}

export interface AnalystConversationList {
  items: AnalystConversation[];
  next_cursor: string | null;
}

@Injectable({ providedIn: 'root' })
export class AnalystApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  askQuestion(questionText: string, conversationId?: string): Observable<AnalystConversation> {
    const headers = new HttpHeaders({ 'Idempotency-Key': crypto.randomUUID() });
    const body: { question_text: string; conversation_id?: string } = {
      question_text: questionText,
    };
    if (conversationId) {
      body.conversation_id = conversationId;
    }
    return this.http.post<AnalystConversation>(`${this.base}/analyst/conversations`, body, {
      headers,
    });
  }
  listConversations(limit = 50, cursor?: string): Observable<AnalystConversationList> {
    const params: Record<string, string | number> = { limit };
    if (cursor) {
      params['cursor'] = cursor;
    }
    return this.http.get<AnalystConversationList>(`${this.base}/analyst/conversations`, { params });
  }

  getConversation(conversationId: string): Observable<AnalystConversation> {
    return this.http.get<AnalystConversation>(`${this.base}/analyst/conversations/${conversationId}`);
  }
}
