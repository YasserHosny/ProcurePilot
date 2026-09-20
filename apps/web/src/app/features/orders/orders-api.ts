import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type OrderStatus =
  | 'draft'
  | 'submitted'
  | 'confirmed'
  | 'partially_received'
  | 'received'
  | 'cancelled'
  | 'closed';
export type EvidenceState = 'pending' | 'available' | 'unavailable';

export interface Money {
  amount: string;
  currency: string;
}

export interface PurchaseOrderLine {
  id: string;
  line_number: number;
  workspace_product_id: string | null;
  description: string;
  ordered_quantity: string;
  base_unit: string;
  unit_price: Money;
  tax: Money;
  line_total: Money;
}

export interface PurchaseOrder {
  id: string;
  tenant_id: string;
  order_number: string;
  supplier_id: string;
  status: OrderStatus;
  order_date: string;
  expected_delivery_date: string | null;
  total: Money;
  tax: Money;
  source_kind: 'manual' | 'import' | 'provider';
  source_reference: string;
  source_hash: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  lines: PurchaseOrderLine[];
}

export interface SupplierConfirmationLine {
  id: string;
  purchase_order_line_id: string;
  confirmed_quantity: string;
  confirmed_unit_price: Money | null;
}

export interface SupplierConfirmation {
  id: string;
  tenant_id: string;
  purchase_order_id: string;
  supplier_reference: string;
  confirmed_at: string;
  expected_delivery_date: string | null;
  source_kind: 'manual' | 'import' | 'provider';
  source_reference: string;
  source_hash: string | null;
  recorded_by: string;
  created_at: string;
  lines: SupplierConfirmationLine[];
}

export interface DeliveryReceiptLine {
  id: string;
  purchase_order_line_id: string;
  received_quantity: string;
}

export interface DeliveryReceipt {
  id: string;
  tenant_id: string;
  purchase_order_id: string;
  receipt_reference: string;
  receipt_date: string;
  received_by: string;
  source_kind: 'manual' | 'import' | 'provider';
  source_reference: string;
  source_hash: string | null;
  created_at: string;
  lines: DeliveryReceiptLine[];
}

export interface EvidenceProjection {
  state: EvidenceState;
  quantity: string | null;
  source_ids: string[];
}

export interface LifecycleLineSummary {
  purchase_order_line_id: string;
  ordered_quantity: string;
  confirmed: EvidenceProjection;
  received: EvidenceProjection;
  remaining_quantity: string | null;
  over_received_quantity: string | null;
}

export interface LifecycleSummary {
  purchase_order_id: string;
  status: OrderStatus;
  confirmation: EvidenceState;
  receipt: EvidenceState;
  lines: LifecycleLineSummary[];
}

export interface OrderEvidenceProjection {
  order: PurchaseOrder;
  confirmation: SupplierConfirmation | null;
  receipts: DeliveryReceipt[];
  lifecycle: LifecycleSummary;
}

export interface PurchaseOrderList {
  items: PurchaseOrder[];
  next_cursor: string | null;
}

export interface SupplierConfirmationCreate {
  supplier_reference: string;
  confirmed_at: string;
  expected_delivery_date: string | null;
  source_kind: 'manual';
  source_reference: string;
  lines: {
    purchase_order_line_id: string;
    confirmed_quantity: string;
    confirmed_unit_price: Money | null;
  }[];
}

export interface DeliveryReceiptCreate {
  receipt_reference: string;
  receipt_date: string;
  source_kind: 'manual';
  source_reference: string;
  lines: {
    purchase_order_line_id: string;
    received_quantity: string;
  }[];
}

@Injectable({ providedIn: 'root' })
export class OrdersApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  listOrders(cursor?: string): Observable<PurchaseOrderList> {
    const query = new URLSearchParams({ limit: '50' });
    if (cursor) query.set('cursor', cursor);
    return this.http.get<PurchaseOrderList>(`${this.base}/orders?${query.toString()}`);
  }

  getOrder(orderId: string): Observable<OrderEvidenceProjection> {
    return this.http.get<OrderEvidenceProjection>(
      `${this.base}/orders/${encodeURIComponent(orderId)}`,
    );
  }

  submitOrder(orderId: string): Observable<PurchaseOrder> {
    return this.http.post<PurchaseOrder>(
      `${this.base}/orders/${encodeURIComponent(orderId)}/submit`,
      {},
      { headers: this.idempotencyHeaders() },
    );
  }

  recordConfirmation(
    orderId: string,
    payload: SupplierConfirmationCreate,
  ): Observable<OrderEvidenceProjection> {
    return this.http.post<OrderEvidenceProjection>(
      `${this.base}/orders/${encodeURIComponent(orderId)}/confirmations`,
      payload,
      { headers: this.idempotencyHeaders() },
    );
  }

  recordReceipt(orderId: string, payload: DeliveryReceiptCreate): Observable<OrderEvidenceProjection> {
    return this.http.post<OrderEvidenceProjection>(
      `${this.base}/orders/${encodeURIComponent(orderId)}/receipts`,
      payload,
      { headers: this.idempotencyHeaders() },
    );
  }

  private idempotencyHeaders(): HttpHeaders {
    return new HttpHeaders({ 'Idempotency-Key': crypto.randomUUID() });
  }
}
