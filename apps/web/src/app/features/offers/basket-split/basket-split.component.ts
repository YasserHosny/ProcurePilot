import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Injectable, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormGroupDirective, FormsModule, NgForm } from '@angular/forms';
import { ErrorStateMatcher } from '@angular/material/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription, interval, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatService } from '../../../core/format/format.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatQuantityPipe } from '../../../core/format/quantity.pipe';
import { UnitLabelPipe, unitLabel } from '../../../core/format/unit-label';
import { RfqApi, type RfqDetail } from '../../rfq/rfq-api';
import type {
  BasketItemRequest,
  BasketOptimiseRequest,
  BasketSplitJob,
  OptimisationConstraint,
  OptimisationWeights,
  RiskTolerance,
  UrgencyLevel,
  ViolatedOptimisationConstraint,
} from '../offers-api';
import {
  type BasketSplitFormItem,
  type BasketSplitUIState,
  determineBasketSplitUIState,
} from './basket-split-state';

import { BasketSplitInfeasibleComponent } from './basket-split-infeasible.component';
import { BasketSplitResultsComponent } from './basket-split-results.component';

@Injectable()
export class BasketSubmitErrorStateMatcher implements ErrorStateMatcher {
  private readonly component = inject(BasketSplitComponent);
  isErrorState(control: AbstractControl | null, form: FormGroupDirective | NgForm | null): boolean {
    const isSubmitted = Boolean(form?.submitted || this.component.hasAttemptedSubmit());
    return Boolean(control && control.invalid && (control.touched || isSubmitted));
  }
}

