import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe, SlicePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription, interval, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  Job,
  PotentialDuplicate,
  PresignMimeType,
  PresignResponse,
  Quotation,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';

export type UploadState =
  | 'idle'
  | 'uploading'
  | 'duplicate-warning'
  | 'processing'
  | 'extracted'
  | 'failed';

const SUPPORTED_MIME_MAP: Record<string, PresignMimeType> = {
  'application/pdf': 'application/pdf',
  'image/png': 'image/png',
  'image/jpeg': 'image/jpeg',
  'image/tiff': 'image/tiff',
  'text/csv': 'text/csv',
  'application/vnd.ms-excel': 'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

const EXTENSION_MIME_MAP: Record<string, PresignMimeType> = {
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  tif: 'image/tiff',
  tiff: 'image/tiff',
  csv: 'text/csv',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

@Component({
  selector: 'app-quotation-upload',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    DatePipe,
    SlicePipe,
    TranslatePipe,
  ],
  templateUrl: './quotation-upload.component.html',
  styleUrl: './quotation-upload.component.scss',
})
export class QuotationUploadComponent {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly uploadState = signal<UploadState>('idle');
  readonly selectedFile = signal<File | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly isDragOver = signal<boolean>(false);

  readonly createdQuotation = signal<Quotation | null>(null);
  readonly currentJob = signal<Job | null>(null);
  readonly potentialDuplicates = signal<readonly PotentialDuplicate[]>([]);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  private pollSubscription: Subscription | null = null;
  private pendingPresign = signal<PresignResponse | null>(null);

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.validateAndSetFile(input.files[0]);
    }
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

  private validateAndSetFile(file: File): void {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.potentialDuplicates.set([]);
    this.pendingPresign.set(null);

    if (file.size === 0) {
      this.errorMessage.set(this.translate.instant('quotations.upload.emptyFileError'));
      this.selectedFile.set(null);
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      this.errorMessage.set(this.translate.instant('quotations.upload.fileTooLargeError'));
      this.selectedFile.set(null);
      return;
    }

    const mimeType = this.resolveMimeType(file);
    if (!mimeType) {
      this.errorMessage.set(this.translate.instant('quotations.upload.unsupportedFormatError'));
      this.selectedFile.set(null);
      return;
    }

    this.selectedFile.set(file);
  }

  private resolveMimeType(file: File): PresignMimeType | null {
    if (file.type && SUPPORTED_MIME_MAP[file.type]) {
      return SUPPORTED_MIME_MAP[file.type];
    }
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    if (EXTENSION_MIME_MAP[ext]) {
      return EXTENSION_MIME_MAP[ext];
    }
    return null;
  }

  startUpload(): void {
    void this.presignSelectedFile();
  }

  proceedDespiteDuplicate(): void {
    const file = this.selectedFile();
    const presign = this.pendingPresign();
    if (!file || !presign) return;

    this.potentialDuplicates.set([]);
    this.uploadPresignedFile(file, presign);
  }

  cancelUpload(): void {
    this.resetUpload();
  }

  private async presignSelectedFile(): Promise<void> {
    const file = this.selectedFile();
    if (!file) return;

    const mimeType = this.resolveMimeType(file);
    if (!mimeType) {
      this.errorMessage.set(this.translate.instant('quotations.upload.unsupportedFormatError'));
      return;
    }

    this.uploadState.set('uploading');
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.potentialDuplicates.set([]);
    this.pendingPresign.set(null);

    let contentHash: string;
    try {
      contentHash = await this.computeContentHash(file);
    } catch (err: unknown) {
      this.uploadState.set('failed');
      this.handleError(err);
      return;
    }

    this.api
      .presignDocument({
        filename: file.name,
        mime_type: mimeType,
        size_bytes: file.size,
        content_hash: contentHash,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (presign) => {
          const duplicates = presign.potential_duplicates ?? [];
          this.pendingPresign.set(presign);
          this.potentialDuplicates.set(duplicates);
          if (duplicates.length > 0) {
            this.uploadState.set('duplicate-warning');
            return;
          }
          this.uploadPresignedFile(file, presign);
        },
        error: (err: unknown) => {
          this.uploadState.set('failed');
          this.handleError(err);
        },
      });
  }

  private uploadPresignedFile(file: File, presign: PresignResponse): void {
    this.uploadState.set('uploading');
    this.api
      .uploadFileToStorage(presign.upload_url, file, presign.upload_fields)
      .pipe(
        switchMap(() =>
          this.api.createQuotation({
            document_id: presign.document_id,
          }),
        ),
        switchMap((quotation) => {
          this.createdQuotation.set(quotation);
          this.uploadState.set('processing');
          return this.api.extractQuotation(quotation.id);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          this.pollJob(job.id);
        },
        error: (err: unknown) => {
          this.uploadState.set('failed');
          this.handleError(err);
        },
      });
  }

  private async computeContentHash(file: File): Promise<string> {
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  private pollJob(jobId: string): void {
    this.pollSubscription?.unsubscribe();

    this.pollSubscription = interval(1500)
      .pipe(
        switchMap(() => this.api.getJob(jobId)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          if (job.status === 'succeeded') {
            this.uploadState.set('extracted');
            this.pollSubscription?.unsubscribe();
            this.pollSubscription = null;
          } else if (job.status === 'failed') {
            this.uploadState.set('failed');
            this.pollSubscription?.unsubscribe();
            this.pollSubscription = null;
            this.errorMessage.set(
              (job.error?.['message'] as string | undefined) ??
                this.translate.instant('quotations.upload.failedMessage'),
            );
          }
        },
        error: (err: unknown) => {
          this.uploadState.set('failed');
          this.pollSubscription?.unsubscribe();
          this.pollSubscription = null;
          this.handleError(err);
        },
      });
  }

  resetUpload(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = null;
    this.uploadState.set('idle');
    this.selectedFile.set(null);
    this.createdQuotation.set(null);
    this.currentJob.set(null);
    this.potentialDuplicates.set([]);
    this.pendingPresign.set(null);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
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
          this.translate.instant('quotations.upload.failedMessage'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('quotations.upload.failedMessage'));
  }
}
