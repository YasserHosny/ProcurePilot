import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { ApiError } from '../../../core/api/models';
import {
  type BillingAccount,
  BillingApiService,
  type LimitCheck,
} from '../billing-api';

@Component({
  selector: 'app-plan-display',
  standalone: true,
  imports: [
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: './plan-display.component.html',
  styleUrl: './plan-display.component.scss',
})
export class PlanDisplayComponent implements OnInit {
  private readonly billingApi = inject(BillingApiService);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly billingAccount = signal<BillingAccount | null>(null);
  readonly limitCheck = signal<LimitCheck | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  ngOnInit(): void {
    this.loadBillingInfo();
  }

  loadBillingInfo(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.billingApi.getBillingAccount().subscribe({
      next: (account) => {
        this.billingAccount.set(account);
        this.loadLimitCheck();
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  private loadLimitCheck(): void {
    this.billingApi.checkActiveCatalogueProductsLimit().subscribe({
      next: (check) => {
        this.limitCheck.set(check);
        this.isLoading.set(false);
      },
      error: () => {
        // Non-fatal if limit check fails; continue showing plan
        this.isLoading.set(false);
      },
    });
  }

  continueToWorkspace(): void {
    void this.router.navigate(['/home']);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('onboarding.planDisplay.errorLoading'),
      );
      return;
    }
    if (err && typeof err === 'object' && 'error' in err) {
      const apiError = (err as { error?: ApiError }).error;
      if (apiError) {
        this.errorTraceId.set(apiError.trace_id ?? null);
        this.errorMessage.set(apiError.message ?? null);
        return;
      }
    }
    this.errorMessage.set(this.translate.instant('onboarding.planDisplay.errorLoading'));
  }
}
