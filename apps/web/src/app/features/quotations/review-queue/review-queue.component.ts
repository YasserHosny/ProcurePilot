import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSortModule, type Sort } from '@angular/material/sort';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, ReviewTask, ReviewTaskPriority, ReviewTaskStatus } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';

type ReviewTaskSortBy = 'created_at' | 'stated_total' | 'priority' | 'status';
type ReviewTaskSortOrder = 'asc' | 'desc';

@Component({
  selector: 'app-review-queue',
  standalone: true,
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
    MatFormFieldModule,
    MatSelectModule,
    MatSortModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    RoleDirective,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './review-queue.component.html',
  styleUrl: './review-queue.component.scss',
})
export class ReviewQueueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
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
  readonly sortBy = signal<ReviewTaskSortBy>('created_at');
  readonly sortOrder = signal<ReviewTaskSortOrder>('desc');
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly archivingTaskId = signal<string | null>(null);
  readonly isBulkArchiving = signal<boolean>(false);
  readonly isBulkRefusing = signal<boolean>(false);
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;

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

  readonly displayedColumns: readonly string[] = [
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
  ];

  ngOnInit(): void {
    this.loadTasks();
  }

  loadTasks(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.nextCursor.set(null);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.sanitizedSearch();

    this.api
      .getReviewTasks({
        status: status === 'all' ? undefined : status,
        priority: priority === 'all' ? undefined : priority,
        search,
        date_from: this.dateFrom() ?? undefined,
        date_to: this.dateTo() ?? undefined,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          this.tasks.set(res.items);
          this.selectedTaskIds.set(new Set());
          this.nextCursor.set(res.next_cursor);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor) return;

    this.isLoadingMore.set(true);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const search = this.sanitizedSearch();

    this.api
      .getReviewTasks({
        cursor,
        status: status === 'all' ? undefined : status,
        priority: priority === 'all' ? undefined : priority,
        search,
        date_from: this.dateFrom() ?? undefined,
        date_to: this.dateTo() ?? undefined,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          this.tasks.set([...this.tasks(), ...res.items]);
          this.nextCursor.set(res.next_cursor);
          this.isLoadingMore.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingMore.set(false);
          this.handleError(err);
        },
      });
  }

  truncateId(id: string): string {
    return id.slice(0, 8);
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

  onDateFromChange(value: string | null): void {
    this.dateFrom.set(value || null);
    this.loadTasks();
  }

  onDateToChange(value: string | null): void {
    this.dateTo.set(value || null);
    this.loadTasks();
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
    if (!window.confirm(this.translate.instant('quotations.queue.archiveConfirm'))) {
      return;
    }
    this.archivingTaskId.set(task.id);
    this.api.archiveQuotation(task.quotation_id).subscribe({
      next: () => {
        this.tasks.set(this.tasks().filter((item) => item.id !== task.id));
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
    let completed = 0;
    let errors = 0;
    for (const task of tasks) {
      this.api.archiveQuotation(task.quotation_id).subscribe({
        next: () => {
          completed++;
          if (completed + errors === tasks.length) {
            this.finishBulkArchive(completed, errors);
          }
        },
        error: () => {
          errors++;
          if (completed + errors === tasks.length) {
            this.finishBulkArchive(completed, errors);
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
    let completed = 0;
    let errors = 0;
    for (const task of tasks) {
      this.api.refuseQuotation(task.quotation_id).subscribe({
        next: () => {
          completed++;
          if (completed + errors === tasks.length) {
            this.finishBulkRefuse(completed, errors);
          }
        },
        error: () => {
          errors++;
          if (completed + errors === tasks.length) {
            this.finishBulkRefuse(completed, errors);
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

  onRowClick(_task: ReviewTask): void {
    // Navigation is handled by RouterLink on the row.
  }

  private sanitizedSearch(): string | undefined {
    const search = this.searchQuery().trim();
    return search ? search : undefined;
  }

  private isSortableColumn(value: string): value is ReviewTaskSortBy {
    return ['created_at', 'stated_total', 'priority', 'status'].includes(value);
  }

  private finishBulkArchive(_completed: number, _errors: number): void {
    this.isBulkArchiving.set(false);
    this.selectedTaskIds.set(new Set());
    this.loadTasks();
  }

  private finishBulkRefuse(_completed: number, _errors: number): void {
    this.isBulkRefusing.set(false);
    this.selectedTaskIds.set(new Set());
    this.loadTasks();
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
