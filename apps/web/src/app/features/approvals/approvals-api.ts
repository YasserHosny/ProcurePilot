import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  ApprovalDelegation,
  ApprovalDelegationCreate,
  ApprovalDelegationList,
  PurchaseRequestList,
  ThresholdRule,
  ThresholdRuleCreate,
  ThresholdRuleList,
  ThresholdRuleUpdate,
} from '../../core/api/models';

export type {
  ApprovalDelegation,
  ApprovalDelegationCreate,
  ApprovalDelegationList,
  ThresholdRule,
  ThresholdRuleCreate,
  ThresholdRuleList,
  ThresholdRuleUpdate,
};

@Injectable({ providedIn: 'root' })
export class ApprovalsApiService {
  private readonly api = inject(ApiService);

  listPendingApprovals(params?: {
    cursor?: string;
    limit?: number;
  }): Observable<PurchaseRequestList> {
    return this.api.listPendingApprovals(params);
  }

  listThresholdRules(params?: { cursor?: string; limit?: number }): Observable<ThresholdRuleList> {
    return this.api.listThresholdRules(params);
  }

  createThresholdRule(
    body: ThresholdRuleCreate,
    idempotencyKey?: string,
  ): Observable<ThresholdRule> {
    return this.api.createThresholdRule(body, idempotencyKey);
  }

  updateThresholdRule(ruleId: string, body: ThresholdRuleUpdate): Observable<ThresholdRule> {
    return this.api.updateThresholdRule(ruleId, body);
  }

  deleteThresholdRule(ruleId: string): Observable<void> {
    return this.api.deleteThresholdRule(ruleId);
  }

  listApprovalDelegations(params?: {
    membership_id?: string;
  }): Observable<ApprovalDelegationList> {
    return this.api.listApprovalDelegations(params);
  }

  createApprovalDelegation(
    body: ApprovalDelegationCreate,
    idempotencyKey?: string,
  ): Observable<ApprovalDelegation> {
    return this.api.createApprovalDelegation(body, idempotencyKey);
  }

  cancelApprovalDelegation(delegationId: string): Observable<void> {
    return this.api.cancelApprovalDelegation(delegationId);
  }
}
