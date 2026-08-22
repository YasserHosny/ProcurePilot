import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
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
    MatChipsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './resolution-queue.component.html',
  styleUrl: './resolution-queue.component.scss',
})
export class ResolutionQueueComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly tasks = signal<MatchTask[]>([]);
  readonly statusFilter = signal<MatchTaskStatus | 'all'>('open');
  readonly priorityFilter = signal<MatchTaskPriority | 'all'>('all');
  readonly reasonFilter = signal<MatchTaskReason | 'all'>('all');
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly displayedColumns: readonly string[] = [
    'quotation_line',
    'original_text',
    'reason',
    'priority',
    'status',
    'candidates_count',
    'created_at',
    'actions',
  ];

  ngOnInit(): void {
    this.loadTasks();
  }

  loadTasks(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const status = this.statusFilter();
    const priority = this.priorityFilter();
    const reason = this.reasonFilter();

    this.api
      .getMatchTasks({
        status: status === 'all' ? undefined : status,
        priority: priority === 'all' ? undefined : priority,
        reason: reason === 'all' ? undefined : reason,
      })
      .subscribe({
        next: (res) => {
          this.tasks.set(res.items);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
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
