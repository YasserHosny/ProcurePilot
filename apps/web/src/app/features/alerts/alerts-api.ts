import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  Alert,
  AlertAction,
  AlertDismissal,
  AlertKind,
  AlertSeverity,
  ApiError,
} from '../../core/api/models';

export type { AlertKind, AlertSeverity, AlertAction, Alert, AlertDismissal, ApiError };

@Injectable({ providedIn: 'root' })
export class AlertsApiService {
  private readonly api = inject(ApiService);

  getAlerts(params?: {
    kind?: AlertKind;
    cursor?: string;
    limit?: number;
  }): Observable<{ items: Alert[]; next_cursor: string | null }> {
    return this.api.getAlerts(params);
  }

  dismissAlert(id: string, idempotencyKey?: string): Observable<AlertDismissal> {
    return this.api.dismissAlert(id, idempotencyKey);
  }
}
