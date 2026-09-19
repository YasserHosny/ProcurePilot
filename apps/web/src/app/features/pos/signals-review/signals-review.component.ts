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
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Product } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  PosApiService,
  type SyncedProductSignal,
} from '../pos-api';

@Component({
  selector: 'app-signals-review',
  standalone: true,
  imports: [
    FormsModule,
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
  ],
  templateUrl: './signals-review.component.html',
  styleUrl: './signals-review.component.scss',
})
export class SignalsReviewComponent implements OnInit {
  private readonly posApi = inject(PosApiService);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isSyncing = signal<boolean>(false);
  readonly isMatching = signal<Record<string, boolean>>({});
  readonly unmatchedSignals = signal<SyncedProductSignal[]>([]);
  readonly matchedSignals = signal<SyncedProductSignal[]>([]);
  readonly products = signal<Product[]>([]);
  readonly selectedProducts = signal<Record<string, string>>({});
  readonly errorMessage = signal<string | null>(null);

  readonly unmatchedColumns: readonly string[] = [
    'externalItemName',
    'stockOnHand',
    'salesVelocity',
    'actions',
  ];

  readonly matchedColumns: readonly string[] = [
    'externalItemName',
    'matchedProduct',
    'stockOnHand',
    'salesVelocity',
    'status',
  ];

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    forkJoin({
      products: this.api.products({ status: 'active', limit: 100 }),
      unmatched: this.posApi.listSignals({ matchStatus: 'unmatched' }),
      matched: this.posApi.listSignals({ matchStatus: 'matched' }),
    }).subscribe({
      next: ({ products, unmatched, matched }) => {
        this.products.set(products.items);
        this.unmatchedSignals.set(unmatched.items);
        this.matchedSignals.set(matched.items);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.errorMessage.set(this.translate.instant('pos.signals.loadError'));
        this.snackBar.open(
          this.translate.instant('pos.signals.loadError'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  loadSignals(): void {
    forkJoin({
      unmatched: this.posApi.listSignals({ matchStatus: 'unmatched' }),
      matched: this.posApi.listSignals({ matchStatus: 'matched' }),
    }).subscribe({
      next: ({ unmatched, matched }) => {
        this.unmatchedSignals.set(unmatched.items);
        this.matchedSignals.set(matched.items);
      },
      error: () => {
        this.snackBar.open(
          this.translate.instant('pos.signals.loadError'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  triggerSync(): void {
    if (this.isSyncing()) {
      return;
    }
    this.isSyncing.set(true);

    this.posApi.triggerSync().subscribe({
      next: () => {
        this.isSyncing.set(false);
        this.snackBar.open(
          this.translate.instant('pos.signals.syncSuccess'),
          undefined,
          { duration: 4000 },
        );
        this.loadSignals();
      },
      error: (err: unknown) => {
        this.isSyncing.set(false);
        const status =
          err instanceof HttpErrorResponse
            ? err.status
            : (err as { status?: number })?.status;

        if (status === 409) {
          this.snackBar.open(
            this.translate.instant('pos.signals.syncAlreadyRunning'),
            undefined,
            { duration: 4000 },
          );
        } else if (status === 404) {
          this.snackBar.open(
            this.translate.instant('pos.signals.syncNoConnection'),
            undefined,
            { duration: 4000 },
          );
        } else {
          this.snackBar.open(
            this.translate.instant('pos.signals.syncFailed'),
            undefined,
            { duration: 4000 },
          );
        }
      },
    });
  }

  onProductSelect(signalId: string, productId: string): void {
    this.selectedProducts.update((prev) => ({
      ...prev,
      [signalId]: productId,
    }));
  }

  matchSignal(signalId: string): void {
    const selectedProductId = this.selectedProducts()[signalId];
    if (!selectedProductId || this.isMatching()[signalId]) {
      return;
    }

    this.isMatching.update((prev) => ({ ...prev, [signalId]: true }));

    this.posApi.manuallyMatchSignal(signalId, selectedProductId).subscribe({
      next: () => {
        this.isMatching.update((prev) => ({ ...prev, [signalId]: false }));
        this.snackBar.open(
          this.translate.instant('pos.signals.unmatched.matchSuccess'),
          undefined,
          { duration: 4000 },
        );
        this.loadSignals();
      },
      error: (err: unknown) => {
        this.isMatching.update((prev) => ({ ...prev, [signalId]: false }));
        const status =
          err instanceof HttpErrorResponse
            ? err.status
            : (err as { status?: number })?.status;

        if (status === 409) {
          this.snackBar.open(
            this.translate.instant('pos.signals.unmatched.alreadyMatched'),
            undefined,
            { duration: 4000 },
          );
        } else {
          this.snackBar.open(
            this.translate.instant('pos.signals.unmatched.matchFailed'),
            undefined,
            { duration: 4000 },
          );
        }
      },
    });
  }

  getProductName(workspaceProductId: string | null): string {
    if (!workspaceProductId) {
      return '—';
    }
    const product = this.products().find((p) => p.id === workspaceProductId);
    if (!product) {
      return workspaceProductId;
    }
    return product.variant
      ? `${product.tenant_name} (${product.variant})`
      : product.tenant_name;
  }
}
