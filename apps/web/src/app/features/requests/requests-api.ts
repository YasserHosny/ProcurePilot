import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  ApprovalDecisionInput,
  PurchaseRequest,
  PurchaseRequestLine,
  PurchaseRequestCreate,
  PurchaseRequestList,
  PurchaseRequestStatus,
  PurchaseRequestUpdate,
  RequestGroupSummary,
  RequestSource,
} from '../../core/api/models';

export type { PurchaseRequestStatus };

export type PurchaseRequestSort =
  | 'created_desc'
  | 'created_asc'
  | 'required_by_asc'
  | 'required_by_desc'
  | 'total_desc'
  | 'total_asc';

export type {
  ApprovalDecisionInput,
  PurchaseRequest,
  PurchaseRequestLine,
  PurchaseRequestCreate,
  PurchaseRequestList,
  PurchaseRequestUpdate,
  RequestGroupSummary,
  RequestSource,
};

@Injectable({ providedIn: 'root' })
export class RequestsApiService {
  private readonly api = inject(ApiService);

  listRequests(params?: {
    status?: PurchaseRequestStatus;
    branch_id?: string;
    cursor?: string;
    limit?: number;
    eligible_for_order?: boolean;
    q?: string;
    sort?: PurchaseRequestSort;
    mine?: boolean;
  }): Observable<PurchaseRequestList> {
    return this.api.listRequests(params);
  }

  getRequest(requestId: string): Observable<PurchaseRequest> {
    return this.api.getRequest(requestId);
  }

  createRequest(
    body: PurchaseRequestCreate,
    idempotencyKey?: string,
  ): Observable<PurchaseRequest> {
    return this.api.createRequest(body, idempotencyKey);
  }

  updateRequest(requestId: string, body: PurchaseRequestUpdate): Observable<PurchaseRequest> {
    return this.api.updateRequest(requestId, body);
  }

  submitRequest(requestId: string, idempotencyKey?: string): Observable<PurchaseRequest> {
    return this.api.submitRequest(requestId, idempotencyKey);
  }

  withdrawRequest(requestId: string, idempotencyKey?: string): Observable<PurchaseRequest> {
    return this.api.withdrawRequest(requestId, idempotencyKey);
  }

  approveRequest(requestId: string, body: ApprovalDecisionInput, idempotencyKey?: string): Observable<PurchaseRequest> {
    return this.api.approveRequest(requestId, body, idempotencyKey);
  }

  rejectRequest(requestId: string, body: ApprovalDecisionInput, idempotencyKey?: string): Observable<PurchaseRequest> {
    return this.api.rejectRequest(requestId, body, idempotencyKey);
  }

  submitGroup(groupId: string, idempotencyKey?: string): Observable<PurchaseRequest[]> {
    return this.api.submitGroup(groupId, idempotencyKey);
  }

  approveGroup(
    groupId: string,
    body?: ApprovalDecisionInput,
    idempotencyKey?: string,
  ): Observable<PurchaseRequest[]> {
    return this.api.approveGroup(groupId, body, idempotencyKey);
  }

  rejectGroup(
    groupId: string,
    body: ApprovalDecisionInput,
    idempotencyKey?: string,
  ): Observable<PurchaseRequest[]> {
    return this.api.rejectGroup(groupId, body, idempotencyKey);
  }

  withdrawGroup(groupId: string, idempotencyKey?: string): Observable<PurchaseRequest[]> {
    return this.api.withdrawGroup(groupId, idempotencyKey);
  }
}