@Component({
  selector: 'app-basket-split',
  standalone: true,
  providers: [
    { provide: ErrorStateMatcher, useClass: BasketSubmitErrorStateMatcher },
  ],
  imports: [
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTableModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslatePipe,
    RouterModule,
    FormatDatePipe,
    FormatQuantityPipe,
    UnitLabelPipe,
    BasketSplitResultsComponent,
    BasketSplitInfeasibleComponent,
  ],
  templateUrl: './basket-split.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './basket-split.component.scss',
})
export class BasketSplitComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly format = inject(FormatService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly rfqApi = inject(RfqApi);

  readonly rfqDetail = signal<RfqDetail | null>(null);
  readonly suppliers = signal<Supplier[]>([]);
  readonly products = signal<Product[]>([]);
  readonly isLoading = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);

  readonly minSuppliers = 2;
  readonly maxSuppliers = 10;
  readonly hasAttemptedSubmit = signal<boolean>(false);

  readonly supplierId1 = signal<string>('');
  readonly supplierId2 = signal<string>('');
  readonly additionalSupplierIds = signal<string[]>([]);
  readonly items = signal<BasketSplitFormItem[]>([
    { workspace_product_id: '', quantity: '' },
  ]);

  readonly showAdvancedConstraints = signal<boolean>(false);
  readonly riskTolerance = signal<RiskTolerance>('medium');
  readonly urgency = signal<UrgencyLevel>('normal');
  readonly excludedSupplierIds = signal<string[]>([]);
  readonly weights = signal<OptimisationWeights>({
    price: 0.4,
    preferred_supplier: 0.2,
    risk: 0.2,
    lead_time: 0.1,
    quality: 0.1,
  });

  readonly allSelectedSupplierIds = computed<string[]>(() => {
    const s1 = this.supplierId1();
    const s2 = this.supplierId2();
    const extra = this.additionalSupplierIds().filter(Boolean);
    const set = new Set<string>();
    if (s1) set.add(s1);
    if (s2) set.add(s2);
    extra.forEach((id) => set.add(id));
    return Array.from(set);
  });

  readonly currentJob = signal<BasketSplitJob | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly otherProductIdsByRow = computed<Set<string>[]>(() => {
    const currentItems = this.items();
    return currentItems.map((_, index) => {
      const ids = new Set<string>();
      currentItems.forEach((item, i) => {
        if (i !== index && item.workspace_product_id) {
          ids.add(item.workspace_product_id);
        }
      });
      return ids;
    });
  });

  private readonly productErrorMatchers = new Map<number, ErrorStateMatcher>();

  getProductErrorMatcher(index: number): ErrorStateMatcher {
    let matcher = this.productErrorMatchers.get(index);
    if (!matcher) {
      matcher = {
        isErrorState: (control: AbstractControl | null, form: FormGroupDirective | NgForm | null): boolean => {
          const isSubmitted = Boolean(form?.submitted || this.hasAttemptedSubmit());
          const isDuplicate = this.isItemProductDuplicate(index);
          const isInvalid = Boolean((control && control.invalid) || isDuplicate);
          return Boolean(isInvalid && (control?.touched || isSubmitted));
        },
      };
      this.productErrorMatchers.set(index, matcher);
    }
    return matcher;
  }

  otherProductIds(index: number): Set<string> {
    return this.otherProductIdsByRow()[index] ?? new Set<string>();
  }

  isItemProductDuplicate(index: number): boolean {
    const item = this.items()[index];
    if (!item?.workspace_product_id) return false;
    return this.otherProductIds(index).has(item.workspace_product_id);
  }

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));
  readonly isRfqMode = computed<boolean>(() => Boolean(this.currentJob()?.rfq_id));
  readonly rfqShortId = computed<string>(() => this.currentJob()?.rfq_id?.slice(0, 8) ?? '');
  readonly rfqSentDate = computed<string>(() => {
    const detail = this.rfqDetail();
    return detail?.rfq.sent_at || detail?.rfq.created_at || '';
  });

  readonly uiState = computed<BasketSplitUIState>(() => {
    return determineBasketSplitUIState(this.currentJob(), this.isSubmitting());
  });

  readonly appliedConstraints = computed<readonly OptimisationConstraint[]>(
    () => this.currentJob()?.result?.applied_constraints ?? [],
  );

  readonly violatedConstraints = computed<readonly ViolatedOptimisationConstraint[]>(
    () => this.currentJob()?.result?.violated_constraints ?? [],
  );

  readonly riskNotes = computed<readonly string[]>(
    () => this.currentJob()?.result?.risk_notes ?? [],
  );

  readonly solverConfidence = computed<'high' | 'medium' | 'low' | undefined>(
    () => this.currentJob()?.result?.confidence,
  );

  readonly validUntil = computed<string | null | undefined>(
    () => this.currentJob()?.result?.valid_until,
  );

  translateRiskNote(note: string): string {
    const key = `advancedBasket.riskNotes.${note}`;
    const translated = this.translate.instant(key);
    return translated !== key ? translated : note;
  }

  private pollSubscription: Subscription | null = null;

  ngOnInit(): void {
    this.loadSuppliersAndProducts();

    this.route.paramMap.subscribe((params) => {
      const jobId = params.get('id');
      if (jobId) {
        this.fetchJob(jobId);
      }
    });
  }

  loadSuppliersAndProducts(): void {
    this.isLoading.set(true);
    this.api.suppliers({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.suppliers.set(res.items);
        if (res.items.length >= 2 && !this.supplierId1() && !this.supplierId2()) {
          this.supplierId1.set(res.items[0].id);
          this.supplierId2.set(res.items[1].id);
        }
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false),
    });

    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.products.set(res.items);
      },
      error: () => {
        // Fallback silently if products load fails
      },
    });
  }

  addItem(): void {
    this.items.update((list) => [...list, { workspace_product_id: '', quantity: '' }]);
  }

  removeItem(index: number): void {
    this.items.update((list) => list.filter((_, i) => i !== index));
  }

  onProductSelect(index: number, productId: string): void {
    this.items.update((list) => {
      const updated = [...list];
      updated[index] = { ...updated[index], workspace_product_id: productId };
      return updated;
    });
  }

  onQuantityChange(index: number, qty: string): void {
    this.items.update((list) => {
      const updated = [...list];
      updated[index] = { ...updated[index], quantity: qty };
      return updated;
    });
  }

  baseUnitFor(workspaceProductId: string): string | undefined {
    return (
      this.currentJob()?.pack_snapshot?.[workspaceProductId]?.base_unit ??
      this.products().find((product) => product.id === workspaceProductId)?.base_unit
    );
  }

  getItemPackQuantity(item: { workspace_product_id: string; quantity: string }): number {
    const base = parseFloat(item.quantity);
    const snapshot = this.currentJob()?.pack_snapshot?.[item.workspace_product_id];
    const pack = this.products().find((p) => p.id === item.workspace_product_id)?.pack;
    const size = snapshot
      ? parseFloat(snapshot.base_quantity)
      : pack
        ? parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)))
        : 1;
    const packSize = Number.isFinite(size) && size > 0 ? size : 1;
    return Number.isFinite(base) ? base / packSize : 0;
  }

  /** Base units (litre/kg) in one purchasing pack of the product; 1 when it has no pack info. */
  packBaseQuantityFor(workspaceProductId: string): number {
    const pack = this.products().find((product) => product.id === workspaceProductId)?.pack;
    if (!pack) return 1;
    const base = parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)));
    return base > 0 ? base : 1;
  }

  /** "10 packs × 1 kg = 10 kg" in the UI language, with localised digits and unit. */
  packHintParams(item: { workspace_product_id: string; quantity: string }): Record<string, string> {
    return {
      count: this.format.formatExactQuantity(item.quantity),
      size: this.format.formatExactQuantity(String(this.packBaseQuantityFor(item.workspace_product_id))),
      total: this.format.formatExactQuantity(this.baseQuantityFor(item)),
      unit: unitLabel(this.translate, this.baseUnitFor(item.workspace_product_id)),
    };
  }

  /** Quantities are typed in PACKS; the optimiser works in base units, so convert on send. */
  baseQuantityFor(item: { workspace_product_id: string; quantity: string }): string {
    const packs = parseFloat(item.quantity);
    if (isNaN(packs)) return item.quantity;
    return String(Math.round(packs * this.packBaseQuantityFor(item.workspace_product_id) * 1e6) / 1e6);
  }

  isItemProductInvalid(item: BasketSplitFormItem): boolean {
    return this.hasAttemptedSubmit() && !item.workspace_product_id;
  }

  isItemQuantityInvalid(item: BasketSplitFormItem): boolean {
    if (!this.hasAttemptedSubmit()) return false;
    const q = parseFloat(item.quantity);
    return isNaN(q) || q <= 0;
  }

  isFormValid(): boolean {
    const s1 = this.supplierId1();
    const s2 = this.supplierId2();
    if (!s1 || !s2 || s1 === s2) return false;

    const all = this.allSelectedSupplierIds();
    if (all.length < this.minSuppliers || all.length > this.maxSuppliers) return false;

    const currentItems = this.items();
    if (currentItems.length === 0 || currentItems.length > 50) return false;

    const productIds = currentItems.map((item) => item.workspace_product_id).filter(Boolean);
    if (new Set(productIds).size !== productIds.length) return false;

    return currentItems.every((item) => {
      const q = parseFloat(item.quantity);
      return Boolean(item.workspace_product_id) && !isNaN(q) && q > 0;
    });
  }

  submitBasket(): void {
    this.hasAttemptedSubmit.set(true);
    if (!this.isFormValid() || !this.isWriter()) return;

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    const s1 = this.supplierId1();
    const s2 = this.supplierId2();
    const supplierIds = this.allSelectedSupplierIds();
    const reqItems: BasketItemRequest[] = this.items().map((it) => ({
      workspace_product_id: it.workspace_product_id,
      quantity: this.baseQuantityFor(it),
    }));

    const reqBody: BasketOptimiseRequest = {
      supplier_ids: supplierIds.length >= 2 ? supplierIds : [s1, s2],
      items: reqItems,
      risk_tolerance: this.riskTolerance(),
      urgency: this.urgency(),
      excluded_supplier_ids:
        this.excludedSupplierIds().length > 0 ? this.excludedSupplierIds() : undefined,
      weights: this.weights(),
    };

    this.api
      .optimiseBasket(reqBody)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          this.isSubmitting.set(false);
          this.currentJob.set(job);
          this.router.navigate(['/offers/basket-split', job.id]);
          this.pollJob(job.id);
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.handleError(err);
        },
      });
  }

  addAdditionalSupplier(): void {
    if (this.allSelectedSupplierIds().length < this.maxSuppliers) {
      this.additionalSupplierIds.update((s) => [...s, '']);
    }
  }

  removeAdditionalSupplier(index: number): void {
    this.additionalSupplierIds.update((s) => s.filter((_, i) => i !== index));
  }

  updateAdditionalSupplier(index: number, id: string): void {
    this.additionalSupplierIds.update((s) => {
      const next = [...s];
      next[index] = id;
      return next;
    });
  }

  updateWeight(key: keyof OptimisationWeights, val: string | number): void {
    const num = typeof val === 'number' ? val : parseFloat(val);
    if (!isNaN(num) && num >= 0 && num <= 1) {
      this.weights.update((w) => ({ ...w, [key]: num }));
    }
  }

  rerunOptimisation(): void {
    const rfqId = this.currentJob()?.rfq_id;
    if (rfqId) {
      if (!this.isWriter() || this.isSubmitting()) return;
      this.isSubmitting.set(true);
      this.errorMessage.set(null);
      this.rfqApi.splitRfq(rfqId).subscribe({
        next: (job) => {
          this.isSubmitting.set(false);
          this.currentJob.set(job);
          this.router.navigate(['/offers/basket-split', job.id]);
          this.pollJob(job.id);
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.handleError(err);
        },
      });
      return;
    }
    this.submitBasket();
  }

  fetchJob(jobId: string): void {
    this.isLoading.set(true);
    this.api
      .getBasketSplitJob(jobId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          this.isLoading.set(false);
          if (job.rfq_id) {
            this.rfqApi.getRfq(job.rfq_id).subscribe({
              next: (detail) => this.rfqDetail.set(detail),
              error: () => this.rfqDetail.set(null),
            });
          } else {
            this.rfqDetail.set(null);
          }
          if (job.status === 'queued' || job.status === 'running') {
            this.pollJob(job.id);
          }
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
  }

  private pollJob(jobId: string): void {
    this.pollSubscription?.unsubscribe();

    this.pollSubscription = interval(1500)
      .pipe(
        switchMap(() => this.api.getBasketSplitJob(jobId)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          if (job.rfq_id && !this.rfqDetail()) {
            this.rfqApi.getRfq(job.rfq_id).subscribe({
              next: (detail) => this.rfqDetail.set(detail),
              error: () => this.rfqDetail.set(null),
            });
          }
          if (job.status === 'completed' || job.status === 'failed') {
            this.pollSubscription?.unsubscribe();
            this.pollSubscription = null;
          }
        },
        error: (err: unknown) => {
          this.pollSubscription?.unsubscribe();
          this.pollSubscription = null;
          this.handleError(err);
        },
      });
  }

  resetForm(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = null;
    this.currentJob.set(null);
    this.errorMessage.set(null);
    this.hasAttemptedSubmit.set(false);
    this.items.set([{ workspace_product_id: '', quantity: '' }]);
    this.router.navigate(['/offers/basket-split']);
  }

  getSupplierName(supplierId: string): string {
    const s = this.suppliers().find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getProductName(productId: string): string {
    const p = this.products().find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }

  getSingleSupplierSavings(): {
    type: 'split_saves' | 'no_savings' | 'single_only' | 'neither_feasible';
    cheaperSupplierName?: string;
    savingsAmount?: string;
    currency?: string;
  } {
    const job = this.currentJob();
    const result = job?.result;
    if (!result || !result.feasible || !result.total_landed_cost) {
      return { type: 'neither_feasible' };
    }

    const baselines = result.single_supplier_baselines ?? [];
    const feasibleBaselines = baselines.filter((b) => b.feasible && b.total_landed_cost);

    if (feasibleBaselines.length === 0) {
      return { type: 'neither_feasible' };
    }

    if (feasibleBaselines.length === 1) {
      const s = feasibleBaselines[0];
      return {
        type: 'single_only',
        cheaperSupplierName: this.getSupplierName(s.supplier_id),
      };
    }

    // Find cheaper single supplier
    const sorted = [...feasibleBaselines].sort(
      (a, b) =>
        parseFloat(a.total_landed_cost!.amount) - parseFloat(b.total_landed_cost!.amount),
    );
    const cheapestSingle = sorted[0];
    const splitTotal = parseFloat(result.total_landed_cost.amount);
    const singleTotal = parseFloat(cheapestSingle.total_landed_cost!.amount);

    if (splitTotal < singleTotal) {
      const diff = (singleTotal - splitTotal).toFixed(2);
      return {
        type: 'split_saves',
        cheaperSupplierName: this.getSupplierName(cheapestSingle.supplier_id),
        savingsAmount: diff,
        currency: result.total_landed_cost.currency,
      };
    }

    return {
      type: 'no_savings',
      cheaperSupplierName: this.getSupplierName(cheapestSingle.supplier_id),
    };
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('basketSplit.status.failedMessage'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('basketSplit.status.failedMessage'));
  }
}
