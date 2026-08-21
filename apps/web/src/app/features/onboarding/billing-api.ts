import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  BillingAccount,
  LimitCheck,
  Money,
  Plan,
  PlanLimits,
} from '../../core/api/models';

export type {
  PlanLimits,
  Plan,
  BillingAccount,
  LimitCheck,
  Money,
};

@Injectable({ providedIn: 'root' })
export class BillingApiService {
  private readonly api = inject(ApiService);

  getBillingAccount(): Observable<BillingAccount> {
    return this.api.getBillingAccount();
  }

  checkActiveCatalogueProductsLimit(): Observable<LimitCheck> {
    return this.api.checkActiveCatalogueProductsLimit();
  }
}
