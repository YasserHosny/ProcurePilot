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
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  MatchTask,
  MatchTaskPriority,
  MatchTaskReason,
  MatchTaskStatus,
  QuotationMatchSummary,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';

type MatchTaskSortBy = 'created_at' | 'priority' | 'status';
type MatchTaskSortOrder = 'asc' | 'desc';

export interface QuotationTaskGroup {
  readonly quotation: QuotationMatchSummary;
  readonly tasks: readonly MatchTask[];
}

@Component({
  selector: 'app-resolution-queue',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
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
  private readonly route = inject(ActivatedRoute);

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
  readonly quotationId = signal<string | null>(null);
  private searchDebounce: ReturnType<typeof setTimeout> | null = null;
  private latestLoadRequestId = 0;

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

  readonly groups = computed<readonly QuotationTaskGroup[]>(() => {
    const grouped = new Map<string, MatchTask[]>();
    for (const task of this.tasks()) {
      const items = grouped.get(task.quotation.id) ?? [];
      items.push(task);
      grouped.set(task.quotation.id, items);
    }
    return Array.from(grouped.values(), (tasks) => ({ quotation: tasks[0].quotation, tasks }));
  });

  ngOnInit(): void {
    this.quotationId.set(this.route.snapshot.queryParamMap.get('quotation_id'));
    this.loadTasks();
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
        status: status === 'all' ? undefined : status,
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
        status: status === 'all' ? undefined : status,
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
