import { Component, OnInit, OnChanges, inject, signal, computed, input, model, ChangeDetectionStrategy } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import { RfqApi, RfqDetail, RfqGuardrail, RfqResponseComparison, RfqResponseLineComparison } from '../rfq-api';
import { FormatService } from '../../../core/format/format.service';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import type { ApiError, Branch } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { parseIsoDateLocal, toIsoDate } from '../../../core/format/iso-date';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';

const LAST_BRANCH_STORAGE_PREFIX = 'pp.rfq.lastBranchId.';
// Money is compared in 1/10 000ths so totals like 4,830 − 4,770 come out exact.
const MINOR_UNITS = 10_000;

@Component({
  providers: [provideAppDateAdapter()],
  selector: 'app-rfq-compare',
  standalone: true,
  imports: [
    FormsModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatChipsModule,
    MatDialogModule,
    MatTableModule,
    MatSnackBarModule,
    MatSelectModule,
    MatFormFieldModule,
    MatInputModule,
    MatDatepickerModule,
    MatProgressSpinnerModule,
    MatIconModule,
    TranslatePipe,
    FormatMoneyPipe,
    FormatDatePipe
],
  templateUrl: './compare.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './compare.component.scss',
})
export class CompareComponent implements OnInit, OnChanges {
  readonly embedded = input<boolean>(false);
  readonly rfqId = model<string>('');

  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly rfqApi = inject(RfqApi);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly formatService = inject(FormatService);

