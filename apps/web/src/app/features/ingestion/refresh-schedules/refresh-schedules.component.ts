import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
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
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  Product,
  RefreshSchedule,
  Supplier,
} from '../../../core/api/models';
import {
  type CatalogueImportSummary,
  IngestionApiService,
} from '../ingestion-api';

@Component({
  selector: 'app-refresh-schedules',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
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
  ],
  templateUrl: './refresh-schedules.component.html',
  styleUrl: './refresh-schedules.component.scss',
})
export class RefreshSchedulesComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal(true);
  readonly isSaving = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly schedules = signal<RefreshSchedule[]>([]);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);
  readonly importsBySupplier = signal<Record<string, CatalogueImportSummary[]>>({});
  readonly selectedProductId = signal('');
  readonly selectedSupplierId = signal('');
  readonly selectedImportId = signal('');
  readonly cadenceDays = signal(14);
  readonly displayedColumns = ['product', 'supplier', 'cadence', 'nextRefresh', 'source', 'status', 'actions'];

  readonly selectedImports = computed(() =>
    this.importsBySupplier()[this.selectedSupplierId()] ?? [],
  );

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    forkJoin({
      products: this.api.products({ status: 'active', limit: 100 }),
      suppliers: this.api.suppliers({ status: 'active', limit: 100 }),
      schedules: this.api.refreshSchedules({ limit: 100 }),
    }).subscribe({
      next: ({ products, suppliers, schedules }) => {
        this.products.set(products.items);
        this.suppliers.set(suppliers.items);
        this.schedules.set(schedules.items);
        this.loadImports(schedules.items.map((schedule) => schedule.supplier_id));
        this.isLoading.set(false);
      },
      error: (error: unknown) => {
        this.isLoading.set(false);
        this.errorMessage.set(this.getErrorMessage(error));
      },
    });
  }

  onSupplierChange(supplierId: string): void {
    this.selectedSupplierId.set(supplierId);
    this.selectedImportId.set('');
    this.loadImports([supplierId]);
  }

  create(): void {
    const productId = this.selectedProductId();
    const supplierId = this.selectedSupplierId();
    if (!productId || !supplierId || this.cadenceDays() < 1) return;
    this.isSaving.set(true);
    this.api
      .createRefreshSchedule(
        { workspace_product_id: productId, supplier_id: supplierId, cadence_days: this.cadenceDays() },
        globalThis.crypto.randomUUID(),
      )
      .subscribe({
        next: (schedule) => {
          const importId = this.selectedImportId();
          if (importId) {
            this.api.updateRefreshSchedule(schedule.id, { source_import_id: importId }).subscribe({
              next: (updated) => {
                this.addSchedule(updated);
                this.selectedImportId.set('');
                this.isSaving.set(false);
                this.snackBar.open(this.translate.instant('ingestion.refreshSchedules.created'), undefined, {
                  duration: 3500,
                });
              },
              error: (error: unknown) => {
                this.addSchedule(schedule);
                this.isSaving.set(false);
                this.errorMessage.set(this.getErrorMessage(error));
              },
            });
            return;
          }
          this.addSchedule(schedule);
          this.isSaving.set(false);
        },
        error: (error: unknown) => {
          this.isSaving.set(false);
          this.errorMessage.set(this.getErrorMessage(error));
        },
      });
  }

  pauseOrResume(schedule: RefreshSchedule): void {
    const status = schedule.status === 'paused' ? 'active' : 'paused';
    this.api.updateRefreshSchedule(schedule.id, { status }).subscribe({
      next: (updated) => this.schedules.update((items) => items.map((item) => item.id === updated.id ? updated : item)),
      error: (error: unknown) => this.errorMessage.set(this.getErrorMessage(error)),
    });
  }

  assignSource(schedule: RefreshSchedule, importId: string): void {
    if (!importId || importId === schedule.source_import_id) return;
    this.api.updateRefreshSchedule(schedule.id, { source_import_id: importId }).subscribe({
      next: (updated) => {
        this.schedules.update((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.snackBar.open(
          this.translate.instant('ingestion.refreshSchedules.sourceAssigned'),
          undefined,
          { duration: 3500 },
        );
      },
      error: (error: unknown) => this.errorMessage.set(this.getErrorMessage(error)),
    });
  }

  productName(id: string): string {
    return this.products().find((product) => product.id === id)?.tenant_name ?? id;
  }

  supplierName(id: string): string {
    return this.suppliers().find((supplier) => supplier.id === id)?.name ?? id;
  }

  statusLabel(status: RefreshSchedule['status']): string {
    return this.translate.instant(`ingestion.refreshSchedules.status.${status}`);
  }

  importsForSupplier(supplierId: string): CatalogueImportSummary[] {
    return this.importsBySupplier()[supplierId] ?? [];
  }

  private addSchedule(schedule: RefreshSchedule): void {
    this.schedules.update((items) => [schedule, ...items.filter((item) => item.id !== schedule.id)]);
  }

  private loadImports(supplierIds: string[]): void {
    const ids = [...new Set(supplierIds.filter(Boolean))];
    if (ids.length === 0) return;
    forkJoin(ids.map((supplierId) => this.ingestionApi.listCatalogueImports(supplierId, { limit: 100 }))).subscribe({
      next: (responses) => {
        const next = { ...this.importsBySupplier() };
        ids.forEach((supplierId, index) => {
          next[supplierId] = responses[index].items.filter((item) => item.status === 'completed');
        });
        this.importsBySupplier.set(next);
      },
      error: () => undefined,
    });
  }

  private getErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const apiError = error.error as ApiError | undefined;
      if (apiError?.message) return apiError.message;
    }
    return this.translate.instant('ingestion.refreshSchedules.loadError');
  }
}
