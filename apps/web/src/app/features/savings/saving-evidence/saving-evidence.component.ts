import { DecimalPipe, NgClass, NgIf, NgFor } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import {
  type SavingEvidence,
  SavingsApiService,
} from '../savings-api';
import {
  getBaselinePolicyClass,
  getDeliveryResultClass,
  getDeltaClass,
  getSavingStatusClass,
  isNegativeSaving,
  isPositiveSaving,
} from '../savings-formatting';

@Component({
  selector: 'app-saving-evidence',
  standalone: true,
  imports: [
    NgIf,
    NgFor,
    NgClass,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    DecimalPipe,
    RoleDirective,
  ],
  templateUrl: './saving-evidence.component.html',
  styleUrl: './saving-evidence.component.scss',
})
export class SavingEvidenceComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly savingsApi = inject(SavingsApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isVerifying = signal<boolean>(false);
  readonly savingEvidence = signal<SavingEvidence | null>(null);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly isVerified = computed<boolean>(() => {
    return this.savingEvidence()?.saving_record.status === 'verified';
  });

  readonly competingOffersColumns = ['supplier', 'unitPrice', 'landedCost', 'leadTime', 'reliability'];

  ngOnInit(): void {
    this.loadReferenceData();
    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (id) {
        this.fetchEvidence(id);
      }
    });
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

  fetchEvidence(id: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.savingsApi.getSavingEvidence(id).subscribe({
      next: (evidence) => {
        this.savingEvidence.set(evidence);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  onVerify(): void {
    const evidence = this.savingEvidence();
    if (!evidence || evidence.saving_record.status === 'verified' || !this.isWriter()) return;

    this.isVerifying.set(true);
    const savingId = evidence.saving_record.id;

    this.savingsApi.verifySaving(savingId).subscribe({
      next: (updatedSaving) => {
        this.isVerifying.set(false);
        this.savingEvidence.update((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            saving_record: { ...updatedSaving },
          };
        });
        this.snackBar.open(
          this.translate.instant('savings.evidence.verifySuccess'),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isVerifying.set(false);
        this.handleError(err);
      },
    });
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

  getStatusClass(status: SavingEvidence['saving_record']['status']): string {
    return getSavingStatusClass(status);
  }

  getDeltaClass(delta: SavingEvidence['saving_record']['delta']): string {
    return getDeltaClass(delta);
  }

  getPolicyClass(policy: SavingEvidence['saving_record']['baseline_policy']): string {
    return getBaselinePolicyClass(policy);
  }

  getDeliveryClass(result: SavingEvidence['purchase_record']['delivery_result']): string {
    return getDeliveryResultClass(result);
  }

  isPositive(delta: SavingEvidence['saving_record']['delta']): boolean {
    return isPositiveSaving(delta);
  }

  isNegative(delta: SavingEvidence['saving_record']['delta']): boolean {
    return isNegativeSaving(delta);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(apiError?.message ?? err.message);
      return;
    }
    this.errorMessage.set(this.translate.instant('savings.ledger.empty.message'));
  }
}
