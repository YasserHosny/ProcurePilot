import { DecimalPipe, NgClass, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import {
  type SavingRecord,
  type SavingStatus,
  SavingsApiService,
} from '../savings-api';
import {
  getBaselinePolicyClass,
  getDeltaClass,
  getSavingStatusClass,
  isNegativeSaving,
  isPositiveSaving,
} from '../savings-formatting';

@Component({
  selector: 'app-savings-ledger',
  standalone: true,
  imports: [
    FormsModule,
    NgIf,
    NgClass,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    DecimalPipe,
    RoleDirective,
  ],
  templateUrl: './savings-ledger.component.html',
  styleUrl: './savings-ledger.component.scss',
})
export class SavingsLedgerComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly savingsApi = inject(SavingsApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly savings = signal<SavingRecord[]>([]);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly statusFilter = signal<SavingStatus | 'all'>('all');
  readonly selectedSupplierId = signal<string>('');
  readonly periodStartDate = signal<Date | null>(null);
  readonly periodEndDate = signal<Date | null>(null);

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly displayedColumns: readonly string[] = [
    'product',
    'supplier',
    'baseline',
    'actual',
    'delta',
    'status',
    'recordedAt',
    'actions',
  ];

  readonly verifiedSavingsCount = computed<number>(() => {
    return this.savings().filter((s) => s.status === 'verified').length;
  });

  readonly pendingSavingsCount = computed<number>(() => {
    return this.savings().filter((s) => s.status === 'pending').length;
  });

  readonly totalVerifiedAmount = computed<{ amount: string; currency: string } | null>(() => {
    const verified = this.savings().filter((s) => s.status === 'verified' && s.delta);
    if (verified.length === 0) return null;
    let sum = 0;
    const curr = verified[0].delta!.currency;
    for (const row of verified) {
      if (row.delta && row.delta.currency === curr) {
        sum += parseFloat(row.delta.amount);
      }
    }
    return { amount: sum.toFixed(2), currency: curr };
  });

  ngOnInit(): void {
    this.loadReferenceData();
    this.loadSavings();
  }

  private loadReferenceData(): void {
    this.api.products({ limit: 100, status: 'all' }).subscribe({
      next: (res) => this.products.set(res.items),
      error: () => undefined,
    });

    this.api.suppliers({ limit: 100, status: 'all' }).subscribe({
      next: (res) => this.suppliers.set(res.items),
      error: () => undefined,
    });
  }

  loadSavings(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const statusParam = this.statusFilter() === 'all' ? undefined : (this.statusFilter() as SavingStatus);
    const supplierParam = this.selectedSupplierId() || undefined;
    const startParam = this.periodStartDate()
      ? this.periodStartDate()!.toISOString().split('T')[0]
      : undefined;
    const endParam = this.periodEndDate()
      ? this.periodEndDate()!.toISOString().split('T')[0]
      : undefined;

    this.savingsApi
      .getSavings({
        status: statusParam,
        supplier_id: supplierParam,
        period_start: startParam,
        period_end: endParam,
        limit: 100,
      })
      .subscribe({
        next: (res) => {
          this.savings.set([...res.items]);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
  }

  onFilterChange(): void {
    this.loadSavings();
  }

  clearFilters(): void {
    this.statusFilter.set('all');
    this.selectedSupplierId.set('');
    this.periodStartDate.set(null);
    this.periodEndDate.set(null);
    this.loadSavings();
  }

  getProductName(productId: string): string {
    const p = this.products().find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }

  getSupplierName(supplierId?: string | null): string {
    if (!supplierId) return '—';
    const s = this.suppliers().find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getStatusClass(status: SavingStatus): string {
    return getSavingStatusClass(status);
  }

  getDeltaClass(delta: SavingRecord['delta']): string {
    return getDeltaClass(delta);
  }

  getPolicyClass(policy: SavingRecord['baseline_policy']): string {
    return getBaselinePolicyClass(policy);
  }

  isPositive(delta: SavingRecord['delta']): boolean {
    return isPositiveSaving(delta);
  }

  isNegative(delta: SavingRecord['delta']): boolean {
    return isNegativeSaving(delta);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(apiError?.message ?? err.message);
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
    this.errorMessage.set(this.translate.instant('savings.ledger.empty.message'));
  }
}
