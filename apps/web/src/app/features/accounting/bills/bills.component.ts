import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RoleDirective } from '../../../core/auth/role.directive';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import {
  AccountingApiService,
  type BillMatchStatus,
  type BillProviderStatus,
  type ListBillsParams,
  type SyncedBill,
} from '../accounting-api';

@Component({
  selector: 'app-bills',
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
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    RoleDirective,
  ],
  templateUrl: './bills.component.html',
  styleUrl: './bills.component.scss',
})
export class BillsComponent implements OnInit {
  private readonly accountingApi = inject(AccountingApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly isSyncing = signal<boolean>(false);
  readonly bills = signal<SyncedBill[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly matchStatusFilter = signal<BillMatchStatus | 'all'>('all');

  readonly displayedColumns: readonly string[] = [
    'vendor',
    'amount',
    'date',
    'providerStatus',
    'matchedStatus',
  ];

  ngOnInit(): void {
    this.loadBills();
  }

  loadBills(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    const params: ListBillsParams = { limit: 50 };
    const filter = this.matchStatusFilter();
    if (filter !== 'all') {
      params.match_status = filter;
    }

    this.accountingApi.listBills(params).subscribe({
      next: (res) => {
        this.bills.set([...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.errorMessage.set(this.translate.instant('accounting.bills.loadError'));
        this.snackBar.open(
          this.translate.instant('accounting.bills.loadError'),
          undefined,
          { duration: 4000 },
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
    const params: ListBillsParams = {
      cursor,
      limit: 50,
    };
    const filter = this.matchStatusFilter();
    if (filter !== 'all') {
      params.match_status = filter;
    }

    this.accountingApi.listBills(params).subscribe({
      next: (res) => {
        this.bills.set([...this.bills(), ...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoadingMore.set(false);
      },
      error: () => {
        this.isLoadingMore.set(false);
        this.snackBar.open(
          this.translate.instant('accounting.bills.loadError'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  onFilterChange(status: BillMatchStatus | 'all'): void {
    this.matchStatusFilter.set(status);
    this.loadBills();
  }

  triggerSync(): void {
    if (this.isSyncing()) {
      return;
    }
    this.isSyncing.set(true);

    this.accountingApi.triggerSync().subscribe({
      next: () => {
        this.isSyncing.set(false);
        this.snackBar.open(
          this.translate.instant('accounting.bills.syncSuccess'),
          undefined,
          { duration: 4000 },
        );
      },
      error: (err: unknown) => {
        this.isSyncing.set(false);
        const status =
          err instanceof HttpErrorResponse
            ? err.status
            : (err as { status?: number })?.status;

        if (status === 409) {
          this.snackBar.open(
            this.translate.instant('accounting.bills.syncAlreadyRunning'),
            undefined,
            { duration: 4000 },
          );
        } else if (status === 404) {
          this.snackBar.open(
            this.translate.instant('accounting.bills.syncNoConnection'),
            undefined,
            { duration: 4000 },
          );
        } else {
          this.snackBar.open(
            this.translate.instant('accounting.bills.syncFailed'),
            undefined,
            { duration: 4000 },
          );
        }
      },
    });
  }

  getProviderStatusClass(status: BillProviderStatus): string {
    switch (status) {
      case 'open':
        return 'status-open';
      case 'paid':
        return 'status-paid';
      case 'void':
        return 'status-void';
      default:
        return '';
    }
  }

  getProviderStatusLabel(status: BillProviderStatus): string {
    return this.translate.instant(`accounting.bills.providerStatus.${status}`);
  }
}
