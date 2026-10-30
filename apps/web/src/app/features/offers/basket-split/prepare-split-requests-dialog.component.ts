import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin } from 'rxjs';

import type { Branch, CostCentre, PurchaseRequest, SplitPrepareRequest, Supplier } from '../../../core/api/models';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { OffersApiService } from '../offers-api';
import { RequestsApiService } from '../../requests/requests-api';

export interface PrepareSplitRequestsDialogData {
  readonly basketId: string;
  readonly rfqId: string;
  readonly rfqNeededByDate?: string | null;
  readonly suppliers?: readonly Supplier[];
  readonly branchId?: string | null;
}

export interface PrepareSplitRequestsDialogResult {
  readonly success?: boolean;
  readonly requests?: PurchaseRequest[];
  readonly requestIds?: string[];
  readonly stale?: boolean;
  readonly rfqAlreadyConverted?: boolean;
  readonly purchaseRequestIds?: string[];
  readonly error?: string;
}

export const LAST_BRANCH_STORAGE_PREFIX = 'pp.rfq.lastBranchId.';

@Component({
  selector: 'app-prepare-split-requests-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './prepare-split-requests-dialog.component.html',
  styleUrl: './prepare-split-requests-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class PrepareSplitRequestsDialogComponent implements OnInit {
  readonly fb = inject(FormBuilder);
  readonly dialogRef = inject(MatDialogRef<PrepareSplitRequestsDialogComponent, PrepareSplitRequestsDialogResult>);
  readonly data: PrepareSplitRequestsDialogData = inject(MAT_DIALOG_DATA);
  readonly api = inject(ApiService);
  readonly session = inject(SessionService);
  readonly offersApi = inject(OffersApiService);
  readonly requestsApi = inject(RequestsApiService);
  readonly translate = inject(TranslateService);

  readonly branches = signal<readonly Branch[]>([]);
  readonly costCentres = signal<readonly CostCentre[]>([]);
  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly expiredQuotations = signal<{ id: string; supplier_name?: string; confirmed: boolean }[]>([]);

  idempotencyKey: string | null = null;

  readonly form = this.fb.group({
    branch_id: [this.data.branchId ?? '', [Validators.required]],
    required_by_date: [this.data.rfqNeededByDate ?? '', [Validators.required]],
    cost_centre_id: [null as string | null],
  });

  ngOnInit(): void {
    this.loadBranches();
    this.loadCostCentres();
  }

  getTenantStorageKey(): string {
    const tenantId = this.session.tenant?.()?.id ?? 'default';
    return `${LAST_BRANCH_STORAGE_PREFIX}${tenantId}`;
  }

  readSavedBranchId(): string | null {
    try {
      return localStorage.getItem(this.getTenantStorageKey());
    } catch {
      return null;
    }
  }

  saveBranchId(branchId: string): void {
    if (!branchId) return;
    try {
      localStorage.setItem(this.getTenantStorageKey(), branchId);
    } catch {
      // Ignore storage access errors
    }
  }

  loadBranches(): void {
    this.api.listBranches({ is_active: true, limit: 100 }).subscribe({
      next: (res) => {
        this.branches.set(res.items);
        this.applyBranchPreselection();
      },
      error: () => {
        // Soft fail
      },
    });
  }

  loadCostCentres(): void {
    this.api.listCostCentres({ is_archived: false, limit: 100 }).subscribe({
      next: (res) => {
        this.costCentres.set(res.items);
      },
      error: () => {
        // Soft fail
      },
    });
  }

  applyBranchPreselection(): void {
    const items = this.branches();
    if (items.length === 0) return;
    if (this.form.get('branch_id')?.value) return;

    if (items.length === 1) {
      this.form.patchValue({ branch_id: items[0].id });
      return;
    }
    const saved = this.readSavedBranchId();
    if (saved && items.some((b) => b.id === saved)) {
      this.form.patchValue({ branch_id: saved });
    }
  }

  onBranchChange(branchId: string): void {
    this.saveBranchId(branchId);
  }

  toggleExpiredQuotation(id: string, confirmed: boolean): void {
    this.expiredQuotations.update((list) =>
      list.map((item) => (item.id === id ? { ...item, confirmed } : item)),
    );
  }

  getSupplierNameForQuotation(id: string): string {
    const s = this.data.suppliers?.find((sup) => sup.id === id);
    return s?.name ?? id;
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const branchId = this.form.value.branch_id!;
    this.saveBranchId(branchId);

    if (!this.idempotencyKey) {
      this.idempotencyKey = crypto.randomUUID();
    }

    const confirmedExpiredIds = this.expiredQuotations()
      .filter((eq) => eq.confirmed)
      .map((eq) => eq.id);

    const payload: SplitPrepareRequest = {
      branch_id: branchId,
      required_by_date: this.form.value.required_by_date!,
      cost_centre_id: this.form.value.cost_centre_id || undefined,
      confirm_expired_quotation_ids: confirmedExpiredIds,
    };

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    this.offersApi.prepareRequests(this.data.basketId, payload, this.idempotencyKey).subscribe({
      next: (res) => {
        this.fetchRequests(res.purchase_request_ids as string[]);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (err instanceof HttpErrorResponse && err.status === 409) {
          const reason = err.error?.details?.reason;
          if (reason === 'expired_quotation_unconfirmed') {
            const quotationIds: string[] = err.error?.details?.quotation_ids ?? [];
            this.expiredQuotations.set(
              quotationIds.map((id) => ({
                id,
                supplier_name: this.getSupplierNameForQuotation(id),
                confirmed: false,
              })),
            );
            this.errorMessage.set(
              this.translate.instant('basketSplit.prepareRequests.errors.expiredUnconfirmed'),
            );
            return;
          }
          if (reason === 'split_stale') {
            this.dialogRef.close({ stale: true });
            return;
          }
          if (reason === 'rfq_already_converted') {
            this.dialogRef.close({
              rfqAlreadyConverted: true,
              purchaseRequestIds: err.error?.details?.purchase_request_ids ?? [],
            });
            return;
          }
          const messageKey = `basketSplit.prepareRequests.errors.${this.toCamelCase(reason)}`;
          const translated = this.translate.instant(messageKey);
          this.errorMessage.set(
            translated !== messageKey
              ? translated
              : this.translate.instant('basketSplit.prepareRequests.errors.generic'),
          );
          return;
        }

        this.errorMessage.set(this.translate.instant('basketSplit.prepareRequests.errors.generic'));
      },
    });
  }

  fetchRequests(ids: string[]): void {
    if (!ids || ids.length === 0) {
      this.isSubmitting.set(false);
      this.dialogRef.close({ success: true, requests: [] });
      return;
    }

    forkJoin(ids.map((id) => this.requestsApi.getRequest(id))).subscribe({
      next: (requests) => {
        this.isSubmitting.set(false);
        this.dialogRef.close({ success: true, requests });
      },
      error: () => {
        this.isSubmitting.set(false);
        this.dialogRef.close({ success: true, requestIds: ids });
      },
    });
  }

  private toCamelCase(str: string): string {
    if (!str) return '';
    return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  }

  cancel(): void {
    this.dialogRef.close();
  }
}
