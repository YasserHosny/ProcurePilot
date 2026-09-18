import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
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
  type DiscrepancyStatus,
  type DiscrepancyType,
  type ListDiscrepanciesParams,
  type ReconciliationDiscrepancy,
} from '../accounting-api';

@Component({
  selector: 'app-discrepancies',
  standalone: true,
  imports: [
    FormsModule,
    NgClass,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTableModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    RoleDirective,
  ],
  templateUrl: './discrepancies.component.html',
  styleUrl: './discrepancies.component.scss',
})
export class DiscrepanciesComponent implements OnInit {
  private readonly accountingApi = inject(AccountingApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly discrepancies = signal<ReconciliationDiscrepancy[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly statusFilter = signal<DiscrepancyStatus>('open');

  readonly activeResolvingId = signal<string | null>(null);
  readonly resolutionNote = signal<string>('');
  readonly isResolving = signal<boolean>(false);

  readonly displayedColumns: readonly string[] = [
    'type',
    'details',
    'detectedAt',
    'status',
    'actions',
  ];

  ngOnInit(): void {
    this.loadDiscrepancies();
  }

  loadDiscrepancies(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    const params: ListDiscrepanciesParams = {
      limit: 50,
      status: this.statusFilter(),
    };

    this.accountingApi.listDiscrepancies(params).subscribe({
      next: (res) => {
        this.discrepancies.set([...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        const msg = this.translate.instant('accounting.discrepancies.loadError');
        this.errorMessage.set(msg);
        this.snackBar.open(msg, undefined, { duration: 4000 });
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) {
      return;
    }

    this.isLoadingMore.set(true);
    const params: ListDiscrepanciesParams = {
      cursor,
      limit: 50,
      status: this.statusFilter(),
    };

    this.accountingApi.listDiscrepancies(params).subscribe({
      next: (res) => {
        this.discrepancies.set([...this.discrepancies(), ...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoadingMore.set(false);
      },
      error: () => {
        this.isLoadingMore.set(false);
        this.snackBar.open(
          this.translate.instant('accounting.discrepancies.loadError'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  onStatusFilterChange(status: DiscrepancyStatus): void {
    this.statusFilter.set(status);
    this.activeResolvingId.set(null);
    this.resolutionNote.set('');
    this.loadDiscrepancies();
  }

  startResolve(discrepancy: ReconciliationDiscrepancy): void {
    this.activeResolvingId.set(discrepancy.id);
    this.resolutionNote.set('');
    setTimeout(() => {
      const input = document.querySelector<HTMLInputElement>('[data-testid="resolve-note-input"]');
      input?.focus();
    }, 0);
  }

  cancelResolve(): void {
    this.activeResolvingId.set(null);
    this.resolutionNote.set('');
    setTimeout(() => {
      const resolveBtn = document.querySelector<HTMLButtonElement>('[data-testid="resolve-btn"]');
      resolveBtn?.focus();
    }, 0);
  }

  confirmResolve(discrepancy: ReconciliationDiscrepancy): void {
    if (this.isResolving()) {
      return;
    }

    this.isResolving.set(true);
    const note = this.resolutionNote().trim() || undefined;

    this.accountingApi.resolveDiscrepancy(discrepancy.id, note).subscribe({
      next: () => {
        this.isResolving.set(false);
        this.activeResolvingId.set(null);
        this.resolutionNote.set('');

        if (this.statusFilter() === 'open') {
          this.discrepancies.set(
            this.discrepancies().filter((d) => d.id !== discrepancy.id),
          );
        } else {
          this.loadDiscrepancies();
        }

        this.snackBar.open(
          this.translate.instant('accounting.discrepancies.resolveSuccess'),
          undefined,
          { duration: 4000 },
        );
      },
      error: (err: unknown) => {
        this.isResolving.set(false);
        const status =
          err instanceof HttpErrorResponse
            ? err.status
            : (err as { status?: number })?.status;

        if (status === 409) {
          this.snackBar.open(
            this.translate.instant(
              'accounting.discrepancies.resolveAlreadyResolved',
            ),
            undefined,
            { duration: 4000 },
          );
        } else {
          this.snackBar.open(
            this.translate.instant('accounting.discrepancies.resolveFailed'),
            undefined,
            { duration: 4000 },
          );
        }
      },
    });
  }

  getTypeLabel(type: DiscrepancyType): string {
    return this.translate.instant(`accounting.discrepancies.types.${type}`);
  }

  getTypeClass(type: DiscrepancyType): string {
    switch (type) {
      case 'amount_mismatch':
        return 'type-amount-mismatch';
      case 'unmatched_bill':
        return 'type-unmatched-bill';
      case 'unmatched_purchase':
        return 'type-unmatched-purchase';
      default:
        return '';
    }
  }

  getStatusLabel(status: DiscrepancyStatus): string {
    return this.translate.instant(`accounting.discrepancies.status.${status}`);
  }
}
