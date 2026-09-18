import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  type ApiError,
  type IngestionEmailLog,
  type IngestionEmailStatus,
  IngestionApiService,
  type IngestionStats,
} from '../ingestion-api';

@Component({
  selector: 'app-ingestion-dashboard',
  standalone: true,
  imports: [
    NgClass,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatTableModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly translate = inject(TranslateService);

  readonly isLoadingStats = signal<boolean>(true);
  readonly isLoadingRecentEmails = signal<boolean>(true);
  readonly statsError = signal<string | null>(null);
  readonly recentEmailsError = signal<string | null>(null);

  readonly stats = signal<IngestionStats | null>(null);

  // Recent activity scope: Per plan doc §2, recent activity displays only the 5 most recent
  // inbound emails from GET /ingestion/emails. Captures and catalogue imports are not included
  // because there is no tenant-wide activity listing endpoint for them.
  readonly recentEmails = signal<IngestionEmailLog[]>([]);

  readonly isLoading = computed(() => this.isLoadingStats() || this.isLoadingRecentEmails());
  readonly errorMessage = computed(() => this.statsError() ?? this.recentEmailsError());

  readonly displayedEmailColumns: readonly string[] = [
    'from',
    'subject',
    'status',
    'supplier',
    'receivedAt',
  ];

  ngOnInit(): void {
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.loadStats();
    this.loadRecentEmails();
  }

  loadStats(): void {
    this.isLoadingStats.set(true);
    this.statsError.set(null);

    this.ingestionApi.getStats().subscribe({
      next: (stats) => {
        this.stats.set(stats);
        this.isLoadingStats.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingStats.set(false);
        this.statsError.set(this.getErrorMessage(err));
      },
    });
  }

  loadRecentEmails(): void {
    this.isLoadingRecentEmails.set(true);
    this.recentEmailsError.set(null);

    // Recent activity scope: Fetch only the 5 most recent email logs
    this.ingestionApi.listEmailLogs({ limit: 5 }).subscribe({
      next: (res) => {
        this.recentEmails.set(res.items ?? []);
        this.isLoadingRecentEmails.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingRecentEmails.set(false);
        this.recentEmailsError.set(this.getErrorMessage(err));
      },
    });
  }

  formatRate(rate: number | null | undefined): string {
    if (rate === null || rate === undefined || Number.isNaN(rate)) {
      return '0%';
    }
    return `${Math.round(rate * 100)}%`;
  }

  getRatePercent(rate: number | null | undefined): number {
    if (rate === null || rate === undefined || Number.isNaN(rate)) {
      return 0;
    }
    return Math.min(100, Math.max(0, rate * 100));
  }

  getEmailStatusClass(status: IngestionEmailStatus): string {
    switch (status) {
      case 'completed':
        return 'status-completed';
      case 'processing':
        return 'status-processing';
      case 'received':
        return 'status-received';
      case 'failed':
        return 'status-failed';
      case 'duplicate':
        return 'status-duplicate';
      case 'rejected':
        return 'status-rejected';
      default:
        return 'status-default';
    }
  }

  private getErrorMessage(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      if (typeof apiError?.message === 'string' && apiError.message.trim().length > 0) {
        return apiError.message;
      }
    }
    return this.translate.instant('ingestion.dashboard.error.generic');
  }
}
