import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
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
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, ReviewTask, ReviewTaskPriority, ReviewTaskStatus } from '../../../core/api/models';
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

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly tasks = signal<ReviewTask[]>([]);
  readonly selectedTaskIds = signal<Set<string>>(new Set());
  readonly nextCursor = signal<string | null>(null);
  readonly statusFilter = signal<ReviewTaskStatus | 'all'>('open');
  readonly priorityFilter = signal<ReviewTaskPriority | 'all'>('all');
  readonly searchQuery = signal<string>('');
  readonly dateFrom = signal<string | null>(null);
  readonly dateTo = signal<string | null>(null);
  readonly dateFromModel = computed(() => parseIsoDateLocal(this.dateFrom()));
  readonly dateToModel = computed(() => parseIsoDateLocal(this.dateTo()));
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

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));
  readonly hasSelection = computed<boolean>(() => this.selectedTaskIds().size > 0);
  readonly allSelected = computed<boolean>(
    () => this.tasks().length > 0 && this.selectedTaskIds().size === this.tasks().length,
  );
  readonly hasActiveFilters = computed<boolean>(
    () =>
      this.statusFilter() !== 'open' ||
      this.priorityFilter() !== 'all' ||
      this.searchQuery().trim().length > 0 ||
      this.dateFrom() !== null ||
      this.dateTo() !== null,
  );

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
    this.loadTasks();
  }

  loadTasks(preserveIds?: Set<string>): void {
    this.loadTasksSub?.unsubscribe();
    this.loadTasksSub = null;
    if (this.loadMoreSub) {
      this.loadMoreSub.unsubscribe();
      this.loadMoreSub = null;
    }
    this.isLoadingMore.set(false);

    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.nextCursor.set(null);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.sanitizedSearch();
    const { date_from, date_to } = this.formatFilterDates();

    this.loadTasksSub = this.api
      .getReviewTasks({
        status,
        priority: priority === 'all' ? undefined : priority,
        search,
        date_from,
        date_to,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          this.tasks.set(res.items);
          if (preserveIds && preserveIds.size > 0) {
            const currentItemIds = new Set(res.items.map((item) => item.id));
            const retained = new Set<string>();
            for (const id of preserveIds) {
              if (currentItemIds.has(id)) {
                retained.add(id);
              }
            }
            this.selectedTaskIds.set(retained);
          } else {
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
        search,
        date_from,
        date_to,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          this.tasks.set([...this.tasks(), ...res.items]);
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
    this.loadTasks();
  }

  onPriorityChange(priority: ReviewTaskPriority | 'all'): void {
    this.priorityFilter.set(priority);
    this.loadTasks();
  }

  onSearchChange(value: string): void {
    this.searchQuery.set(value);
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
      this.loadTasks();
    }
  }

  onDateToChange(value: Date | string | null): void {
    const next = toIsoDateOrNull(value);
    if (this.dateTo() !== next) {
      this.dateTo.set(next);
      this.loadTasks();
    }
  }

  onSortChange(sort: Sort): void {
    if (this.isSortableColumn(sort.active)) {
      this.sortBy.set(sort.active);
    }
    this.sortOrder.set(sort.direction === 'asc' ? 'asc' : 'desc');
    this.loadTasks();
  }

  clearFilters(): void {
    this.statusFilter.set('open');
    this.priorityFilter.set('all');
    this.searchQuery.set('');
    this.dateFrom.set(null);
    this.dateTo.set(null);
    this.loadTasks();
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
    if (tasks.length === 0) {
      this.isBulkArchiving.set(false);
      return;
    }
    const succeededIds: string[] = [];
    const failedIds: string[] = [];
    for (const task of tasks) {
      this.api.archiveQuotation(task.quotation_id).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedIds.length === tasks.length) {
            this.finishBulkAction('archive', succeededIds, failedIds, []);
          }
        },
        error: () => {
          failedIds.push(task.id);
          if (succeededIds.length + failedIds.length === tasks.length) {
            this.finishBulkAction('archive', succeededIds, failedIds, []);
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
    const failedIds: string[] = [];
    for (const task of eligibleTasks) {
      this.api.refuseQuotation(task.quotation_id).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedIds.length === eligibleTasks.length) {
            this.finishBulkAction('refuse', succeededIds, failedIds, skippedIds);
          }
        },
        error: () => {
          failedIds.push(task.id);
          if (succeededIds.length + failedIds.length === eligibleTasks.length) {
            this.finishBulkAction('refuse', succeededIds, failedIds, skippedIds);
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
    const failedIds: string[] = [];
    for (const task of eligibleTasks) {
      this.api.updateReviewTaskPriority(task.id, priority).subscribe({
        next: () => {
          succeededIds.push(task.id);
          if (succeededIds.length + failedIds.length === eligibleTasks.length) {
            this.finishBulkAction('reprioritise', succeededIds, failedIds, skippedIds);
          }
        },
        error: () => {
          failedIds.push(task.id);
          if (succeededIds.length + failedIds.length === eligibleTasks.length) {
            this.finishBulkAction('reprioritise', succeededIds, failedIds, skippedIds);
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

  private finishBulkAction(
    action: 'archive' | 'refuse' | 'reprioritise',
    succeededIds: string[],
    failedIds: string[],
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
    const failed = failedIds.length;
    const skipped = skippedIds.length;

    let message: string;
    if (succeeded > 0 && failed === 0) {
      message = this.translate.instant('quotations.queue.bulk.result.allSucceeded', {
        count: succeeded,
        succeeded,
      });
    } else if (succeeded > 0 && failed > 0) {
      message = this.translate.instant('quotations.queue.bulk.result.partial', {
        succeeded,
        failed,
        count: succeeded + failed,
      });
    } else {
      message = this.translate.instant('quotations.queue.bulk.result.allFailed', {
        failed,
        count: failed,
      });
    }

    if (skipped > 0) {
      const isArabic =
        typeof this.translate.currentLang === 'function'
          ? this.translate.currentLang() === 'ar'
          : this.translate.getCurrentLang?.() === 'ar';
      const separator = isArabic ? '، ' : ', ';
      const skippedPart = this.translate.instant('quotations.queue.bulk.result.skipped', {
        skipped,
        count: skipped,
      });
      message = `${message}${separator}${skippedPart}`;
    }

    this.snackBar.open(message, undefined, { duration: 4000 });

    const failedSet = new Set(failedIds);
    this.selectedTaskIds.set(failedSet);
    this.loadTasks(failedSet);
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
