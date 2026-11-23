import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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

import { EMPTY, Subject } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { CursorPager } from '../../../layout/list-pager/cursor-pager';
import { ListPagerComponent } from '../../../layout/list-pager/list-pager.component';
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
    ListPagerComponent,
    FormatDatePipe,
  ],
  templateUrl: './reports-center.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './reports-center.component.scss',
})
export class ReportsCenterComponent implements OnInit {
  private readonly reportsApi = inject(ReportsApiService);
  private readonly translate = inject(TranslateService);

  readonly isLoadingArtifacts = signal<boolean>(true);
  readonly artifacts = signal<ReportArtifact[]>([]);
  readonly artifactsPager = new CursorPager('report-artifacts');
  readonly artifactsErrorMessage = signal<string | null>(null);
  readonly artifactsErrorTraceId = signal<string | null>(null);

  readonly selectedKind = signal<ReportKind | 'all'>('all');
  readonly selectedStatus = signal<ReportArtifactStatus | 'all'>('all');

  readonly isLoadingSchedules = signal<boolean>(true);
  readonly schedules = signal<ReportSchedule[]>([]);
  readonly schedulesPager = new CursorPager('report-schedules');
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

  private readonly reloadArtifacts = new Subject<Parameters<ReportsApiService['getArtifacts']>[0]>();
  private readonly reloadSchedules = new Subject<Parameters<ReportsApiService['getSchedules']>[0]>();

  constructor() {
    this.reloadArtifacts
      .pipe(
        switchMap((params) => {
          this.isLoadingArtifacts.set(true);
          this.artifactsErrorMessage.set(null);
          this.artifactsErrorTraceId.set(null);

          return this.reportsApi.getArtifacts(params).pipe(
            catchError((err: unknown) => {
              this.isLoadingArtifacts.set(false);
              if (!this.artifactsPager.failed()) this.artifacts.set([]);
              this.handleArtifactError(err);
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((res) => {
        if (!this.artifactsPager.loaded(res)) {
          this.loadArtifacts();
          return;
        }
        this.artifacts.set([...res.items]);
        this.isLoadingArtifacts.set(false);
      });

    this.reloadSchedules
      .pipe(
        switchMap((params) => {
          this.isLoadingSchedules.set(true);
          this.schedulesErrorMessage.set(null);
          this.schedulesErrorTraceId.set(null);

          return this.reportsApi.getSchedules(params).pipe(
            catchError((err: unknown) => {
              this.isLoadingSchedules.set(false);
              if (!this.schedulesPager.failed()) this.schedules.set([]);
              this.handleScheduleError(err);
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((res) => {
        if (!this.schedulesPager.loaded(res)) {
          this.loadSchedules();
          return;
        }
        this.schedules.set([...res.items]);
        this.isLoadingSchedules.set(false);
      });
  }

  ngOnInit(): void {
    this.loadArtifacts();
    this.loadSchedules();
  }

  loadArtifacts(): void {
    const kind = this.selectedKind();
    const status = this.selectedStatus();
    this.reloadArtifacts.next({
      ...this.artifactsPager.params(),
      kind: kind === 'all' ? undefined : kind,
      status: status === 'all' ? undefined : status,
    });
  }

  onFilterChange(): void {
    this.artifacts.set([]);
    this.artifactsPager.reset();
    this.loadArtifacts();
  }

  clearFilters(): void {
    this.selectedKind.set('all');
    this.selectedStatus.set('all');
    this.onFilterChange();
  }

  loadSchedules(): void {
    this.reloadSchedules.next(this.schedulesPager.params());
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
