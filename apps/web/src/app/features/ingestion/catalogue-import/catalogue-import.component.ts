import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { type CatalogueImportResult, IngestionApiService } from '../ingestion-api';

export type CatalogueImportState = 'idle' | 'importing' | 'success' | 'failed';

export const CATALOGUE_IMPORT_MAX_BYTES = 25 * 1024 * 1024; // 25 MB

const SUPPORTED_EXTENSIONS = new Set(['csv', 'xlsx']);

const SUPPORTED_MIME_TYPES = new Set([
  'text/csv',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  'application/csv',
  'text/x-csv',
]);

@Component({
  selector: 'app-catalogue-import',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatExpansionModule,
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: './catalogue-import.component.html',
  styleUrl: './catalogue-import.component.scss',
})
export class CatalogueImportComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly importState = signal<CatalogueImportState>('idle');
  readonly selectedFile = signal<File | null>(null);
  readonly selectedSupplierId = signal<string | null>(null);
  readonly suppliers = signal<Supplier[]>([]);
  readonly isLoadingSuppliers = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly isDragOver = signal<boolean>(false);
  readonly importResult = signal<CatalogueImportResult | null>(null);

  ngOnInit(): void {
    this.loadSuppliers();
  }

  loadSuppliers(): void {
    this.isLoadingSuppliers.set(true);
    this.api
      .suppliers()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.suppliers.set(res.items);
          this.isLoadingSuppliers.set(false);
        },
        error: () => {
          this.suppliers.set([]);
          this.isLoadingSuppliers.set(false);
        },
      });
  }

  onSupplierChange(supplierId: string | null): void {
    this.selectedSupplierId.set(supplierId);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    if (!supplierId) {
      this.selectedFile.set(null);
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!this.selectedSupplierId()) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.supplierRequiredError'));
      input.value = '';
      return;
    }
    if (input.files && input.files.length > 0) {
      this.validateAndSetFile(input.files[0]);
    }
    input.value = '';
  }

  onDropFile(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    if (!this.selectedSupplierId()) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.supplierRequiredError'));
      return;
    }
    if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
      this.validateAndSetFile(event.dataTransfer.files[0]);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    if (this.selectedSupplierId()) {
      this.isDragOver.set(true);
    }
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
  }

  validateAndSetFile(file: File): boolean {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    if (!this.selectedSupplierId()) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.supplierRequiredError'));
      this.selectedFile.set(null);
      return false;
    }

    if (file.size === 0) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.emptyFileError'));
      this.selectedFile.set(null);
      return false;
    }

    if (file.size > CATALOGUE_IMPORT_MAX_BYTES) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.fileTooLargeError'));
      this.selectedFile.set(null);
      return false;
    }

    if (!this.checkFileFormat(file)) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.unsupportedFormatError'));
      this.selectedFile.set(null);
      return false;
    }

    this.selectedFile.set(file);
    return true;
  }

  checkFileFormat(file: File): boolean {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (SUPPORTED_EXTENSIONS.has(ext)) {
      return true;
    }
    if (file.type && SUPPORTED_MIME_TYPES.has(file.type.toLowerCase())) {
      return true;
    }
    return false;
  }

  removeFile(): void {
    this.selectedFile.set(null);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
  }

  submit(): void {
    const supplierId = this.selectedSupplierId();
    if (!supplierId) {
      this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.supplierRequiredError'));
      return;
    }

    const file = this.selectedFile();
    if (!file) {
      return;
    }

    if (!this.validateAndSetFile(file)) {
      return;
    }

    this.importState.set('importing');
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.ingestionApi
      .submitCatalogueImport(supplierId, file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.importResult.set(result);
          this.importState.set('success');
        },
        error: (err: unknown) => {
          this.importState.set('failed');
          this.handleError(err);
        },
      });
  }

  retry(): void {
    if (this.selectedFile() && this.selectedSupplierId()) {
      this.submit();
    } else {
      this.importState.set('idle');
      this.errorMessage.set(null);
      this.errorTraceId.set(null);
    }
  }

  resetForm(): void {
    this.importState.set('idle');
    this.selectedFile.set(null);
    this.selectedSupplierId.set(null);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.importResult.set(null);
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('ingestion.catalogueImport.importFailed'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('ingestion.catalogueImport.importFailed'));
  }
}
