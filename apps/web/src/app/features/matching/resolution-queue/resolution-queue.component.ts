import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSortModule, type Sort } from '@angular/material/sort';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  BaseUnit,
  CatalogueRefreshReview,
  MatchCorrectionRequest,
  MatchQueueItem,
  MatchTaskPriority,
  MatchTaskReason,
  MatchTaskStatus,
  QuotationMatchSummary,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { UnitLabelPipe } from '../../../core/format/unit-label';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';
import { CorrectMatchDialogComponent, FALLBACK_BASE_UNITS } from '../match-resolution/correct-match-dialog.component';
import { formatSweptLinesMessage, appendSweptMessage } from '../matching-api';

type MatchTaskSortBy = 'created_at' | 'priority' | 'status';
type MatchTaskSortOrder = 'asc' | 'desc';

export interface QuotationTaskGroup {
  readonly quotation: QuotationMatchSummary;
  readonly tasks: readonly MatchQueueItem[];
}

@Component({
  selector: 'app-resolution-queue',
  standalone: true,
  providers: [provideAppDateAdapter()],
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatChipsModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatSortModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatDialogModule,
    MatSnackBarModule,
    TranslatePipe,
    UnitLabelPipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './resolution-queue.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './resolution-queue.component.scss',
})
export class ResolutionQueueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly tasks = signal<MatchQueueItem[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly statusFilter = signal<MatchTaskStatus | 'all'>('open');
  readonly priorityFilter = signal<MatchTaskPriority | 'all'>('all');
  readonly reasonFilter = signal<MatchTaskReason | 'all'>('all');
  readonly searchQuery = signal<string>('');
  readonly dateFrom = signal<string | null>(null);
  readonly dateTo = signal<string | null>(null);
  readonly dateFromModel = computed(() => parseIsoDateLocal(this.dateFrom()));
  readonly dateToModel = computed(() => parseIsoDateLocal(this.dateTo()));
  readonly sortBy = signal<MatchTaskSortBy>('created_at');
  readonly sortOrder = signal<MatchTaskSortOrder>('desc');
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly exactMatchCount = signal<number>(0);
  readonly isConfirmingExact = signal<boolean>(false);
  readonly exactConfirmedCount = signal<number | null>(null);
  readonly exactSkippedCount = signal<number>(0);
  readonly refreshReviews = signal<CatalogueRefreshReview[]>([]);
  readonly isLoadingRefreshReviews = signal<boolean>(true);
  readonly refreshReviewDecisionId = signal<string | null>(null);
  readonly quotationId = signal<string | null>(null);
  readonly baseUnits = signal<BaseUnit[]>([]);
  readonly collapsedGroupIds = signal<ReadonlySet<string>>(new Set<string>());
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;
  private latestLoadRequestId = 0;
  private exactConfirmKey: string | null = null;

  isWriter(): boolean {
    return this.session.hasRole('owner', 'buyer');
  }
  readonly hasActiveFilters = computed<boolean>(
    () =>
      this.quotationId() !== null ||
      this.statusFilter() !== 'open' ||
      this.priorityFilter() !== 'all' ||
      this.reasonFilter() !== 'all' ||
      this.searchQuery().trim().length > 0 ||
      this.dateFrom() !== null ||
      this.dateTo() !== null,
  );

  readonly groups = computed<readonly QuotationTaskGroup[]>(() => {
    const grouped = new Map<string, MatchQueueItem[]>();
    for (const task of this.tasks()) {
      const items = grouped.get(task.quotation.id) ?? [];
      items.push(task);
      grouped.set(task.quotation.id, items);
    }
    return Array.from(grouped.values(), (tasks) => ({ quotation: tasks[0].quotation, tasks }));
  });

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    this.quotationId.set(qp.get('quotation_id'));
    const status = qp.get('status') as MatchTaskStatus | 'all' | null;
    if (status && ['open', 'in_progress', 'resolved', 'auto_accepted', 'all'].includes(status)) {
      this.statusFilter.set(status);
    }
    const priority = qp.get('priority') as MatchTaskPriority | 'all' | null;
    if (priority && ['all', 'low', 'normal', 'high'].includes(priority)) {
      this.priorityFilter.set(priority);
    }
    const reason = qp.get('reason') as MatchTaskReason | 'all' | null;
    if (reason && ['all', 'low_confidence', 'close_candidates', 'fuzzy_match_review', 'no_candidate', 'alias_conflict', 'auto_accepted'].includes(reason)) {
      this.reasonFilter.set(reason);
    }
    const search = qp.get('search');
    if (search) this.searchQuery.set(search);
    const dateFrom = qp.get('date_from');
    if (dateFrom) this.dateFrom.set(dateFrom);
    const dateTo = qp.get('date_to');
    if (dateTo) this.dateTo.set(dateTo);
    const sortBy = qp.get('sort_by') as MatchTaskSortBy | null;
    if (sortBy && ['created_at', 'priority', 'status'].includes(sortBy)) {
      this.sortBy.set(sortBy);
    }
    const sortOrder = qp.get('sort_order') as MatchTaskSortOrder | null;
    if (sortOrder && ['asc', 'desc'].includes(sortOrder)) {
      this.sortOrder.set(sortOrder);
    }
    this.loadBaseUnits();
    this.loadTasks();
    this.loadRefreshReviews();
    this.loadExactMatchCount();
  }

  private loadBaseUnits(): void {
    this.api.baseUnits().subscribe({
      next: (res) => this.baseUnits.set(res.items.length > 0 ? res.items : FALLBACK_BASE_UNITS),
      error: () => {
        this.baseUnits.set(FALLBACK_BASE_UNITS);
      },
    });
  }

  loadExactMatchCount(): void {
    if (!this.isWriter()) return;
    this.api.getExactMatchCount().subscribe({
      next: (res) => this.exactMatchCount.set(res.count),
      error: (err: unknown) => {
        this.exactMatchCount.set(0);
        this.handleError(err);
      },
    });
  }

  /** Human-triggered: each exact-name match gets an ordinary buyer decision and learns an alias. */
  confirmAllExact(): void {
    if (!this.isWriter() || this.isConfirmingExact()) return;
    this.isConfirmingExact.set(true);
    this.exactConfirmedCount.set(null);
    // One key per logical attempt: a retry after a lost response replays the same frozen batch.
    this.exactConfirmKey ??= crypto.randomUUID();
    this.api.confirmExactMatches(this.exactConfirmKey).subscribe({
      next: (res) => {
        this.isConfirmingExact.set(false);
        this.exactConfirmKey = null;
        this.exactConfirmedCount.set(res.confirmed);
        this.exactSkippedCount.set(res.skipped);
        this.loadExactMatchCount();
        this.loadTasks();

        const baseMsg = this.translate.instant('matching.queue.exact.confirmed', { count: res.confirmed });
        const swept = formatSweptLinesMessage(this.translate, res.lines_matched_by_same_wording);
        const msg = swept ? appendSweptMessage(baseMsg, swept) : baseMsg;
        this.snackBar.open(msg, undefined, { duration: 4000 });
      },
      error: (err: unknown) => {
        this.isConfirmingExact.set(false);
        this.handleError(err);
      },
    });
  }

  loadRefreshReviews(): void {
    this.isLoadingRefreshReviews.set(true);
    this.api.listCatalogueRefreshReviews({ status: 'pending_review' }).subscribe({
      next: (res) => {
        this.refreshReviews.set(res.items);
        this.isLoadingRefreshReviews.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingRefreshReviews.set(false);
        this.handleError(err);
      },
    });
  }

  decideRefreshReview(review: CatalogueRefreshReview, decision: 'approve' | 'reject'): void {
    if (!this.isWriter() || this.refreshReviewDecisionId()) return;
    this.refreshReviewDecisionId.set(review.id);
    const request = decision === 'approve'
      ? this.api.approveCatalogueRefreshReview(review.id)
      : this.api.rejectCatalogueRefreshReview(review.id);
    request.subscribe({
      next: () => {
        this.refreshReviews.update((reviews) => reviews.filter((item) => item.id !== review.id));
        this.refreshReviewDecisionId.set(null);
      },
      error: (err: unknown) => {
        this.refreshReviewDecisionId.set(null);
        this.handleError(err);
      },
    });
  }

  loadTasks(): void {
    const requestId = ++this.latestLoadRequestId;
    this.isLoading.set(true);
    this.isLoadingMore.set(false);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.nextCursor.set(null);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const reason = this.reasonFilter();
    const search = this.sanitizedSearch();

    this.api
      .getMatchTasks({
        status,
        priority: priority === 'all' ? undefined : priority,
        reason: reason === 'all' ? undefined : reason,
        quotation_id: this.quotationId() ?? undefined,
        search,
        date_from: this.dateFrom() ?? undefined,
        date_to: this.dateTo() ?? undefined,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          if (requestId !== this.latestLoadRequestId) return;
          this.tasks.set(res.items);
          this.nextCursor.set(res.next_cursor);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          if (requestId !== this.latestLoadRequestId) return;
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor) return;

    const requestId = this.latestLoadRequestId;
    this.isLoadingMore.set(true);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const reason = this.reasonFilter();
    const search = this.sanitizedSearch();

    this.api
      .getMatchTasks({
        cursor,
        status,
        priority: priority === 'all' ? undefined : priority,
        reason: reason === 'all' ? undefined : reason,
        quotation_id: this.quotationId() ?? undefined,
        search,
        date_from: this.dateFrom() ?? undefined,
        date_to: this.dateTo() ?? undefined,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          if (requestId !== this.latestLoadRequestId) return;
          this.tasks.set([...this.tasks(), ...res.items]);
          this.nextCursor.set(res.next_cursor);
          this.isLoadingMore.set(false);
        },
        error: (err: unknown) => {
          if (requestId !== this.latestLoadRequestId) return;
          this.isLoadingMore.set(false);
          this.handleError(err);
        },
      });
  }

  onStatusChange(status: MatchTaskStatus | 'all'): void {
    this.statusFilter.set(status);
    this.syncQueryParams();
    this.loadTasks();
  }

  onPriorityChange(priority: MatchTaskPriority | 'all'): void {
    this.priorityFilter.set(priority);
    this.syncQueryParams();
    this.loadTasks();
  }

  onReasonChange(reason: MatchTaskReason | 'all'): void {
    this.reasonFilter.set(reason);
    this.syncQueryParams();
    this.loadTasks();
  }

  onSearchChange(value: string): void {
    this.searchQuery.set(value);
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
    }
    this.searchDebounce = setTimeout(() => {
      this.syncQueryParams();
      this.loadTasks();
    }, 300);
  }

  onDateFromChange(value: Date | string | null): void {
    const next = toIsoDateOrNull(value);
    if (this.dateFrom() !== next) {
      this.dateFrom.set(next);
      this.syncQueryParams();
      this.loadTasks();
    }
  }

  onDateToChange(value: Date | string | null): void {
    const next = toIsoDateOrNull(value);
    if (this.dateTo() !== next) {
      this.dateTo.set(next);
      this.syncQueryParams();
      this.loadTasks();
    }
  }

  onSortChange(sort: Sort): void {
    if (this.isSortableColumn(sort.active)) {
      this.sortBy.set(sort.active);
    }
    this.sortOrder.set(sort.direction === 'asc' ? 'asc' : 'desc');
    this.syncQueryParams();
    this.loadTasks();
  }

  clearFilters(): void {
    this.quotationId.set(null);
    this.statusFilter.set('open');
    this.priorityFilter.set('all');
    this.reasonFilter.set('all');
    this.searchQuery.set('');
    this.dateFrom.set(null);
    this.dateTo.set(null);
    this.syncQueryParams();
    this.loadTasks();
  }

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  detailQueryParams(quotationId: string): Record<string, string> {
    const qp: Record<string, string> = { quotation_id: quotationId };
    if (this.statusFilter() !== 'open') qp['status'] = this.statusFilter();
    if (this.priorityFilter() !== 'all') qp['priority'] = this.priorityFilter();
    if (this.reasonFilter() !== 'all') qp['reason'] = this.reasonFilter();
    const search = this.searchQuery().trim();
    if (search) qp['search'] = search;
    if (this.dateFrom()) qp['date_from'] = this.dateFrom()!;
    if (this.dateTo()) qp['date_to'] = this.dateTo()!;
    if (this.sortBy() !== 'created_at') qp['sort_by'] = this.sortBy();
    if (this.sortOrder() !== 'desc') qp['sort_order'] = this.sortOrder();
    return qp;
  }

  truncateId(id: string): string {
    return id.slice(0, 8);
  }

  isGroupCollapsed(quotationId: string): boolean {
    return this.collapsedGroupIds().has(quotationId);
  }

  toggleGroup(quotationId: string): void {
    this.collapsedGroupIds.update((collapsedGroupIds) => {
      const next = new Set(collapsedGroupIds);
      if (next.has(quotationId)) {
        next.delete(quotationId);
      } else {
        next.add(quotationId);
      }
      return next;
    });
  }

  ageLabel(createdAt: string): string {
    const created = new Date(createdAt);
    const diffMs = Date.now() - created.getTime();
    if (isNaN(created.getTime()) || diffMs < 60 * 60 * 1000) {
      return this.translate.instant('quotations.queue.age.justNow');
    }

    const diffHours = Math.floor(diffMs / (60 * 60 * 1000));
    if (diffHours < 24) {
      return this.translate.instant('quotations.queue.age.hoursAgo', { count: diffHours });
    }

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) {
      return this.translate.instant('quotations.queue.age.daysAgo', { count: diffDays });
    }
    if (diffDays < 30) {
      return this.translate.instant('quotations.queue.age.weeksAgo', {
        count: Math.floor(diffDays / 7),
      });
    }
    return this.translate.instant('quotations.queue.age.monthsAgo', {
      count: Math.floor(diffDays / 30),
    });
  }

  private syncQueryParams(): void {
    const qp: Record<string, string> = {};
    if (this.quotationId()) qp['quotation_id'] = this.quotationId()!;
    if (this.statusFilter() !== 'open') qp['status'] = this.statusFilter();
    if (this.priorityFilter() !== 'all') qp['priority'] = this.priorityFilter();
    if (this.reasonFilter() !== 'all') qp['reason'] = this.reasonFilter();
    const search = this.searchQuery().trim();
    if (search) qp['search'] = search;
    if (this.dateFrom()) qp['date_from'] = this.dateFrom()!;
    if (this.dateTo()) qp['date_to'] = this.dateTo()!;
    if (this.sortBy() !== 'created_at') qp['sort_by'] = this.sortBy();
    if (this.sortOrder() !== 'desc') qp['sort_order'] = this.sortOrder();
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: qp,
      replaceUrl: true,
    });
  }

  private sanitizedSearch(): string | undefined {
    const search = this.searchQuery().trim();
    return search ? search : undefined;
  }

  rfqPositionForTask(task: MatchQueueItem): number | null {
    return task.top_candidate?.rfq_position ?? null;
  }

  openCorrectMatchDialog(task: MatchQueueItem): void {
    if (!this.isWriter()) return;
    this.api.getMatchTaskForLine(task.quotation_line.id).subscribe({
      next: (fullTask) => {
        const decisionId = fullTask.decision?.id ?? task.decision?.id;
        if (!decisionId) {
          this.errorMessage.set(this.translate.instant('matching.resolution.errors.decisionChanged'));
          return;
        }
        const baseUnits = this.baseUnits().length > 0 ? this.baseUnits() : FALLBACK_BASE_UNITS;
        const dialogRef = this.dialog.open(CorrectMatchDialogComponent, {
          width: '640px',
          data: {
            line: fullTask.quotation_line,
            candidates: fullTask.candidates,
            expectedCurrentDecisionId: decisionId,
            currentCandidateId: fullTask.decision?.selected_match_candidate_id,
            baseUnits,
            quotationSupplierId: fullTask.quotation?.supplier_id ?? null,
          },
        });
        dialogRef.afterClosed().subscribe((request: MatchCorrectionRequest | null | undefined) => {
          if (!request) return;
          const key = crypto.randomUUID();
          this.api.correctMatch(task.quotation_line.id, request, key).subscribe({
            next: (res) => {
              const baseMsg = this.translate.instant('matching.resolution.actions.correctSuccess');
              const swept = formatSweptLinesMessage(this.translate, res.lines_matched_by_same_wording);
              const msg = swept ? appendSweptMessage(baseMsg, swept) : baseMsg;
              this.snackBar.open(
                msg,
                undefined,
                { duration: 4000 },
              );
              this.loadTasks();
            },
            error: (err: unknown) => {
              this.handleCorrectionError(err);
            },
          });
        });
      },
      error: (err: unknown) => {
        this.handleError(err);
      },
    });
  }

  private handleCorrectionError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);

      if (err.status === 409) {
        const details = apiError?.details as Record<string, unknown> | undefined;
        const reason = details?.['reason'];

        if (reason === 'line_on_purchase_request') {
          const prId = String(details?.['purchase_request_id'] ?? '');
          const shortId = prId ? prId.slice(0, 8) : '';
          this.errorMessage.set(
            this.translate.instant('matching.resolution.errors.lineOnPurchaseRequest', { shortId }),
          );
          return;
        }

        if (reason === 'decision_changed') {
          this.errorMessage.set(
            this.translate.instant('matching.resolution.errors.decisionChanged'),
          );
          return;
        }
      }
    }
    this.handleError(err);
  }

  private isSortableColumn(value: string): value is MatchTaskSortBy {
    return ['created_at', 'priority', 'status'].includes(value);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('matching.resolution.errors.genericError'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('matching.resolution.errors.genericError'));
  }
}
