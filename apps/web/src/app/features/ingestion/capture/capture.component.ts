import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { type CaptureResult, IngestionApiService } from '../ingestion-api';

export type CaptureState = 'idle' | 'uploading' | 'success' | 'failed';

export const CAPTURE_MAX_BYTES = 10 * 1024 * 1024; // 10 MB

const SUPPORTED_MIME_TYPES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/heic',
  'image/heif',
]);

const SUPPORTED_EXTENSIONS = new Set([
  'pdf',
  'jpg',
  'jpeg',
  'png',
  'heic',
  'heif',
]);

@Component({
  selector: 'app-capture',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: './capture.component.html',
  styleUrl: './capture.component.scss',
})
export class CaptureComponent implements OnInit {
  private readonly ingestionApi = inject(IngestionApiService);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly uploadState = signal<CaptureState>('idle');
  readonly selectedFile = signal<File | null>(null);
  readonly selectedSupplierId = signal<string | null>(null);
  readonly notes = signal<string>('');
  readonly suppliers = signal<Supplier[]>([]);
  readonly isLoadingSuppliers = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly isDragOver = signal<boolean>(false);
  readonly captureResult = signal<CaptureResult | null>(null);

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

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.validateAndSetFile(input.files[0]);
    }
    input.value = '';
  }

  onDropFile(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
      this.validateAndSetFile(event.dataTransfer.files[0]);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
  }

  validateAndSetFile(file: File): boolean {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    if (file.size === 0) {
      this.errorMessage.set(this.translate.instant('ingestion.capture.emptyFileError'));
      this.selectedFile.set(null);
      return false;
    }

    if (file.size > CAPTURE_MAX_BYTES) {
      this.errorMessage.set(this.translate.instant('ingestion.capture.fileTooLargeError'));
      this.selectedFile.set(null);
      return false;
    }

    const mimeType = this.resolveMimeType(file);
    if (!mimeType) {
      this.errorMessage.set(this.translate.instant('ingestion.capture.unsupportedFormatError'));
      this.selectedFile.set(null);
      return false;
    }

    this.selectedFile.set(file);
    return true;
  }

  resolveMimeType(file: File): string | null {
    if (file.type && SUPPORTED_MIME_TYPES.has(file.type.toLowerCase())) {
      return file.type.toLowerCase();
    }
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (SUPPORTED_EXTENSIONS.has(ext)) {
      return ext === 'pdf' ? 'application/pdf' : `image/${ext}`;
    }
    return null;
  }

  removeFile(): void {
    this.selectedFile.set(null);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
  }

  submit(): void {
    const file = this.selectedFile();
    if (!file) {
      return;
    }

    if (!this.validateAndSetFile(file)) {
      return;
    }

    this.uploadState.set('uploading');
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const supplierId = this.selectedSupplierId() ?? undefined;
    const notes = this.notes().trim() || undefined;

    this.ingestionApi
      .submitCapture(file, supplierId, notes)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.captureResult.set(result);
          this.uploadState.set('success');
        },
        error: (err: unknown) => {
          this.uploadState.set('failed');
          this.handleError(err);
        },
      });
  }

  retry(): void {
    if (this.selectedFile()) {
      this.submit();
    } else {
      this.uploadState.set('idle');
      this.errorMessage.set(null);
      this.errorTraceId.set(null);
    }
  }

  resetForm(): void {
    this.uploadState.set('idle');
    this.selectedFile.set(null);
    this.selectedSupplierId.set(null);
    this.notes.set('');
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.captureResult.set(null);
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
          this.translate.instant('ingestion.capture.errors.generic'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('ingestion.capture.errors.generic'));
  }
}
