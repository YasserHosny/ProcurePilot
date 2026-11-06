import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSortModule, type Sort } from '@angular/material/sort';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink, convertToParamMap, type ParamMap } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription, of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, QuotationStatus, ReviewTask, ReviewTaskPriority, ReviewTaskReason, ReviewTaskStatus, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';

type ReviewTaskSortBy = 'created_at' | 'stated_total' | 'priority' | 'status';
type ReviewTaskSortOrder = 'asc' | 'desc';

@Component({
  selector: 'app-review-queue',
  standalone: true,
  providers: [provideAppDateAdapter()],
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatCheckboxModule,
    MatIconModule,
    MatInputModule,
    MatChipsModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatMenuModule,
    MatSelectModule,
    MatSnackBarModule,
    MatSortModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    RoleDirective,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './review-queue.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './review-queue.component.scss',
})
export class ReviewQueueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly tasks = signal<ReviewTask[]>([]);
  readonly selectedTaskIds = signal<Set<string>>(new Set());
  readonly nextCursor = signal<string | null>(null);
  readonly statusFilter = signal<ReviewTaskStatus | 'all'>('open');
  readonly priorityFilter = signal<ReviewTaskPriority | 'all'>('all');
  readonly supplierFilter = signal<string | null>(null);
  readonly reasonFilter = signal<ReviewTaskReason | 'all'>('all');
  readonly lifecycleFilter = signal<QuotationStatus | 'all'>('all');
  readonly suppliers = signal<Supplier[]>([]);
  readonly supplierLabel = computed(() =>
    this.suppliers().find((supplier) => supplier.id === this.supplierFilter())?.name ?? this.supplierFilter(),
  );
  readonly reasons: readonly ReviewTaskReason[] = [
    'ready_to_authorise', 'low_confidence', 'arithmetic_mismatch', 'read_failure',
    'review_required', 'no_supplier_match', 'currency_unresolved', 'date_unparsed',
    'merged_line_items', 'line_count_mismatch', 'total_unverified',
  ];
  readonly lifecycles: readonly QuotationStatus[] = [
    'pending', 'extracting', 'extracted', 'in_review', 'reviewed', 'refused',
  ];
  readonly searchQuery = signal<string>('');
  readonly dateFrom = signal<string | null>(null);
  readonly dateTo = signal<string | null>(null);
  readonly dateFromModel = computed(() => parseIsoDateLocal(this.dateFrom()));
  readonly dateToModel = computed(() => parseIsoDateLocal(this.dateTo()));
  readonly dateRangeInvalid = computed(() => {
    const from = this.dateFrom();
    const to = this.dateTo();
    return from !== null && to !== null && from > to;
  });
  readonly sortBy = signal<ReviewTaskSortBy>('created_at');
  readonly sortOrder = signal<ReviewTaskSortOrder>('desc');
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly archivingTaskId = signal<string | null>(null);
  readonly isBulkArchiving = signal<boolean>(false);
  readonly isBulkRefusing = signal<boolean>(false);
  readonly isBulkReprioritising = signal<boolean>(false);
  readonly bulkPriorityTarget = signal<ReviewTaskPriority | null>(null);
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;
  private loadTasksSub: Subscription | null = null;
  private loadMoreSub: Subscription | null = null;
  private isInitialLoad = true;
  private queryParamSub: Subscription | null = null;

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));
  readonly hasSelection = computed<boolean>(() => this.selectedTaskIds().size > 0);
  readonly allSelected = computed<boolean>(
    () => this.tasks().length > 0 && this.selectedTaskIds().size === this.tasks().length,
  );
  readonly hasActiveFilters = computed<boolean>(
    () =>
      this.statusFilter() !== 'open' ||
      this.priorityFilter() !== 'all' ||
      this.supplierFilter() !== null ||
      this.reasonFilter() !== 'all' ||
      this.lifecycleFilter() !== 'all' ||
      this.searchQuery().trim().length > 0 ||
      this.dateFrom() !== null ||
      this.dateTo() !== null,
  );
  readonly resultCountLabel = computed<string>(() => this.resultCountText());

  readonly displayedColumns = computed<readonly string[]>(() =>
    this.isWriter()
      ? [
          'select',
          'quotation_id',
          'supplier_name',
          'reason',
          'priority',
          'status',
          'stated_total',
          'created_at',
          'age',
          'actions',
        ]
      : [
          'quotation_id',
          'supplier_name',
          'reason',
          'priority',
          'status',
          'stated_total',
          'created_at',
          'age',
          'actions',
        ],
  );

  ngOnInit(): void {
    this.loadSuppliers();
    this.queryParamSub?.unsubscribe();
    const queryParamMap$ =
      this.route.queryParamMap ?? of(this.route.snapshot?.queryParamMap ?? convertToParamMap({}));
    this.queryParamSub = queryParamMap$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        this.handleQueryParamChange(params);
      });
  }

  // The supplier endpoint has no name sort: load up to 20 pages and sort by name here.
  private loadSuppliers(cursor?: string, loaded: Supplier[] = [], page = 1): void {
    this.api.suppliers({ limit: 100, status: 'all', cursor })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          const all = [...loaded, ...response.items];
          this.suppliers.set(all.sort((a, b) => a.name.localeCompare(b.name)));
          if (response.next_cursor && page < 20) this.loadSuppliers(response.next_cursor, all, page + 1);
        },
        error: (error: unknown) => {
          if (page === 1) this.handleError(error);
        },
      });
  }

  loadTasks(preserveFailedTasks?: readonly ReviewTask[]): void {
    this.loadTasksSub?.unsubscribe();
    this.loadTasksSub = null;
    if (this.loadMoreSub) {
      this.loadMoreSub.unsubscribe();
      this.loadMoreSub = null;
    }
    this.isLoadingMore.set(false);

    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.nextCursor.set(null);

    if (this.dateRangeInvalid()) {
      // From after To can never match: show the error instead of asking the API.
      this.tasks.set([]);
      this.isLoading.set(false);
      return;
    }

    this.isLoading.set(true);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.sanitizedSearch();
    const { date_from, date_to } = this.formatFilterDates();

    this.loadTasksSub = this.api
      .getReviewTasks({
        status,
        priority: priority === 'all' ? undefined : priority,
        ...this.additionalRequestFilters(),
        search,
        date_from,
        date_to,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          if (preserveFailedTasks && preserveFailedTasks.length > 0) {
            const refreshedIds = new Set(res.items.map((item) => item.id));
            const missingFailedRows = preserveFailedTasks.filter(
              (task) => !refreshedIds.has(task.id),
            );
            this.tasks.set([...missingFailedRows, ...res.items]);
            this.selectedTaskIds.set(new Set(preserveFailedTasks.map((t) => t.id)));
          } else {
            this.tasks.set(res.items);
            this.selectedTaskIds.set(new Set());
          }
          this.nextCursor.set(res.next_cursor);
          this.isLoading.set(false);
          this.loadTasksSub = null;
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.loadTasksSub = null;
          this.handleError(err);
        },
      });
  }

  loadMore(): void {
    if (this.isLoading()) return;
    const cursor = this.nextCursor();
    if (!cursor) return;

    this.isLoadingMore.set(true);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.sanitizedSearch();
    const { date_from, date_to } = this.formatFilterDates();

    this.loadMoreSub = this.api
      .getReviewTasks({
        cursor,
        status,
        priority: priority === 'all' ? undefined : priority,
        ...this.additionalRequestFilters(),
        search,
        date_from,
        date_to,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          const currentIds = new Set(this.tasks().map((task) => task.id));
          const newItems = res.items.filter((item) => !currentIds.has(item.id));
          this.tasks.set([...this.tasks(), ...newItems]);
          this.nextCursor.set(res.next_cursor);
          this.isLoadingMore.set(false);
          this.loadMoreSub = null;
        },
        error: (err: unknown) => {
          this.isLoadingMore.set(false);
          this.loadMoreSub = null;
          this.handleError(err);
        },
      });
  }

  truncateId(id: string): string {
    return id.slice(0, 8);
  }

  isResolvedTask(task: ReviewTask): boolean {
    return task.status === 'resolved';
  }

  reviewActionIcon(task: ReviewTask): string {
    return this.isResolvedTask(task) ? 'visibility' : 'fact_check';
  }

  reviewActionLabelKey(task: ReviewTask): string {
    return this.isResolvedTask(task)
      ? 'quotations.queue.actions.viewReview'
      : 'quotations.queue.actions.review';
  }

  onStatusChange(status: ReviewTaskStatus | 'all'): void {
    this.statusFilter.set(status);
    this.updateQueryParams();
    this.loadTasks();
  }

  onPriorityChange(priority: ReviewTaskPriority | 'all'): void {
    this.priorityFilter.set(priority);
    this.updateQueryParams();
    this.loadTasks();
  }

  onSupplierChange(value: string | null): void {
    this.supplierFilter.set(value);
    this.updateQueryParams();
    this.loadTasks();
  }

  onReasonChange(value: ReviewTaskReason | 'all'): void {
    this.reasonFilter.set(value);
    this.updateQueryParams();
    this.loadTasks();
  }

  onLifecycleChange(value: QuotationStatus | 'all'): void {
    this.lifecycleFilter.set(value);
    this.updateQueryParams();
    this.loadTasks();
  }

  private additionalRequestFilters(): {
    supplier_id?: string; reason?: ReviewTaskReason; quotation_status?: QuotationStatus;
  } {
    const supplier = this.supplierFilter();
    const reason = this.reasonFilter();
    const lifecycle = this.lifecycleFilter();
    return {
      ...(supplier ? { supplier_id: supplier } : {}),
      ...(reason !== 'all' ? { reason } : {}),
      ...(lifecycle !== 'all' ? { quotation_status: lifecycle } : {}),
    };
  }

  onSearchChange(value: string): void {
    this.searchQuery.set(value);
    this.updateQueryParams();
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
    }
    this.searchDebounce = setTimeout(() => {
      this.loadTasks();
    }, 300);
  }

  onDateFromChange(value: Date | string | null): void {
    const next = toIsoDateOrNull(value);
    if (this.dateFrom() !== next) {
      this.dateFrom.set(next);
      this.updateQueryParams();
      this.loadTasks();
    }
  }

  onDateToChange(value: Date | string | null): void {
    const next = toIsoDateOrNull(value);
    if (this.dateTo() !== next) {
      this.dateTo.set(next);
      this.updateQueryParams();
      this.loadTasks();
    }
  }

  onSortChange(sort: Sort): void {
    if (this.isSortableColumn(sort.active)) {
      this.sortBy.set(sort.active);
    }
    this.sortOrder.set(sort.direction === 'asc' ? 'asc' : 'desc');
    this.updateQueryParams();
    this.loadTasks();
  }

  clearFilters(): void {
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = null;
    }
    this.statusFilter.set('open');
    this.priorityFilter.set('all');
    this.supplierFilter.set(null);
    this.reasonFilter.set('all');
    this.lifecycleFilter.set('all');
    this.searchQuery.set('');
    this.dateFrom.set(null);
    this.dateTo.set(null);
    this.updateQueryParams();
    this.loadTasks();
  }

  removeStatusFilter(): void {
    this.statusFilter.set('open');
    this.updateQueryParams();
    this.loadTasks();
  }

  removePriorityFilter(): void {
    this.priorityFilter.set('all');
    this.updateQueryParams();
    this.loadTasks();
  }

  removeSearchFilter(): void {
    if (this.searchDebounce) {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = null;
    }
    this.searchQuery.set('');
    this.updateQueryParams();
    this.loadTasks();
  }

  removeDateRangeFilter(): void {
    this.dateFrom.set(null);
    this.dateTo.set(null);
    this.updateQueryParams();
    this.loadTasks();
  }

  removeFilter(filter: 'status' | 'priority' | 'search' | 'date_range' | 'date'): void {
    switch (filter) {
      case 'status':
        this.removeStatusFilter();
        break;
      case 'priority':
        this.removePriorityFilter();
        break;
      case 'search':
        this.removeSearchFilter();
        break;
      case 'date_range':
      case 'date':
        this.removeDateRangeFilter();
        break;
    }
  }

  resultCountText(): string {
    const count = this.tasks().length;
    if (this.nextCursor()) {
      return this.translate.instant('quotations.queue.resultsCount.more', { count });
    }
    if (count === 1) {
      return this.translate.instant('quotations.queue.resultsCount.one', { count });
    }
    return this.translate.instant('quotations.queue.resultsCount.other', { count });
  }

  archiveTask(task: ReviewTask, event: MouseEvent): void {
    event.stopPropagation();
    if (this.isResolvedTask(task)) {
      return;
    }
    if (!window.confirm(this.translate.instant('quotations.queue.archiveConfirm'))) {
      return;
    }
    this.archivingTaskId.set(task.id);
    this.api.archiveQuotation(task.quotation_id).subscribe({
      next: () => {
        this.tasks.set(this.tasks().filter((item) => item.id !== task.id));
        const selected = new Set(this.selectedTaskIds());
        if (selected.delete(task.id)) {
          this.selectedTaskIds.set(selected);
        }
        this.archivingTaskId.set(null);
      },
      error: (err: unknown) => {
        this.archivingTaskId.set(null);
        this.handleError(err);
      },
    });
  }

  toggleTask(taskId: string): void {
    const selected = new Set(this.selectedTaskIds());
    if (selected.has(taskId)) {
      selected.delete(taskId);
    } else {
      selected.add(taskId);
    }
    this.selectedTaskIds.set(selected);
  }

  toggleAll(): void {
    if (this.allSelected()) {
      this.clearSelection();
      return;
    }
    this.selectedTaskIds.set(new Set(this.tasks().map((task) => task.id)));
  }

  clearSelection(): void {
    this.selectedTaskIds.set(new Set());
  }

  bulkArchive(): void {
    const selected = this.selectedTaskIds();
    if (selected.size === 0) return;
    if (
      !window.confirm(
        this.translate.instant('quotations.queue.bulkArchiveConfirm', { count: selected.size }),
      )
    ) {
      return;
    }
    this.isBulkArchiving.set(true);
    const tasks = this.tasks().filter((task) => selected.has(task.id));
    const eligibleTasks = tasks.filter((task) => !this.isResolvedTask(task));
    const skippedTasks = tasks.filter((task) => this.isResolvedTask(task));
    const skippedIds = skippedTasks.map((t) => t.id);

    if (eligibleTasks.length === 0) {
      this.finishBulkAction('archive', [], [], skippedIds);
      return;
    }

    const succeededIds: string[] = [];
    const failedTasks: ReviewTask[] = [];
    for (const task of eligibleTasks) {
      this.api.archiveQuotation(task.quotation_id).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('archive', succeededIds, failedTasks, skippedIds);
          }
        },
        error: () => {
          failedTasks.push(task);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('archive', succeededIds, failedTasks, skippedIds);
          }
        },
      });
    }
  }

  bulkRefuse(): void {
    const selected = this.selectedTaskIds();
    if (selected.size === 0) return;
    if (
      !window.confirm(
        this.translate.instant('quotations.queue.bulkRefuseConfirm', { count: selected.size }),
      )
    ) {
      return;
    }
    this.isBulkRefusing.set(true);
    const tasks = this.tasks().filter((task) => selected.has(task.id));
    const eligibleTasks = tasks.filter((task) => !this.isResolvedTask(task));
    const skippedTasks = tasks.filter((task) => this.isResolvedTask(task));
    const skippedIds = skippedTasks.map((t) => t.id);

    if (eligibleTasks.length === 0) {
      this.finishBulkAction('refuse', [], [], skippedIds);
      return;
    }

    const succeededIds: string[] = [];
    const failedTasks: ReviewTask[] = [];
    for (const task of eligibleTasks) {
      this.api.refuseQuotation(task.quotation_id).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('refuse', succeededIds, failedTasks, skippedIds);
          }
        },
        error: () => {
          failedTasks.push(task);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('refuse', succeededIds, failedTasks, skippedIds);
          }
        },
      });
    }
  }

  bulkReprioritise(priority: ReviewTaskPriority): void {
    const selected = this.selectedTaskIds();
    if (selected.size === 0) return;
    this.isBulkReprioritising.set(true);
    this.bulkPriorityTarget.set(priority);
    const tasks = this.tasks().filter((task) => selected.has(task.id));
    const eligibleTasks = tasks.filter((task) => !this.isResolvedTask(task));
    const skippedTasks = tasks.filter((task) => this.isResolvedTask(task));
    const skippedIds = skippedTasks.map((t) => t.id);

    if (eligibleTasks.length === 0) {
      this.finishBulkAction('reprioritise', [], [], skippedIds);
      return;
    }

    const succeededIds: string[] = [];
    const failedTasks: ReviewTask[] = [];
    for (const task of eligibleTasks) {
      this.api.updateReviewTaskPriority(task.id, priority).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('reprioritise', succeededIds, failedTasks, skippedIds);
          }
        },
        error: () => {
          failedTasks.push(task);
          if (succeededIds.length + failedTasks.length === eligibleTasks.length) {
            this.finishBulkAction('reprioritise', succeededIds, failedTasks, skippedIds);
          }
        },
      });
    }
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

  private sanitizedSearch(): string | undefined {
    const search = this.searchQuery().trim();
    return search ? search : undefined;
  }

  private formatFilterDates(): { date_from?: string; date_to?: string } {
    const toBoundaryIso = (value: string | null, isEnd: boolean): string | undefined => {
      if (!value) return undefined;
      const [y, m, d] = value.split('-').map(Number);
      if (isNaN(y) || isNaN(m) || isNaN(d)) return undefined;
      return isEnd
        ? new Date(y, m - 1, d, 23, 59, 59, 999).toISOString()
        : new Date(y, m - 1, d, 0, 0, 0, 0).toISOString();
    };

    return {
      date_from: toBoundaryIso(this.dateFrom(), false),
      date_to: toBoundaryIso(this.dateTo(), true),
    };
  }

  private isSortableColumn(value: string): value is ReviewTaskSortBy {
    return ['created_at', 'stated_total', 'priority', 'status'].includes(value);
  }

  private isValidStatus(val: string): val is ReviewTaskStatus | 'all' {
    return ['open', 'in_progress', 'resolved', 'all'].includes(val);
  }

  private isValidPriority(val: string): val is ReviewTaskPriority | 'all' {
    return ['all', 'high', 'normal', 'low'].includes(val);
  }

  private isValidDateString(val: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(val)) return false;
    const [y, m, d] = val.split('-').map(Number);
    const date = new Date(y, m - 1, d);
    return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
  }

  private parseFiltersFromParams(params: ParamMap): {
    status: ReviewTaskStatus | 'all';
    priority: ReviewTaskPriority | 'all';
    supplier: string | null;
    reason: ReviewTaskReason | 'all';
    lifecycle: QuotationStatus | 'all';
    search: string;
    dateFrom: string | null;
    dateTo: string | null;
    sortBy: ReviewTaskSortBy;
    sortOrder: ReviewTaskSortOrder;
  } {
    const status = params.get('status');
    const priority = params.get('priority');
    const search = params.get('search');
    const dateFrom = params.get('date_from');
    const dateTo = params.get('date_to');
    const sort = params.get('sort');
    const order = params.get('order');
    const supplier = params.get('supplier_id');
    const reason = params.get('reason');
    const lifecycle = params.get('quotation_status');

    return {
      status: status && this.isValidStatus(status) ? status : 'open',
      priority: priority && this.isValidPriority(priority) ? priority : 'all',
      supplier: supplier && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(supplier) ? supplier : null,
      reason: this.reasons.find((value) => value === reason) ?? 'all',
      lifecycle: this.lifecycles.find((value) => value === lifecycle) ?? 'all',
      search: search ? search.trim() : '',
      dateFrom: dateFrom && this.isValidDateString(dateFrom) ? dateFrom : null,
      dateTo: dateTo && this.isValidDateString(dateTo) ? dateTo : null,
      sortBy: sort && this.isSortableColumn(sort) ? sort : 'created_at',
      sortOrder: order === 'asc' || order === 'desc' ? order : 'desc',
    };
  }

  private hasFilterStateChanged(target: {
    status: ReviewTaskStatus | 'all';
    priority: ReviewTaskPriority | 'all';
    supplier: string | null;
    reason: ReviewTaskReason | 'all';
    lifecycle: QuotationStatus | 'all';
    search: string;
    dateFrom: string | null;
    dateTo: string | null;
    sortBy: ReviewTaskSortBy;
    sortOrder: ReviewTaskSortOrder;
  }): boolean {
    return (
      this.statusFilter() !== target.status ||
      this.priorityFilter() !== target.priority ||
      this.supplierFilter() !== target.supplier ||
      this.reasonFilter() !== target.reason ||
      this.lifecycleFilter() !== target.lifecycle ||
      this.searchQuery().trim() !== target.search ||
      this.dateFrom() !== target.dateFrom ||
      this.dateTo() !== target.dateTo ||
      this.sortBy() !== target.sortBy ||
      this.sortOrder() !== target.sortOrder
    );
  }

  private applyFilterState(target: {
    status: ReviewTaskStatus | 'all';
    priority: ReviewTaskPriority | 'all';
    supplier: string | null;
    reason: ReviewTaskReason | 'all';
    lifecycle: QuotationStatus | 'all';
    search: string;
    dateFrom: string | null;
    dateTo: string | null;
    sortBy: ReviewTaskSortBy;
    sortOrder: ReviewTaskSortOrder;
  }): void {
    this.statusFilter.set(target.status);
    this.priorityFilter.set(target.priority);
    this.supplierFilter.set(target.supplier);
    this.reasonFilter.set(target.reason);
    this.lifecycleFilter.set(target.lifecycle);
    this.searchQuery.set(target.search);
    this.dateFrom.set(target.dateFrom);
    this.dateTo.set(target.dateTo);
    this.sortBy.set(target.sortBy);
    this.sortOrder.set(target.sortOrder);
  }

  private handleQueryParamChange(params: ParamMap): void {
    const target = this.parseFiltersFromParams(params);
    if (this.isInitialLoad) {
      this.isInitialLoad = false;
      this.applyFilterState(target);
      this.loadTasks();
      return;
    }

    if (this.hasFilterStateChanged(target)) {
      if (this.searchDebounce) {
        clearTimeout(this.searchDebounce);
        this.searchDebounce = null;
      }
      this.applyFilterState(target);
      this.loadTasks();
    }
  }

  private restoreFiltersFromUrl(): void {
    const params = this.route.snapshot?.queryParamMap ?? convertToParamMap({});
    this.applyFilterState(this.parseFiltersFromParams(params));
  }

  private buildQueryParams(): Record<string, string | null> {
    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.searchQuery().trim();
    const dateFrom = this.dateFrom();
    const dateTo = this.dateTo();
    const sort = this.sortBy();
    const order = this.sortOrder();

    return {
      status: status !== 'open' ? status : null,
      priority: priority !== 'all' ? priority : null,
      supplier_id: this.supplierFilter(),
      reason: this.reasonFilter() !== 'all' ? this.reasonFilter() : null,
      quotation_status: this.lifecycleFilter() !== 'all' ? this.lifecycleFilter() : null,
      search: search.length > 0 ? search : null,
      date_from: dateFrom ? dateFrom : null,
      date_to: dateTo ? dateTo : null,
      sort: sort !== 'created_at' ? sort : null,
      order: order !== 'desc' ? order : null,
    };
  }

  private updateQueryParams(): void {
    void this.router.navigate([], {
      queryParams: this.buildQueryParams(),
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  private finishBulkAction(
    action: 'archive' | 'refuse' | 'reprioritise',
    succeededIds: string[],
    failedTasks: ReviewTask[],
    skippedIds: string[],
  ): void {
    if (action === 'archive') {
      this.isBulkArchiving.set(false);
    } else if (action === 'refuse') {
      this.isBulkRefusing.set(false);
    } else if (action === 'reprioritise') {
      this.isBulkReprioritising.set(false);
      this.bulkPriorityTarget.set(null);
    }

    const succeeded = succeededIds.length;
    const failed = failedTasks.length;
    const skipped = skippedIds.length;

    let message: string;
    if (succeeded > 0 && failed === 0) {
      message =
        skipped > 0
          ? this.translate.instant('quotations.queue.bulk.result.allSucceededSkipped', {
              count: succeeded,
              succeeded,
              skipped,
            })
          : this.translate.instant('quotations.queue.bulk.result.allSucceeded', {
              count: succeeded,
              succeeded,
            });
    } else if (succeeded > 0 && failed > 0) {
      message =
        skipped > 0
          ? this.translate.instant('quotations.queue.bulk.result.partialSkipped', {
              succeeded,
              failed,
              count: succeeded + failed,
              skipped,
            })
          : this.translate.instant('quotations.queue.bulk.result.partial', {
              succeeded,
              failed,
              count: succeeded + failed,
            });
    } else {
      message =
        skipped > 0
          ? this.translate.instant('quotations.queue.bulk.result.allFailedSkipped', {
              failed,
              count: failed,
              skipped,
            })
          : this.translate.instant('quotations.queue.bulk.result.allFailed', {
              failed,
              count: failed,
            });
    }

    this.snackBar.open(message, undefined, { duration: 4000 });

    const failedIds = new Set(failedTasks.map((t) => t.id));
    this.selectedTaskIds.set(failedIds);
    this.loadTasks(failedTasks);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('quotations.review.actions.genericError'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('quotations.review.actions.genericError'));
  }
}
