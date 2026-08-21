import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  BaselinePolicy,
  Money,
  PurchaseDeliveryResult,
  PurchaseOutcomeCreate,
  PurchaseOutcomeCreated,
  PurchaseRecord,
  SavingCalculationEvidence,
  SavingEvidence,
  SavingList,
  SavingRecord,
  SavingStatus,
} from '../../core/api/models';

export type {
  SavingStatus,
  BaselinePolicy,
  PurchaseDeliveryResult,
  PurchaseOutcomeCreate,
  PurchaseRecord,
  SavingRecord,
  PurchaseOutcomeCreated,
  SavingList,
  SavingCalculationEvidence,
  SavingEvidence,
  Money,
};

@Injectable({ providedIn: 'root' })
export class SavingsApiService {
  private readonly api = inject(ApiService);

  recordPurchase(
    body: PurchaseOutcomeCreate,
    idempotencyKey?: string,
  ): Observable<PurchaseOutcomeCreated> {
    return this.api.recordPurchase(body, idempotencyKey);
  }

  getSavings(params?: {
    status?: SavingStatus;
    period_start?: string;
    period_end?: string;
    supplier_id?: string;
    branch_id?: string | null;
    cursor?: string;
    limit?: number;
  }): Observable<SavingList> {
    return this.api.getSavings(params);
  }

  getSaving(id: string): Observable<SavingRecord> {
    return this.api.getSaving(id);
  }

  getSavingEvidence(id: string): Observable<SavingEvidence> {
    return this.api.getSavingEvidence(id);
  }

  verifySaving(id: string, idempotencyKey?: string): Observable<SavingRecord> {
    return this.api.verifySaving(id, idempotencyKey);
  }
}
