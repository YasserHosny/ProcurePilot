import { NgClass } from '@angular/common';
import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDatepickerModule } from '@angular/material/datepicker';
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

import { EMPTY, Subject } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { CursorPager } from '../../../layout/list-pager/cursor-pager';
import { ListPagerComponent } from '../../../layout/list-pager/list-pager.component';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';
import {
  type IngestionEmailLog,
  type IngestionEmailStatus,
  IngestionApiService,
  type ListEmailLogsParams,
} from '../ingestion-api';

@Component({
  selector: 'app-email-log',
  standalone: true,
  providers: [provideAppDateAdapter()],
  imports: [
    FormsModule,
    NgClass,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    MatTooltipModule,
    TranslatePipe,
    ListPagerComponent,
    FormatDatePipe,
  ],
  templateUrl: './email-log.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './email-log.component.scss',
})
export class EmailLogComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly logs = signal<IngestionEmailLog[]>([]);
  readonly pager = new CursorPager('ingestion-email-log');
  readonly errorMessage = signal<string | null>(null);

  readonly statusFilter = signal<IngestionEmailStatus | 'all'>('all');
  readonly fromDomain = signal<string>('');
  readonly dateFrom = signal<string>('');
  readonly dateTo = signal<string>('');
  readonly dateFromModel = computed(() => parseIsoDateLocal(this.dateFrom()));
  readonly dateToModel = computed(() => parseIsoDateLocal(this.dateTo()));

  onDateFromChange(date: Date | null): void {
    const next = toIsoDateOrNull(date) ?? '';
    if (this.dateFrom() !== next) {
      this.dateFrom.set(next);
      this.onFilterChange();
    }
  }

  onDateToChange(date: Date | null): void {
    const next = toIsoDateOrNull(date) ?? '';
    if (this.dateTo() !== next) {
      this.dateTo.set(next);
      this.onFilterChange();
    }
  }

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

  private readonly reloadSubject = new Subject<ListEmailLogsParams>();

  constructor() {
    this.reloadSubject
      .pipe(
        switchMap((params) => {
          this.isLoading.set(true);
          this.errorMessage.set(null);

          return this.ingestionApi.listEmailLogs(params).pipe(
            catchError(() => {
              this.isLoading.set(false);
              if (!this.pager.failed()) this.logs.set([]);
              this.errorMessage.set(this.translate.instant('ingestion.emailLog.error.generic'));
              this.snackBar.open(
                this.translate.instant('ingestion.emailLog.loadError'),
                undefined,
                { duration: 4000 },
              );
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((res) => {
        if (!this.pager.loaded(res)) {
          this.loadLogs();
          return;
        }
        this.logs.set([...res.items]);
        this.isLoading.set(false);
      });
  }

  ngOnInit(): void {
    this.loadLogs();
  }

  loadLogs(): void {
    const params: ListEmailLogsParams = { ...this.pager.params() };
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
    this.reloadSubject.next(params);
  }

  onFilterChange(): void {
    this.logs.set([]);
    this.pager.reset();
    this.loadLogs();
  }

  resetFilters(): void {
    this.statusFilter.set('all');
    this.fromDomain.set('');
    this.dateFrom.set('');
    this.dateTo.set('');
    this.onFilterChange();
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
