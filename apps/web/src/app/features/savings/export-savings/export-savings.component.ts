import { NgClass, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { Subscription, interval, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Supplier } from '../../../core/api/models';
import { RoleDirective } from '../../../core/auth/role.directive';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  type ExportCreate,
  type ExportFormat,
  type ExportJob,
  ExportsApiService,
} from '../exports-api';
import {
  type ExportJobUIState,
  determineExportJobUIState,
} from '../export-job-state';

@Component({
  selector: 'app-export-savings',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    NgIf,
    NgClass,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatRadioModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
    RoleDirective,
  ],
  templateUrl: './export-savings.component.html',
  styleUrl: './export-savings.component.scss',
})
export class ExportSavingsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly exportsApi = inject(ExportsApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);

  readonly isLoading = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);
  readonly suppliers = signal<Supplier[]>([]);
  readonly currentJob = signal<ExportJob | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly uiState = computed<ExportJobUIState>(() => {
    return determineExportJobUIState(this.currentJob(), this.isSubmitting());
  });

  private pollSubscription: Subscription | null = null;

  // Default date range: current year to date
  readonly form = this.fb.group({
    format: ['xlsx' as ExportFormat, [Validators.required]],
    period_start: [new Date(new Date().getFullYear(), 0, 1), [Validators.required]],
    period_end: [new Date(), [Validators.required]],
    supplier_id: [''],
  });

  ngOnInit(): void {
    this.loadSuppliers();

    this.route.paramMap.subscribe((params) => {
      const jobId = params.get('id');
      if (jobId) {
        this.fetchJob(jobId);
      }
    });
  }

  private loadSuppliers(): void {
    this.api.suppliers({ limit: 100, status: 'all' }).subscribe({
      next: (res) => this.suppliers.set(res.items),
      error: () => undefined,
    });
  }

  submitExport(): void {
    if (this.form.invalid || !this.isWriter()) {
      this.form.markAllAsTouched();
      return;
    }

    const fv = this.form.getRawValue();
    const startDate = fv.period_start!;
    const endDate = fv.period_end!;

    if (startDate > endDate) {
      this.errorMessage.set(this.translate.instant('exports.validation.invalidDateRange'));
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const payload: ExportCreate = {
      kind: 'savings_ledger',
      format: fv.format as ExportFormat,
      filters: {
        period_start: startDate.toISOString().split('T')[0],
        period_end: endDate.toISOString().split('T')[0],
        supplier_id: fv.supplier_id ? fv.supplier_id : null,
      },
    };

    this.exportsApi
      .createExport(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          this.isSubmitting.set(false);
          this.currentJob.set(job);
          void this.router.navigate(['/savings/export', job.id]);
          this.pollJob(job.id);
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.handleError(err);
        },
      });
  }

  fetchJob(jobId: string): void {
    this.isLoading.set(true);
    this.exportsApi
      .getExportJob(jobId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          this.isLoading.set(false);
          if (job.status === 'queued' || job.status === 'running') {
            this.pollJob(job.id);
          }
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
  }

  private pollJob(jobId: string): void {
    this.pollSubscription?.unsubscribe();

    this.pollSubscription = interval(1500)
      .pipe(
        switchMap(() => this.exportsApi.getExportJob(jobId)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (job) => {
          this.currentJob.set(job);
          if (job.status === 'completed' || job.status === 'failed') {
            this.pollSubscription?.unsubscribe();
            this.pollSubscription = null;
          }
        },
        error: (err: unknown) => {
          this.pollSubscription?.unsubscribe();
          this.pollSubscription = null;
          this.handleError(err);
        },
      });
  }

  resetExport(): void {
    this.pollSubscription?.unsubscribe();
    this.pollSubscription = null;
    this.currentJob.set(null);
    this.errorMessage.set(null);
    void this.router.navigate(['/savings/export']);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(apiError?.message ?? err.message);
      return;
    }
    this.errorMessage.set(this.translate.instant('exports.status.failedDesc'));
  }
}
