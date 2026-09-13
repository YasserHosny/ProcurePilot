import { DecimalPipe, NgClass, NgFor, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
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
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription, interval, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
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

@Component({
  selector: 'app-basket-split',
  standalone: true,
  imports: [
    FormsModule,
    NgIf,
    NgFor,
    NgClass,
    RouterLink,
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
    FormatDatePipe,
    FormatMoneyPipe,
    DecimalPipe,
    RoleDirective,
  ],
  templateUrl: './basket-split.component.html',
  styleUrl: './basket-split.component.scss',
})
export class BasketSplitComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly suppliers = signal<Supplier[]>([]);
  readonly products = signal<Product[]>([]);
  readonly isLoading = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);

  readonly supplierId1 = signal<string>('');
  readonly supplierId2 = signal<string>('');
  readonly additionalSupplierIds = signal<string[]>([]);
  readonly items = signal<BasketSplitFormItem[]>([
    { workspace_product_id: '', quantity: '10' },
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

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

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
        if (res.items.length > 0 && this.items().length === 1 && !this.items()[0].workspace_product_id) {
          this.items.set([{ workspace_product_id: res.items[0].id, quantity: '10' }]);
        }
      },
      error: () => {
        // Fallback silently if products load fails
      },
    });
  }

  addItem(): void {
    const prods = this.products();
    const defaultProdId = prods.length > 0 ? prods[0].id : '';
    this.items.update((list) => [...list, { workspace_product_id: defaultProdId, quantity: '10' }]);
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
    return this.products().find((product) => product.id === workspaceProductId)?.base_unit;
  }

  isFormValid(): boolean {
    const s1 = this.supplierId1();
    const s2 = this.supplierId2();
    if (!s1 || !s2 || s1 === s2) return false;

    const all = this.allSelectedSupplierIds();
    if (all.length < 2 || all.length > 10) return false;

    const currentItems = this.items();
    if (currentItems.length === 0 || currentItems.length > 50) return false;

    return currentItems.every((item) => {
      const q = parseFloat(item.quantity);
      return Boolean(item.workspace_product_id) && !isNaN(q) && q > 0;
    });
  }

  submitBasket(): void {
    if (!this.isFormValid() || !this.isWriter()) return;

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    const s1 = this.supplierId1();
    const s2 = this.supplierId2();
    const supplierIds = this.allSelectedSupplierIds();
    const reqItems: BasketItemRequest[] = this.items().map((it) => ({
      workspace_product_id: it.workspace_product_id,
      quantity: it.quantity,
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
    if (this.allSelectedSupplierIds().length < 10) {
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
