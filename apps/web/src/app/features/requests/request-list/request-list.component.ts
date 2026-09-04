import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatOptionModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { ApiError, PurchaseRequest, PurchaseRequestStatus } from '../../../core/api/models';
import { RequestsApiService } from '../requests-api';

const I18N = 'requests';

@Component({
  selector: 'app-request-list',
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatOptionModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
  ],
  templateUrl: './request-list.component.html',
  styleUrl: './request-list.component.scss',
})
export class RequestListComponent implements OnInit {
  private readonly requestsApi = inject(RequestsApiService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly requests = signal<PurchaseRequest[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly statusFilter = signal<PurchaseRequestStatus | ''>('');

  readonly displayedColumns: readonly string[] = [
    'requiredByDate',
    'branch',
    'status',
    'estimatedTotal',
    'actions',
  ];

  ngOnInit(): void {
    this.loadRequests();
  }

  loadRequests(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const status = this.statusFilter() || undefined;
    this.requestsApi.listRequests({ status }).subscribe({
      next: (res) => {
        this.requests.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  onStatusFilterChange(value: PurchaseRequestStatus | ''): void {
    this.statusFilter.set(value);
    this.loadRequests();
  }

  navigateToCreate(): void {
    this.router.navigate(['/requests/new']);
  }

  navigateToDetail(request: PurchaseRequest): void {
    this.router.navigate(['/requests', request.id]);
  }

  withdrawRequest(request: PurchaseRequest): void {
    this.requestsApi.withdrawRequest(request.id).subscribe({
      next: () => {
        this.loadRequests();
        this.snackBar.open(
          this.translate.instant(`${I18N}.withdrawSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => this.handleError(err),
    });
  }

  formatMoney(request: PurchaseRequest): string {
    if (!request.estimated_total) {
      return '—';
    }
    return `${request.estimated_total.currency} ${request.estimated_total.amount}`;
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
  }
}
