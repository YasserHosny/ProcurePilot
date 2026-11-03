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
import { EMPTY, Subscription, catchError, expand, forkJoin, interval, map, of, reduce, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, BasketSplitJobSummary, Product, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatService } from '../../../core/format/format.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { unitLabel } from '../../../core/format/unit-label';
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
import { formatQuantityDisplay, type QuantityDisplayResult } from './quantity-display';

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
    FormatMoneyPipe,
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
  /** Cursor for the next page of the current product list; null when it is complete. */
  readonly productsCursor = signal<string | null>(null);
  readonly hasMoreProducts = computed(() => this.productsCursor() !== null);
  private productQuery = '';
  /** Bumped by every new product search, so a slower answer to an older one is dropped. */
  private productGeneration = 0;
  private productSearchTimer: ReturnType<typeof setTimeout> | null = null;
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
  /** Bumped for every job that is opened, so a slow answer for an earlier one is dropped. */
  private jobGeneration = 0;
  private pollFailures = 0;
  readonly jobNotFound = signal(false);
  readonly pollFailed = signal(false);

  /** Earlier splits of this workspace, newest first. */
  readonly history = signal<BasketSplitJobSummary[]>([]);
  private readonly historyCursor = signal<string | null>(null);
  readonly hasMoreHistory = computed(() => this.historyCursor() !== null);

  /** What a screen reader hears as the job moves from queued to running to finished. */
  readonly liveStatus = computed(() => {
    switch (this.uiState()) {
      case 'queued': return this.translate.instant('basketSplit.status.queued');
      case 'running':
      case 'submitting': return this.translate.instant('basketSplit.status.running');
      case 'completed_feasible':
      case 'completed_infeasible': return this.translate.instant('basketSplit.status.completedAnnounce');
      case 'failed': return this.translate.instant('basketSplit.status.failedMessage');
      default: return '';
    }
  });
  /** The form was filled from an earlier job: the buyer should confirm the commercial settings. */
  readonly rerunNotice = signal(false);

  ngOnInit(): void {
    this.loadSuppliersAndProducts();
    this.loadHistory();

    this.route.paramMap.subscribe((params) => {
      const jobId = params.get('id');
      if (jobId) {
        this.fetchJob(jobId);
      }
    });
  }

  loadSuppliersAndProducts(): void {
    this.isLoading.set(true);
    // The optimiser accepts active and preferred suppliers; both belong in the pickers.
    forkJoin({
      active: this.allSuppliers('active'),
      preferred: this.allSuppliers('preferred').pipe(catchError(() => of([] as Supplier[]))),
    }).subscribe({
      next: ({ active, preferred }) => {
        const byId = new Map<string, Supplier>();
        for (const supplier of [...active, ...preferred]) byId.set(supplier.id, supplier);
        const items = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
        this.suppliers.set(items);
        if (items.length >= 2 && !this.supplierId1() && !this.supplierId2()) {
          this.supplierId1.set(items[0].id);
          this.supplierId2.set(items[1].id);
        }
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false),
    });

    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.products.set(res.items);
        this.productsCursor.set(res.next_cursor);
      },
      error: () => {
        // Fallback silently if products load fails
      },
    });
  }

  /** Every page of the suppliers with this status (the API pages at 100). */
  private allSuppliers(status: 'active' | 'preferred') {
    return this.api.suppliers({ limit: 100, status }).pipe(
      expand((res) =>
        res.next_cursor ? this.api.suppliers({ limit: 100, status, cursor: res.next_cursor }) : EMPTY,
      ),
      reduce((all, res) => [...all, ...res.items], [] as Supplier[]),
    );
  }

  /** Products already chosen stay available whatever the search shows. */
  private mergeProducts(found: Product[], keepChosen = true): void {
    const chosen = new Set(this.items().map((item) => item.workspace_product_id).filter(Boolean));
    const byId = new Map<string, Product>();
    for (const product of keepChosen ? this.products().filter((p) => chosen.has(p.id)) : []) byId.set(product.id, product);
    for (const product of found) byId.set(product.id, product);
    this.products.set([...byId.values()]);
  }

  /** Searches the catalogue by name after a short pause; an empty search lists the first page again. */
  onProductSearch(query: string): void {
    if (this.productSearchTimer) clearTimeout(this.productSearchTimer);
    this.productSearchTimer = setTimeout(() => {
      this.productQuery = query.trim();
      const generation = ++this.productGeneration;
      this.api
        .products({ limit: 100, status: 'active', q: this.productQuery || undefined })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (res) => {
            if (generation !== this.productGeneration) return;
            this.mergeProducts(res.items);
            this.productsCursor.set(res.next_cursor);
          },
          error: () => undefined, // the list stays as it was
        });
    }, 300);
  }

  /** The next page of the current list (all products, or the current search). */
  loadMoreProducts(): void {
    const cursor = this.productsCursor();
    if (!cursor) return;
    const generation = this.productGeneration;
    this.api
      .products({ limit: 100, status: 'active', cursor, q: this.productQuery || undefined })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          if (generation !== this.productGeneration) return;
          const byId = new Map(this.products().map((product) => [product.id, product] as const));
          for (const product of res.items) byId.set(product.id, product);
          this.products.set([...byId.values()]);
          this.productsCursor.set(res.next_cursor);
        },
        error: () => undefined,
      });
  }

  /** «Supplier A, Supplier B» for a history row. */
  historySuppliers(job: BasketSplitJobSummary): string {
    return job.supplier_ids
      .map((id, index) => job.supplier_names?.[index] || this.getSupplierName(id))
      .join(', ');
  }

  loadHistory(): void {
    this.api
      .listBasketSplitJobs({ limit: 10 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.history.set([...res.items]);
          this.historyCursor.set(res.next_cursor);
        },
        error: () => {
          // History is a convenience: without it the form works as before.
          this.history.set([]);
          this.historyCursor.set(null);
        },
      });
  }

  loadMoreHistory(): void {
    const cursor = this.historyCursor();
    if (!cursor) return;
    this.api
      .listBasketSplitJobs({ limit: 10, cursor })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          const known = new Set(this.history().map((job) => job.id));
          this.history.set([...this.history(), ...res.items.filter((job) => !known.has(job.id))]);
          this.historyCursor.set(res.next_cursor);
        },
        error: () => undefined,
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

  quantityDisplay(item: { workspace_product_id: string; quantity: string }): QuantityDisplayResult {
    return formatQuantityDisplay({
      line: item,
      product: this.products().find((p) => p.id === item.workspace_product_id),
      packSnapshot: this.currentJob()?.pack_snapshot,
      translate: this.translate,
      format: this.format,
    });
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
    this.rerunNotice.set(false);

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
          this.openJob();
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
    const job = this.currentJob();
    const rfqId = job?.rfq_id;
    if (rfqId) {
      if (!this.isWriter() || this.isSubmitting()) return;
      this.isSubmitting.set(true);
      this.errorMessage.set(null);
      this.rfqApi.splitRfq(rfqId).subscribe({
        next: (next) => {
          this.isSubmitting.set(false);
          this.currentJob.set(next);
          this.router.navigate(['/offers/basket-split', next.id]);
          this.openJob();
          this.pollJob(next.id);
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.handleError(err);
        },
      });
      return;
    }
    if (job?.request_settings) {
      // The job says what it was run with, so the rerun reuses exactly that.
      if (!this.isWriter() || this.isSubmitting()) return;
      const settings = job.request_settings;
      this.isSubmitting.set(true);
      this.errorMessage.set(null);
      this.api
        .optimiseBasket({
          supplier_ids: job.supplier_ids,
          items: job.items,
          risk_tolerance: settings.risk_tolerance,
          urgency: settings.urgency,
          excluded_supplier_ids: settings.excluded_supplier_ids.length > 0 ? settings.excluded_supplier_ids : undefined,
          weights: settings.weights,
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (next) => {
            this.isSubmitting.set(false);
            this.currentJob.set(next);
            this.router.navigate(['/offers/basket-split', next.id]);
            this.openJob();
            this.pollJob(next.id);
          },
          error: (err: unknown) => {
            this.isSubmitting.set(false);
            this.handleError(err);
          },
        });
      return;
    }
    if (job) {
      // Older jobs carry no risk tolerance, urgency, exclusions or weights, so a rerun cannot
      // reproduce them. Put the job's suppliers and quantities back in the form and let the
      // buyer confirm those settings rather than silently running with the defaults.
      this.prefillFromJob(job);
      return;
    }
    this.submitBasket();
  }

  fetchJob(jobId: string): void {
    const generation = this.openJob();
    this.isLoading.set(true);
    this.api
      .getBasketSplitJob(jobId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          if (generation !== this.jobGeneration) return;
          this.currentJob.set(job);
          this.isLoading.set(false);
          this.resolveMissingProducts(job);
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
          if (generation !== this.jobGeneration) return;
          this.isLoading.set(false);
          if (err instanceof HttpErrorResponse && err.status === 404) {
            this.currentJob.set(null);
            this.jobNotFound.set(true);
            return;
          }
          this.handleError(err);
        },
      });
  }

  /** A job can use products beyond the first page the page loads: look those up by id. */
  private resolveMissingProducts(job: BasketSplitJob): void {
    const known = new Set(this.products().map((product) => product.id));
    for (const item of job.items) {
      if (known.has(item.workspace_product_id)) continue;
      this.api
        .product(item.workspace_product_id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (product) => {
            if (!this.products().some((p) => p.id === product.id)) {
              this.products.set([...this.products(), product]);
            }
          },
          error: () => undefined, // the id stays as the label
        });
    }
  }

  /** Starts a fresh job view: the previous job's poll and late answers must not touch it. */
  private openJob(): number {
    this.stopPolling();
    this.jobNotFound.set(false);
    this.pollFailed.set(false);
    this.pollFailures = 0;
    return ++this.jobGeneration;
  }

  private stopPolling(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = null;
  }

  retryPolling(): void {
    const job = this.currentJob();
    if (!job) return;
    this.pollFailed.set(false);
    this.pollFailures = 0;
    this.pollJob(job.id);
  }

  private pollJob(jobId: string): void {
    this.stopPolling();
    const generation = this.jobGeneration;

    this.pollSubscription = interval(1500)
      .pipe(
        switchMap(() =>
          // One failed poll must not end the stream: it is retried on the next tick.
          this.api.getBasketSplitJob(jobId).pipe(
            map((job) => ({ job, failure: null as unknown })),
            catchError((failure: unknown) => of({ job: null, failure })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ job, failure }) => {
        if (generation !== this.jobGeneration) return;
        if (!job) {
          if (failure instanceof HttpErrorResponse && failure.status === 404) {
            this.stopPolling();
            this.currentJob.set(null);
            this.jobNotFound.set(true);
            return;
          }
          this.pollFailures += 1;
          if (this.pollFailures >= 3) {
            this.stopPolling();
            this.pollFailed.set(true);
          }
          return;
        }
        this.pollFailures = 0;
        this.currentJob.set(job);
        if (job.rfq_id && !this.rfqDetail()) {
          this.rfqApi.getRfq(job.rfq_id).subscribe({
            next: (detail) => this.rfqDetail.set(detail),
            error: () => this.rfqDetail.set(null),
          });
        }
        if (job.status === 'completed' || job.status === 'failed') {
          this.stopPolling();
        }
      });
  }

  /** Base units in one pack: the size saved on the job, else the product's, else unknown. */
  private packBaseFor(job: BasketSplitJob, productId: string): number | null {
    const saved = parseFloat(job.pack_snapshot?.[productId]?.base_quantity ?? '');
    if (saved > 0) return saved;
    return this.products().some((product) => product.id === productId)
      ? this.packBaseQuantityFor(productId)
      : null;
  }

  /** Quantities on the job are in base units; the form takes packs. */
  private prefillFromJob(job: BasketSplitJob): void {
    const packBases = job.items.map((item) => this.packBaseFor(job, item.workspace_product_id));
    if (packBases.some((base) => base === null)) {
      // Treating an unknown pack as one unit would turn base units into packs and inflate the rerun.
      this.errorMessage.set(this.translate.instant('basketSplit.rerunPackUnknown'));
      return;
    }
    const [first, second, ...rest] = job.supplier_ids;
    this.supplierId1.set(first ?? '');
    this.supplierId2.set(second ?? '');
    this.additionalSupplierIds.set([...rest]);
    this.items.set(
      job.items.map((item, index) => ({
        workspace_product_id: item.workspace_product_id,
        quantity: String(Math.round((parseFloat(item.quantity) / packBases[index]!) * 1e6) / 1e6),
      })),
    );
    this.stopPolling();
    this.currentJob.set(null);
    this.errorMessage.set(null);
    this.hasAttemptedSubmit.set(false);
    this.rerunNotice.set(true);
  }

  resetForm(): void {
    this.jobGeneration += 1;
    this.stopPolling();
    this.jobNotFound.set(false);
    this.pollFailed.set(false);
    this.rerunNotice.set(false);
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
