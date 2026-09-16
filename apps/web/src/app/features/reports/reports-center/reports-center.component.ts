import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  type ReportArtifact,
  type ReportArtifactStatus,
  type ReportKind,
  type ReportSchedule,
  ReportsApiService,
} from './reports-api';

interface ApiErrorShape {
  code?: string;
  message?: string;
  trace_id?: string;
}

@Component({
  selector: 'app-reports-center',
  standalone: true,
  imports: [
    FormsModule,
    NgClass,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatTableModule,
    MatTabsModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './reports-center.component.html',
  styleUrl: './reports-center.component.scss',
})
export class ReportsCenterComponent implements OnInit {
  private readonly reportsApi = inject(ReportsApiService);
  private readonly translate = inject(TranslateService);

  readonly isLoadingArtifacts = signal<boolean>(true);
  readonly isLoadingMoreArtifacts = signal<boolean>(false);
  readonly artifacts = signal<ReportArtifact[]>([]);
  readonly artifactsNextCursor = signal<string | null>(null);
  readonly artifactsErrorMessage = signal<string | null>(null);
  readonly artifactsErrorTraceId = signal<string | null>(null);

  readonly selectedKind = signal<ReportKind | 'all'>('all');
  readonly selectedStatus = signal<ReportArtifactStatus | 'all'>('all');

  readonly isLoadingSchedules = signal<boolean>(true);
  readonly isLoadingMoreSchedules = signal<boolean>(false);
  readonly schedules = signal<ReportSchedule[]>([]);
  readonly schedulesNextCursor = signal<string | null>(null);
  readonly schedulesErrorMessage = signal<string | null>(null);
  readonly schedulesErrorTraceId = signal<string | null>(null);

  readonly artifactDisplayedColumns: readonly string[] = [
    'kind',
    'format',
    'status',
    'period',
    'rowCount',
    'locale',
    'createdAt',
    'expiresAt',
  ];

  readonly scheduleDisplayedColumns: readonly string[] = [
    'kind',
    'format',
    'weekday',
    'status',
    'locale',
    'nextRunAt',
    'lastRunAt',
  ];

  ngOnInit(): void {
    this.loadArtifacts();
    this.loadSchedules();
  }

  loadArtifacts(): void {
    this.isLoadingArtifacts.set(true);
    this.artifactsErrorMessage.set(null);
    this.artifactsErrorTraceId.set(null);

    const kindParam = this.selectedKind() === 'all' ? undefined : this.selectedKind() as ReportKind;
    const statusParam = this.selectedStatus() === 'all' ? undefined : this.selectedStatus() as ReportArtifactStatus;

    this.reportsApi
      .getArtifacts({
        limit: 50,
        kind: kindParam,
        status: statusParam,
      })
      .subscribe({
        next: (res) => {
          this.artifacts.set([...res.items]);
          this.artifactsNextCursor.set(res.next_cursor);
          this.isLoadingArtifacts.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingArtifacts.set(false);
          this.handleArtifactError(err);
        },
      });
  }

  loadMoreArtifacts(): void {
    const cursor = this.artifactsNextCursor();
    if (!cursor || this.isLoadingMoreArtifacts()) return;

    this.isLoadingMoreArtifacts.set(true);
    const kindParam = this.selectedKind() === 'all' ? undefined : this.selectedKind() as ReportKind;
    const statusParam = this.selectedStatus() === 'all' ? undefined : this.selectedStatus() as ReportArtifactStatus;

    this.reportsApi
      .getArtifacts({
        cursor,
        limit: 50,
        kind: kindParam,
        status: statusParam,
      })
      .subscribe({
        next: (res) => {
          this.artifacts.set([...this.artifacts(), ...res.items]);
          this.artifactsNextCursor.set(res.next_cursor);
          this.isLoadingMoreArtifacts.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingMoreArtifacts.set(false);
          this.handleArtifactError(err);
        },
      });
  }

  onFilterChange(): void {
    this.loadArtifacts();
  }

  clearFilters(): void {
    this.selectedKind.set('all');
    this.selectedStatus.set('all');
    this.loadArtifacts();
  }

  loadSchedules(): void {
    this.isLoadingSchedules.set(true);
    this.schedulesErrorMessage.set(null);
    this.schedulesErrorTraceId.set(null);

    this.reportsApi
      .getSchedules({
        limit: 50,
      })
      .subscribe({
        next: (res) => {
          this.schedules.set([...res.items]);
          this.schedulesNextCursor.set(res.next_cursor);
          this.isLoadingSchedules.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingSchedules.set(false);
          this.handleScheduleError(err);
        },
      });
  }

  loadMoreSchedules(): void {
    const cursor = this.schedulesNextCursor();
    if (!cursor || this.isLoadingMoreSchedules()) return;

    this.isLoadingMoreSchedules.set(true);

    this.reportsApi
      .getSchedules({
        cursor,
        limit: 50,
      })
      .subscribe({
        next: (res) => {
          this.schedules.set([...this.schedules(), ...res.items]);
          this.schedulesNextCursor.set(res.next_cursor);
          this.isLoadingMoreSchedules.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingMoreSchedules.set(false);
          this.handleScheduleError(err);
        },
      });
  }

  getArtifactStatusClass(status: ReportArtifactStatus): string {
    switch (status) {
      case 'completed':
        return 'status-completed';
      case 'running':
        return 'status-running';
      case 'queued':
        return 'status-queued';
      case 'failed':
        return 'status-failed';
      case 'expired':
        return 'status-expired';
      default:
        return 'status-default';
    }
  }

  getScheduleStatusClass(schedule: ReportSchedule): string {
    const isPaused = schedule.status === 'paused' || schedule.is_active === false;
    return isPaused ? 'status-paused' : 'status-active';
  }

  getScheduleStatusKey(schedule: ReportSchedule): string {
    const isPaused = schedule.status === 'paused' || schedule.is_active === false;
    return isPaused ? 'reports.statuses.paused' : 'reports.statuses.active';
  }

  getWeekdayKey(weekday: number): string {
    return `reports.weekdays.${weekday}`;
  }

  formatPeriod(filters: ReportArtifact['filters']): string {
    if (!filters) return '—';
    if (filters.period_start && filters.period_end) {
      return `${filters.period_start} → ${filters.period_end}`;
    }
    if (filters.period_start) {
      return `≥ ${filters.period_start}`;
    }
    if (filters.period_end) {
      return `≤ ${filters.period_end}`;
    }
    return '—';
  }

  private handleArtifactError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiErrorShape | undefined;
      this.artifactsErrorTraceId.set(apiError?.trace_id ?? null);
      this.artifactsErrorMessage.set(apiError?.message ?? err.message);
      return;
    }
    this.artifactsErrorMessage.set(this.translate.instant('reports.error.generic'));
  }

  private handleScheduleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiErrorShape | undefined;
      this.schedulesErrorTraceId.set(apiError?.trace_id ?? null);
      this.schedulesErrorMessage.set(apiError?.message ?? err.message);
      return;
    }
    this.schedulesErrorMessage.set(this.translate.instant('reports.error.generic'));
  }
}
