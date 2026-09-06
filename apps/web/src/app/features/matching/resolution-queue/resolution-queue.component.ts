import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
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
import type {
  ApiError,
  MatchTask,
  MatchTaskPriority,
  MatchTaskReason,
  MatchTaskStatus,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';

type MatchTaskSortBy = 'created_at' | 'priority' | 'status';
type MatchTaskSortOrder = 'asc' | 'desc';

@Component({
  selector: 'app-resolution-queue',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatChipsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatSortModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './resolution-queue.component.html',
  styleUrl: './resolution-queue.component.scss',
})
export class ResolutionQueueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly tasks = signal<MatchTask[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly statusFilter = signal<MatchTaskStatus | 'all'>('open');
  readonly priorityFilter = signal<MatchTaskPriority | 'all'>('all');
  readonly reasonFilter = signal<MatchTaskReason | 'all'>('all');
  readonly searchQuery = signal<string>('');
  readonly dateFrom = signal<string | null>(null);
  readonly dateTo = signal<string | null>(null);
  readonly sortBy = signal<MatchTaskSortBy>('created_at');
  readonly sortOrder = signal<MatchTaskSortOrder>('desc');
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));
  readonly hasActiveFilters = computed<boolean>(
    () =>
      this.statusFilter() !== 'open' ||
      this.priorityFilter() !== 'all' ||
      this.reasonFilter() !== 'all' ||
      this.searchQuery().trim().length > 0 ||
      this.dateFrom() !== null ||
      this.dateTo() !== null,
  );

  readonly displayedColumns: readonly string[] = [
    'quotation_line',
    'supplier_name',
    'original_text',
    'unit_price',
    'reason',
    'priority',
    'status',
    'candidates_count',
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
    const reason = this.reasonFilter();
    const search = this.sanitizedSearch();

    this.api
      .getMatchTasks({
        status: status === 'all' ? undefined : status,
        priority: priority === 'all' ? undefined : priority,
        reason: reason === 'all' ? undefined : reason,
        search,
        date_from: this.dateFrom() ?? undefined,
        date_to: this.dateTo() ?? undefined,
        sort_by: this.sortBy(),
        sort_order: this.sortOrder(),
      })
      .subscribe({
        next: (res) => {
          this.tasks.set(res.items);
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
    const reason = this.reasonFilter();
    const search = this.sanitizedSearch();

    this.api
      .getMatchTasks({
        cursor,
        status: status === 'all' ? undefined : status,
        priority: priority === 'all' ? undefined : priority,
        reason: reason === 'all' ? undefined : reason,
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

  onStatusChange(status: MatchTaskStatus | 'all'): void {
    this.statusFilter.set(status);
    this.loadTasks();
  }

  onPriorityChange(priority: MatchTaskPriority | 'all'): void {
    this.priorityFilter.set(priority);
    this.loadTasks();
  }

  onReasonChange(reason: MatchTaskReason | 'all'): void {
    this.reasonFilter.set(reason);
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
    this.reasonFilter.set('all');
    this.searchQuery.set('');
    this.dateFrom.set(null);
    this.dateTo.set(null);
    this.loadTasks();
  }

  truncateId(id: string): string {
    return id.slice(0, 8);
  }

  ageLabel(createdAt: string): string {
    const created = new Date(createdAt);
    const diffMs = Date.now() - created.getTime();
    if (isNaN(created.getTime()) || diffMs < 60 * 60 * 1000) {
      return this.translate.instant('matching.queue.age.justNow');
    }

    const diffHours = Math.floor(diffMs / (60 * 60 * 1000));
    if (diffHours < 24) {
      return this.translate.instant('matching.queue.age.hoursAgo', { count: diffHours });
    }

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) {
      return this.translate.instant('matching.queue.age.daysAgo', { count: diffDays });
    }
    if (diffDays < 30) {
      return this.translate.instant('matching.queue.age.weeksAgo', {
        count: Math.floor(diffDays / 7),
      });
    }
    return this.translate.instant('matching.queue.age.monthsAgo', {
      count: Math.floor(diffDays / 30),
    });
  }

  private sanitizedSearch(): string | undefined {
    const search = this.searchQuery().trim();
    return search ? search : undefined;
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
