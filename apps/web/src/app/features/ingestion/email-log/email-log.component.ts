import { NgClass } from '@angular/common';
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
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  type IngestionEmailLog,
  type IngestionEmailStatus,
  IngestionApiService,
  type ListEmailLogsParams,
} from '../ingestion-api';

@Component({
  selector: 'app-email-log',
  standalone: true,
  imports: [
    FormsModule,
    NgClass,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './email-log.component.html',
  styleUrl: './email-log.component.scss',
})
export class EmailLogComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly logs = signal<IngestionEmailLog[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly statusFilter = signal<IngestionEmailStatus | 'all'>('all');
  readonly fromDomain = signal<string>('');
  readonly dateFrom = signal<string>('');
  readonly dateTo = signal<string>('');

  readonly statusOptions: readonly IngestionEmailStatus[] = [
    'received',
    'processing',
    'completed',
    'failed',
    'duplicate',
    'rejected',
  ];

  readonly displayedColumns: readonly string[] = [
    'receivedAt',
    'from',
    'subject',
    'status',
    'supplier',
    'quotation',
    'error',
  ];

  readonly hasActiveFilters = computed(() => {
    return (
      this.statusFilter() !== 'all' ||
      this.fromDomain().trim().length > 0 ||
      this.dateFrom().length > 0 ||
      this.dateTo().length > 0
    );
  });

  ngOnInit(): void {
    this.loadLogs();
  }

  loadLogs(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    const params: ListEmailLogsParams = { limit: 50 };
    if (this.statusFilter() !== 'all') {
      params.status = this.statusFilter() as IngestionEmailStatus;
    }
    const domain = this.fromDomain().trim();
    if (domain) {
      params.from_domain = domain;
    }
    if (this.dateFrom()) {
      params.date_from = this.dateFrom();
    }
    if (this.dateTo()) {
      params.date_to = this.dateTo();
    }

    this.ingestionApi.listEmailLogs(params).subscribe({
      next: (res) => {
        this.logs.set([...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.errorMessage.set(
          this.translate.instant('ingestion.emailLog.error.generic')
        );
        this.snackBar.open(
          this.translate.instant('ingestion.emailLog.loadError'),
          undefined,
          { duration: 4000 }
        );
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) {
      return;
    }

    this.isLoadingMore.set(true);
    const params: ListEmailLogsParams = {
      cursor,
      limit: 50,
    };
    if (this.statusFilter() !== 'all') {
      params.status = this.statusFilter() as IngestionEmailStatus;
    }
    const domain = this.fromDomain().trim();
    if (domain) {
      params.from_domain = domain;
    }
    if (this.dateFrom()) {
      params.date_from = this.dateFrom();
    }
    if (this.dateTo()) {
      params.date_to = this.dateTo();
    }

    this.ingestionApi.listEmailLogs(params).subscribe({
      next: (res) => {
        this.logs.set([...this.logs(), ...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoadingMore.set(false);
      },
      error: () => {
        this.isLoadingMore.set(false);
        this.snackBar.open(
          this.translate.instant('ingestion.emailLog.loadError'),
          undefined,
          { duration: 4000 }
        );
      },
    });
  }

  onFilterChange(): void {
    this.loadLogs();
  }

  resetFilters(): void {
    this.statusFilter.set('all');
    this.fromDomain.set('');
    this.dateFrom.set('');
    this.dateTo.set('');
    this.loadLogs();
  }

  getStatusClass(status: IngestionEmailStatus): string {
    switch (status) {
      case 'received':
        return 'status-received';
      case 'processing':
        return 'status-processing';
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      case 'duplicate':
        return 'status-duplicate';
      case 'rejected':
        return 'status-rejected';
      default:
        return '';
    }
  }

  getStatusIcon(status: IngestionEmailStatus): string {
    switch (status) {
      case 'received':
        return 'inbox';
      case 'processing':
        return 'hourglass_top';
      case 'completed':
        return 'check_circle';
      case 'failed':
        return 'error';
      case 'duplicate':
        return 'content_copy';
      case 'rejected':
        return 'cancel';
      default:
        return 'help_outline';
    }
  }
}