  readonly rfqDetail = signal<RfqDetail | null>(null);
  readonly isLoading = signal<boolean>(false);
  readonly responses = signal<RfqResponseComparison[]>([]);
  readonly branches = signal<readonly Branch[]>([]);
  readonly selectedBranchId = signal<string>('');
  readonly requiredByDate = signal<Date | null>(null);
  readonly supplierNames = signal<Record<string, string>>({});
  readonly productNames = signal<Record<string, string>>({});
  readonly errorMessage = signal<string | null>(null);
  readonly guardrails = signal<readonly RfqGuardrail[]>([]);
  readonly currentMembershipId = signal<string | null>(null);
  readonly isSplitting = signal<boolean>(false);
  private splitIdempotencyKey: string | null = null;

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));
  readonly isConverted = computed<boolean>(() => this.rfqDetail()?.rfq.status === 'converted');

  readonly splitEligibility = computed<{
    canSplit: boolean;
    reason: 'needs_two_matched' | 'mixed_currency' | null;
    unmatchedCount: number;
    unmatchedQuotationIds: string[];
  }>(() => {
    const responses = this.responses();
    const nonRefused = responses.filter((r) => r.quotation_status !== 'refused');
    const eligibleReplies = nonRefused.filter(
      (r) => r.quotation_status === 'reviewed' && r.lines.length > 0 && r.lines.every((l) => !l.pending_match),
    );

    let totalUnmatched = 0;
    const unmatchedQuoteIds: string[] = [];
    for (const r of nonRefused) {
      const pendingLines = r.lines.filter((l) => l.pending_match);
      if (pendingLines.length > 0) {
        totalUnmatched += pendingLines.length;
        if (!unmatchedQuoteIds.includes(r.quotation_id)) {
          unmatchedQuoteIds.push(r.quotation_id);
        }
      }
    }

    if (eligibleReplies.length < 2) {
      return {
        canSplit: false,
        reason: 'needs_two_matched',
        unmatchedCount: totalUnmatched,
        unmatchedQuotationIds: unmatchedQuoteIds,
      };
    }

    const currencies = new Set(eligibleReplies.map((r) => this.responseCurrency(r)).filter(Boolean));
    if (currencies.size > 1) {
      return {
        canSplit: false,
        reason: 'mixed_currency',
        unmatchedCount: 0,
        unmatchedQuotationIds: [],
      };
    }

    return {
      canSplit: true,
      reason: null,
      unmatchedCount: 0,
      unmatchedQuotationIds: [],
    };
  });

  formatQuantity(value: string | number): string { return this.formatService.formatExactQuantity(value); }

  responseTotal(response: RfqResponseComparison): number {
    return response.lines.reduce((sum, line) => {
      const qty = Number(line.quoted_quantity) || 0;
      const price = Number(line.quoted_unit_price_amount) || 0;
      return sum + (qty * price);
    }, 0);
  }

  responseCurrency(response: RfqResponseComparison): string {
    return response.lines[0]?.quoted_unit_price_currency || '';
  }

  readonly convertedPurchaseRequestId = computed<string | null>(() => {
    const ids = this.rfqDetail()?.converted_purchase_request_ids;
    return ids && ids.length === 1 ? ids[0] : null;
  });

  // Replies whose quoted totals can be compared for «Lowest total»: fully matched, one
  // currency, the same products in the same quantities.
  private readonly comparableResponses = computed<RfqResponseComparison[] | null>(() => {
    const all = this.responses();
    const eligible = all.filter(
      (r) => r.quotation_status !== 'refused' && r.lines.length > 0 && r.lines.every((l) => !l.pending_match),
    );
    if (eligible.length < 2) {
      return null;
    }
    const currencies = new Set(eligible.map((r) => this.responseCurrency(r)).filter(Boolean));
    if (currencies.size !== 1) {
      return null;
    }

    const getProductQuantities = (response: RfqResponseComparison): Map<string, number> | null => {
      const map = new Map<string, number>();
      for (const line of response.lines) {
        if (!line.workspace_product_id) {
          return null;
        }
        const qty = Number(line.quoted_quantity);
        if (Number.isNaN(qty)) {
          return null;
        }
        map.set(line.workspace_product_id, (map.get(line.workspace_product_id) ?? 0) + qty);
      }
      return map;
    };

    const baselineMap = getProductQuantities(eligible[0]);
    if (!baselineMap || baselineMap.size === 0) {
      return null;
    }

    for (let i = 1; i < eligible.length; i++) {
      const currentMap = getProductQuantities(eligible[i]);
      if (!currentMap || currentMap.size !== baselineMap.size) {
        return null;
      }
      for (const [productId, baselineQty] of baselineMap.entries()) {
        const currentQty = currentMap.get(productId);
        if (currentQty === undefined || Math.abs(currentQty - baselineQty) > 1e-9) {
          return null;
        }
      }
    }

    return eligible;
  });

  readonly lowestTotalResponseIds = computed<Set<string>>(() => {
    const eligible = this.comparableResponses();
    if (!eligible) {
      return new Set<string>();
    }

    const totals = eligible.map((r) => ({ id: r.id, total: this.responseTotal(r) }));
    const minTotal = Math.min(...totals.map((t) => t.total));
    const ids = new Set<string>();
    for (const t of totals) {
      if (Math.abs(t.total - minTotal) < 1e-9) {
        ids.add(t.id);
      }
    }
    return ids;
  });

  hasLowestTotal(response: RfqResponseComparison): boolean {
    return this.lowestTotalResponseIds().has(response.id);
  }

  // Each eligible reply's landed cost for the RFQ's quantity of every RFQ product, in
  // 1/10 000ths of the currency: the figures the RFQ split prices from (rfq_landed_costs).
  // Null unless at least two fully matched replies price every RFQ product in one currency.
  private readonly landedCostGrid = computed<{
    replies: RfqResponseComparison[];
    costs: Map<string, Map<string, number>>;
    productIds: string[];
    currency: string;
  } | null>(() => {
    const productIds = [...new Set((this.rfqDetail()?.lines ?? []).map((l) => l.workspace_product_id))];
    if (productIds.length === 0) {
      return null;
    }
    const replies = this.responses().filter(
      (r) => r.quotation_status !== 'refused' && r.lines.length > 0 && r.lines.every((l) => !l.pending_match),
    );
    if (replies.length < 2) {
      return null;
    }

    const currencies = new Set<string>();
    const costs = new Map<string, Map<string, number>>();
    for (const reply of replies) {
      const byProduct = new Map<string, number>();
      for (const cost of reply.rfq_landed_costs ?? []) {
        const amount = Number(cost.total_amount);
        if (Number.isNaN(amount)) {
          return null;
        }
        byProduct.set(cost.workspace_product_id, Math.round(amount * MINOR_UNITS));
        currencies.add(cost.total_currency);
      }
      if (productIds.some((id) => !byProduct.has(id))) {
        return null;
      }
      costs.set(reply.id, byProduct);
    }
    if (currencies.size !== 1) {
      return null;
    }
    return { replies, costs, productIds, currency: [...currencies][0] };
  });

  private landedCost(replyId: string, productId: string): number {
    return this.landedCostGrid()?.costs.get(replyId)?.get(productId) ?? 0;
  }

  readonly lowestLinePriceKeys = computed<Set<string>>(() => {
    const grid = this.landedCostGrid();
    const keys = new Set<string>();
    if (!grid) {
      return keys;
    }
    for (const productId of grid.productIds) {
      const amounts = grid.replies.map((r) => this.landedCost(r.id, productId));
      const min = Math.min(...amounts);
      if (amounts.every((amount) => amount === min)) {
        continue;
      }
      grid.replies.forEach((reply, i) => {
        if (amounts[i] === min) {
          keys.add(`${reply.id}:${productId}`);
        }
      });
    }
    return keys;
  });

  isLowestLinePrice(response: RfqResponseComparison, line: RfqResponseLineComparison): boolean {
    if (!line.workspace_product_id) {
      return false;
    }
    return this.lowestLinePriceKeys().has(`${response.id}:${line.workspace_product_id}`);
  }

  // The cheapest single supplier against the cheapest supplier per line, both from landed costs.
  // A supplier's delivery fee, minimum order or tiers can cancel that saving, and only the split
  // itself prices them, so the hint stays hidden when any eligible supplier has such terms.
  readonly splitSaving = computed<{ amount: number; currency: string } | null>(() => {
    const grid = this.landedCostGrid();
    if (!grid || grid.replies.some((r) => r.supplier_terms_apply)) {
      return null;
    }
    const singleTotals = grid.replies.map((r) =>
      grid.productIds.reduce((sum, productId) => sum + this.landedCost(r.id, productId), 0),
    );
    const splitTotal = grid.productIds.reduce(
      (sum, productId) => sum + Math.min(...grid.replies.map((r) => this.landedCost(r.id, productId))),
      0,
    );
    const saving = Math.min(...singleTotals) - splitTotal;
    return saving > 0 ? { amount: saving / MINOR_UNITS, currency: grid.currency } : null;
  });

  readonly splitSavingMoney = computed<string>(() => {
    const saving = this.splitSaving();
    return saving ? this.formatService.formatMoney(saving) : '';
  });

  unmatchedCount(response: RfqResponseComparison): number {
    return response.lines.filter((l) => l.pending_match).length;
  }

  matchLinesLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    if (count === 1) {
      return this.translate.instant('rfq.compare.matchLine');
    }
    if (count === 2 && locale.startsWith('ar')) {
      return this.translate.instant('rfq.compare.matchLinesTwo');
    }
    return this.translate.instant('rfq.compare.matchLines', {
      count: this.formatService.formatNumber(count),
    });
  }

  readonly displayedColumns = ['product', 'quantity', 'unitPrice', 'totalValue'];

  ngOnInit(): void {
    this.api.members().subscribe(({ items }) => {
      const email = this.session.currentMember()?.email;
      this.currentMembershipId.set(items.find((member) => member.email === email)?.id ?? null);
    });
    if (!this.rfqId()) {
      this.route.paramMap.subscribe((params) => {
        const id = params.get('id');
        if (id) {
          this.rfqId.set(id);
          this.loadData(id);
        }
      });
    }

    this.loadBranches();
  }

  ngOnChanges(): void {
    const id = this.rfqId();
    if (id && this.rfqDetail()?.rfq.id !== id) {
      this.loadData(id);
    }
  }

  loadData(rfqId: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.rfqApi.getRfq?.(rfqId)?.subscribe({
      next: (detail) => {
        this.rfqDetail.set(detail);
        const parsedNeededBy = parseIsoDateLocal(detail.rfq.needed_by_date);
        if (parsedNeededBy) {
          this.requiredByDate.set(parsedNeededBy);
        }
        this.applyBranchPreselection();
      },
      error: () => this.rfqDetail.set(null),
    });

    this.rfqApi.listResponses(rfqId).subscribe({
      next: (res) => {
        this.responses.set(res.items);
        if (this.session.hasRole('owner')) {
          this.rfqApi.listGuardrails().subscribe({
            next: (guardrails) => this.guardrails.set(guardrails),
          });
        }
        this.resolveSuppliers();
        this.resolveProducts();
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.responses.set([]);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.errorMessage.set(apiError?.message ?? err.message);
        } else {
          this.errorMessage.set(this.translate.instant('rfq.compare.loadError'));
        }
      },
    });
  }

  onEditDraft(): void {
    const id = this.rfqId();
    if (!id) return;
    if (!this.isCreator()) return;
    this.router.navigate(['/rfq', id, 'edit']);
  }

  isCreator(): boolean {
    return this.rfqDetail()?.rfq.created_by_membership_id === this.currentMembershipId();
  }

  onSendDraft(): void {
    if (!this.isCreator()) return;
    const detail = this.rfqDetail();
    const id = this.rfqId();
    if (!id) return;
    const recipientCount = detail?.recipients.length ?? 0;

    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.history.confirmSendTitle',
        messageKey: 'rfq.history.confirmSendMessage',
        messageParams: { count: recipientCount },
        confirmKey: 'rfq.history.confirmSendButton',
        cancelKey: 'rfq.history.cancelSendButton',
        isDestructive: false,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.rfqApi.sendRfq(id).subscribe({
          next: (res) => {
            const total = res.recipients.length;
            const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
            const key = sent === total && total > 0 ? 'rfq.history.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
            const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
            this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
            if (sent === total && total > 0) this.router.navigate(['/rfq/history']);
            else this.loadData(id);
          },
          error: (err: unknown) => {
            const key = err instanceof HttpErrorResponse && err.status === 403 ? 'rfq.creatorOnly' : 'rfq.history.sendError';
            this.snackBar.open(
              this.translate.instant(key),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          },
        });
      }
    });
  }

  guardrailLabel(guardrailId: string): string {
    const guardrail = this.guardrails().find((item) => item.id === guardrailId);
    if (!guardrail) {
      return this.translate.instant('rfq.compare.guardrail');
    }
    return this.translate.instant('rfq.compare.guardrailLabel', {
      money: this.formatService.formatMoney({
        amount: guardrail.max_order_value_amount,
        currency: guardrail.max_order_value_currency,
      }),
    });
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

  onBranchChange(branchId: string): void {
    this.selectedBranchId.set(branchId);
    this.saveBranchId(branchId);
  }

  resolveSuppliers(): void {
    this.api.suppliers({ limit: 100 }).subscribe({
      next: (res) => {
        const names: Record<string, string> = { ...this.supplierNames() };
        for (const s of res.items) {
          names[s.id] = s.name;
        }
        this.supplierNames.set(names);
      },
    });
  }

  resolveProducts(): void {
    this.api.products({ limit: 100 }).subscribe({
      next: (res) => {
        const names: Record<string, string> = { ...this.productNames() };
        for (const p of res.items) {
          names[p.id] = p.tenant_name;
        }
        this.productNames.set(names);
      },
    });
  }

  isEligible(response: RfqResponseComparison): boolean {
    return response.quotation_status !== 'refused' && response.lines.every((l) => !l.pending_match);
  }

  canPrepare(response: RfqResponseComparison): boolean {
    return (
      !this.isConverted() &&
      this.isEligible(response) &&
      Boolean(this.selectedBranchId()) &&
      Boolean(this.requiredByDate())
    );
  }

  prepareRequest(response: RfqResponseComparison): void {
    if (this.isConverted()) return;
    if (response.quotation_status === 'refused') return;
    if (!this.isEligible(response)) {
      this.snackBar.open(
        this.translate.instant('rfq.compare.cannotPreparePending'),
        this.translate.instant('rfq.history.dismiss'),
        { duration: 3000 },
      );
      return;
    }

    const branchId = this.selectedBranchId();
    if (!branchId) {
      this.snackBar.open(
        this.translate.instant('rfq.compare.branchRequired'),
        this.translate.instant('rfq.history.dismiss'),
        { duration: 3000 },
      );
      return;
    }

    this.saveBranchId(branchId);

    const reqDate = this.requiredByDate();
    const requiredBy =
      (reqDate ? toIsoDate(reqDate) : '') ||
      this.rfqDetail()?.rfq.needed_by_date ||
      toIsoDate(new Date());

    const payload = {
      rfq_response_id: response.id,
      branch_id: branchId,
      required_by_date: requiredBy,
    };

    this.rfqApi.prepareRequest(this.rfqId(), payload).subscribe({
      next: (res) => {
        const snackRef = this.snackBar.open(
          this.translate.instant('rfq.compare.prepareSuccess'),
          this.translate.instant('rfq.compare.openDraft'),
          { duration: 5000 },
        );
        let navigated = false;
        const navigateToDraft = () => {
          if (!navigated && res?.purchase_request_id) {
            navigated = true;
            this.router.navigate(['/requests', res.purchase_request_id]);
          }
        };
        snackRef?.onAction?.().subscribe(() => {
          this.router.navigate(['/requests', res.purchase_request_id]);
        });
        navigateToDraft();
      },
      error: (err: unknown) => {
        if (err instanceof HttpErrorResponse && err.status === 409) {
          const reason = (err.error as ApiError | undefined)?.details?.['reason'];
          if (reason === 'rfq_already_converted') {
            this.snackBar.open(
              this.translate.instant('rfq.compare.alreadyConverted'),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
            const id = this.rfqId();
            if (id) {
              this.loadData(id);
            }
            return;
          }
        }
        const message =
          err instanceof HttpErrorResponse
            ? ((err.error as ApiError | undefined)?.message ??
              this.translate.instant('rfq.compare.prepareError'))
            : this.translate.instant('rfq.compare.prepareError');
        this.snackBar.open(
          message,
          this.translate.instant('rfq.history.dismiss'),
          { duration: 5000 },
        );
      },
    });
  }

  splitRfq(): void {
    if (!this.splitEligibility().canSplit || !this.isWriter() || this.isSplitting()) return;
    const id = this.rfqId();
    if (!id) return;

    this.isSplitting.set(true);
    if (!this.splitIdempotencyKey) {
      this.splitIdempotencyKey = crypto.randomUUID();
    }

    this.rfqApi.splitRfq(id, this.splitIdempotencyKey).subscribe({
      next: (job) => {
        this.isSplitting.set(false);
        this.splitIdempotencyKey = null;
        this.router.navigate(['/offers/basket-split', job.id]);
      },
      error: (err: unknown) => {
        this.isSplitting.set(false);
        if (err instanceof HttpErrorResponse && err.status === 409) {
          const reason = (err.error as ApiError | undefined)?.details?.['reason'];
          if (reason === 'rfq_already_converted') {
            this.snackBar.open(
              this.translate.instant('rfq.compare.alreadyConverted'),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          } else if (reason === 'mixed_currency') {
            this.snackBar.open(
              this.translate.instant('rfq.compare.differentCurrencies'),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          } else if (reason === 'not_enough_replies') {
            this.snackBar.open(
              this.translate.instant('rfq.compare.needsTwoMatched'),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          } else {
            this.snackBar.open(
              (err.error as ApiError | undefined)?.message || this.translate.instant('rfq.compare.splitError'),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          }
        } else {
          this.snackBar.open(
            this.translate.instant('rfq.compare.splitError'),
            this.translate.instant('rfq.history.dismiss'),
            { duration: 5000 },
          );
        }
      },
    });
  }

  private getTenantStorageKey(): string {
    const tenantId =
      this.session.tenant?.()?.id ??
      this.rfqDetail()?.rfq.tenant_id ??
      'default';
    return `${LAST_BRANCH_STORAGE_PREFIX}${tenantId}`;
  }

  private readSavedBranchId(): string | null {
    try {
      return localStorage.getItem(this.getTenantStorageKey());
    } catch {
      return null;
    }
  }

  private saveBranchId(branchId: string): void {
    if (!branchId) {
      return;
    }
    try {
      localStorage.setItem(this.getTenantStorageKey(), branchId);
    } catch {
      // Ignore storage access errors
    }
  }

  private applyBranchPreselection(): void {
    const items = this.branches();
    if (items.length === 0) {
      this.selectedBranchId.set('');
      return;
    }
    if (items.length === 1) {
      this.selectedBranchId.set(items[0].id);
      return;
    }
    const saved = this.readSavedBranchId();
    if (saved && items.some((b) => b.id === saved)) {
      this.selectedBranchId.set(saved);
      return;
    }
    this.selectedBranchId.set('');
  }
}
