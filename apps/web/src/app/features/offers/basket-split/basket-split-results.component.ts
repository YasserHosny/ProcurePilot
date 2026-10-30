import { CommonModule, NgClass } from '@angular/common';
import { Component, Input, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterModule } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin } from 'rxjs';

import type {
  BudgetStatusValue,
  Money,
  Product,
  PurchaseRequest,
  SingleSupplierBaseline,
  Supplier,
} from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { SessionService } from '../../../core/auth/session.service';
import { RfqApi, type RfqDetail } from '../../rfq/rfq-api';
import { RequestsApiService } from '../../requests/requests-api';
import type {
  BasketSplitJob,
  OptimisationConstraint,
  ViolatedOptimisationConstraint,
} from '../offers-api';
import { constraintText, isUserFacingConstraint } from './constraint-text';
import { formatQuantityDisplay } from './quantity-display';
import {
  PrepareSplitRequestsDialogComponent,
  type PrepareSplitRequestsDialogResult,
} from './prepare-split-requests-dialog.component';

@Component({
  selector: 'app-basket-split-results',
  standalone: true,
  imports: [
    CommonModule,
    NgClass,
    RouterModule,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatIconModule,
    MatDividerModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './basket-split-results.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './basket-split-results.component.scss',
})
export class BasketSplitResultsComponent implements OnInit {
  private readonly translate = inject(TranslateService);
  private readonly format = inject(FormatService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  private readonly rfqApi = inject(RfqApi);
  private readonly requestsApi = inject(RequestsApiService);

  @Input({ required: true }) currentJob!: BasketSplitJob | null;
  @Input({ required: true }) suppliers: readonly Supplier[] = [];
  @Input({ required: true }) products: readonly Product[] = [];
  @Input({ required: true }) solverConfidence: string | null | undefined = null;
  @Input({ required: true }) validUntil: string | null | undefined = null;
  @Input({ required: true }) appliedConstraints: readonly OptimisationConstraint[] = [];
  @Input({ required: true }) violatedConstraints: readonly ViolatedOptimisationConstraint[] = [];
  @Input({ required: true }) riskNotes: readonly string[] = [];
  @Input({ required: true }) singleSupplierSavings!: {
    type: 'split_saves' | 'no_savings' | 'single_only' | 'neither_feasible';
    cheaperSupplierName?: string;
    savingsAmount?: string;
    currency?: string;
  };
  readonly rfqDetailSignal = signal<RfqDetail | null>(null);

  @Input()
  set rfqDetail(value: RfqDetail | null | undefined) {
    const detail = value ?? null;
    this.rfqDetailSignal.set(detail);
    if (detail?.rfq?.status === 'converted') {
      this.convertedRequestIds.set(detail.converted_purchase_request_ids ?? []);
    }
  }
  get rfqDetail(): RfqDetail | null {
    return this.rfqDetailSignal();
  }

  readonly preparedRequests = signal<PurchaseRequest[] | null>(null);
  readonly staleError = signal<boolean>(false);
  readonly convertedRequestIds = signal<readonly string[] | null>(null);
  readonly generalError = signal<string | null>(null);
  readonly isRerunningSplit = signal<boolean>(false);
  private rerunIdempotencyKey: string | null = null;

  readonly effectiveConvertedRequestIds = computed<readonly string[] | null>(() => {
    const fromSignal = this.convertedRequestIds();
    if (fromSignal !== null) {
      return fromSignal;
    }
    const rfq = this.rfqDetailSignal();
    if (rfq?.rfq?.status === 'converted') {
      return rfq.converted_purchase_request_ids ?? [];
    }
    return null;
  });

  readonly isAlreadyConverted = computed<boolean>(() => {
    return (
      this.convertedRequestIds() !== null ||
      this.rfqDetailSignal()?.rfq?.status === 'converted'
    );
  });

  ngOnInit(): void {
    if (this.currentJob?.rfq_id && !this.rfqDetailSignal()) {
      this.rfqApi.getRfq(this.currentJob.rfq_id).subscribe({
        next: (detail) => {
          this.rfqDetail = detail;
        },
        error: () => {
          // Soft fail
        },
      });
    }
  }

  get isRfqMode(): boolean {
    return Boolean(this.currentJob?.rfq_id);
  }

  get isWriter(): boolean {
    return this.session.hasRole('owner', 'buyer');
  }

  get allocatedSuppliersCount(): number {
    const allocs = this.currentJob?.result?.allocation ?? [];
    return allocs.filter((a) => (a.lines?.length ?? 0) > 0).length || allocs.length;
  }

  get prepareButtonLabel(): string {
    const count = this.allocatedSuppliersCount;
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    return this.translate.instant(`basketSplit.prepareRequests.button.${category}`, {
      count: this.format.formatNumber(count),
    });
  }

  get canPrepareRequests(): boolean {
    return (
      this.isRfqMode &&
      this.currentJob?.status === 'completed' &&
      Boolean(this.currentJob?.result?.feasible) &&
      this.isWriter &&
      this.allocatedSuppliersCount > 0 &&
      !this.preparedRequests() &&
      !this.isAlreadyConverted()
    );
  }

  get rfqNeededByDate(): string | null {
    return this.rfqDetail?.rfq?.needed_by_date ?? null;
  }

  openPrepareDialog(): void {
    if (!this.canPrepareRequests || !this.currentJob?.id) return;

    const dialogRef = this.dialog.open(PrepareSplitRequestsDialogComponent, {
      data: {
        basketId: this.currentJob.id,
        rfqId: this.currentJob.rfq_id!,
        rfqNeededByDate: this.rfqNeededByDate,
        suppliers: this.suppliers,
      },
      width: '560px',
    });

    dialogRef.afterClosed().subscribe((res?: PrepareSplitRequestsDialogResult) => {
      if (!res) return;
      if (res.success) {
        if (res.requests) {
          this.preparedRequests.set(res.requests);
        } else if (res.requestIds) {
          this.loadRequests(res.requestIds);
        }
        this.staleError.set(false);
        this.convertedRequestIds.set(res.requestIds ?? res.requests?.map((r) => r.id) ?? []);
        this.generalError.set(null);
      } else if (res.stale) {
        this.staleError.set(true);
        this.convertedRequestIds.set(null);
        this.generalError.set(null);
      } else if (res.rfqAlreadyConverted) {
        this.convertedRequestIds.set(res.purchaseRequestIds ?? []);
        this.staleError.set(false);
        this.generalError.set(null);
      } else if (res.error) {
        this.generalError.set(res.error);
      }
    });
  }

  rerunSplit(): void {
    const rfqId = this.currentJob?.rfq_id;
    if (!rfqId || this.isRerunningSplit()) return;

    if (!this.rerunIdempotencyKey) {
      this.rerunIdempotencyKey = crypto.randomUUID();
    }

    this.isRerunningSplit.set(true);
    this.rfqApi.splitRfq(rfqId, this.rerunIdempotencyKey).subscribe({
      next: (job) => {
        this.isRerunningSplit.set(false);
        this.rerunIdempotencyKey = null;
        this.router.navigate(['/offers/basket-split', job.id]);
      },
      error: () => {
        this.isRerunningSplit.set(false);
      },
    });
  }

  loadRequests(ids: string[]): void {
    if (!ids || ids.length === 0) return;
    forkJoin(ids.map((id) => this.requestsApi.getRequest(id))).subscribe({
      next: (reqs) => {
        this.preparedRequests.set(reqs);
      },
      error: () => {
        // Soft fail
      },
    });
  }

  getRequestSupplierName(request: PurchaseRequest): string {
    if (request.source?.supplier_name) {
      return request.source.supplier_name;
    }
    if (request.source?.supplier_id) {
      return this.getSupplierName(request.source.supplier_id);
    }
    return request.id;
  }

  getBudgetStatusValue(request: PurchaseRequest): BudgetStatusValue | null {
    const bs = request.budget_status;
    if (!bs) return null;
    if (bs.status) return bs.status;
    if (bs.exceeds) return 'over';
    if (!bs.remaining_amount) return 'no_budget';
    return 'within';
  }

  getBudgetStatusLabel(request: PurchaseRequest): string {
    const status = this.getBudgetStatusValue(request);
    if (!status) {
      return this.translate.instant('basketSplit.prepareRequests.summary.budgetNone');
    }
    if (status === 'over') {
      return this.translate.instant('basketSplit.prepareRequests.summary.budgetOver');
    }
    if (status === 'within') {
      return this.translate.instant('basketSplit.prepareRequests.summary.budgetWithin');
    }
    return this.translate.instant(`approvals.budgetStatus.${status}`);
  }

  getBudgetStatusClass(request: PurchaseRequest): string {
    const status = this.getBudgetStatusValue(request);
    if (status === 'over') return 'status-over';
    if (status === 'within') return 'status-within';
    return 'status-none';
  }

  get singleSupplierBaselines(): readonly SingleSupplierBaseline[] {
    return this.currentJob?.result?.single_supplier_baselines ?? [];
  }

  get bestSingleSupplierBaseline(): SingleSupplierBaseline | null {
    const baselines = this.singleSupplierBaselines.filter((b) => b.feasible && b.total_landed_cost);
    if (baselines.length === 0) return null;
    const sorted = [...baselines].sort(
      (a, b) => parseFloat(a.total_landed_cost!.amount) - parseFloat(b.total_landed_cost!.amount),
    );
    return sorted[0];
  }

  get splitSaving(): Money | null {
    const best = this.bestSingleSupplierBaseline?.total_landed_cost;
    const split = this.currentJob?.result?.total_landed_cost;
    if (!best || !split) return null;
    const diff = Math.max(0, parseFloat(best.amount) - parseFloat(split.amount));
    return {
      amount: diff.toFixed(2),
      currency: split.currency,
    };
  }

  translateRiskNote(note: string): string {
    const key = `advancedBasket.riskNotes.${note}`;
    const translated = this.translate.instant(key);
    return translated !== key ? translated : note;
  }

  /** Applied constraints worth showing a buyer (solver internals filtered out). */
  get visibleAppliedConstraints(): readonly OptimisationConstraint[] {
    return this.appliedConstraints.filter(isUserFacingConstraint);
  }

  constraintLabel(
    constraint: OptimisationConstraint | ViolatedOptimisationConstraint,
    outcome: 'applied' | 'violated' = 'applied',
  ): string {
    return constraintText(constraint, this.translate, (id) => this.getSupplierName(id), outcome);
  }

  /**
   * ADR-020: quantities are bought in packs. The solver works in base units, so show
   * "20 × 25 kg" first and the base total secondary. Loose goods (pack of 1) show base only.
   */
  quantityDisplay(line: { workspace_product_id: string; quantity: string }): {
    primary: string;
    secondary: string | null;
  } {
    return formatQuantityDisplay({
      line,
      product: this.products.find((p) => p.id === line.workspace_product_id),
      packSnapshot: this.currentJob?.pack_snapshot,
      translate: this.translate,
      format: this.format,
    });
  }

  getSupplierName(supplierId: string): string {
    const s = this.suppliers.find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getProductName(productId: string): string {
    const p = this.products.find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }
}
