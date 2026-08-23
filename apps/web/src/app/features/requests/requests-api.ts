import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  ApprovalDecisionInput,
  PurchaseRequest,
  PurchaseRequestCreate,
  PurchaseRequestList,
  PurchaseRequestStatus,
  PurchaseRequestUpdate,
} from '../../core/api/models';

export type {
  ApprovalDecisionInput,
  PurchaseRequest,
  PurchaseRequestCreate,
  PurchaseRequestList,
  PurchaseRequestStatus,
  PurchaseRequestUpdate,
};

@Injectable({ providedIn: 'root' })
export class RequestsApiService {
  private readonly api = inject(ApiService);

  listRequests(params?: {
    status?: PurchaseRequestStatus;
    branch_id?: string;
    cursor?: string;
    limit?: number;
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

  withdrawRequest(requestId: string): Observable<PurchaseRequest> {
    return this.api.withdrawRequest(requestId);
  }

  approveRequest(requestId: string, body: ApprovalDecisionInput): Observable<PurchaseRequest> {
    return this.api.approveRequest(requestId, body);
  }

  rejectRequest(requestId: string, body: ApprovalDecisionInput): Observable<PurchaseRequest> {
    return this.api.rejectRequest(requestId, body);
  }
}
