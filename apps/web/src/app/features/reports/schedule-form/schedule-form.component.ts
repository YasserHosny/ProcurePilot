import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import { type Branch } from '../../../core/api/models';
import {
  type ReportFormat,
  type ReportKind,
  ReportsApiService,
} from '../reports-center/reports-api';

interface ApiErrorShape {
  code?: string;
  message?: string;
  trace_id?: string;
}

@Component({
  selector: 'app-schedule-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    TranslatePipe,
  ],
  templateUrl: './schedule-form.component.html',
  styleUrl: './schedule-form.component.scss',
})
export class ScheduleFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly reportsApi = inject(ReportsApiService);
  private readonly apiService = inject(ApiService);
  private readonly translate = inject(TranslateService);

  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly branches = signal<readonly Branch[]>([]);

  readonly form = this.fb.nonNullable.group({
    kind: this.fb.nonNullable.control<ReportKind>('savings_ledger', Validators.required),
    format: this.fb.nonNullable.control<ReportFormat>('csv', Validators.required),
    weekday: this.fb.nonNullable.control<number>(0, Validators.required),
    locale: this.fb.nonNullable.control<'en' | 'ar'>('en', Validators.required),
    branch_id: this.fb.control<string | null>(null),
  });

  readonly availableFormats = computed<ReportFormat[]>(() => {
    const k = this.form.controls.kind.value;
    if (k === 'spend_by_supplier') {
      return ['csv', 'xlsx'];
    }
    if (k === 'alerts_summary') {
      return ['csv', 'pdf'];
    }
    return ['csv', 'xlsx', 'pdf'];
  });

  ngOnInit(): void {
    const currentLang = this.translate.currentLang;
    if (currentLang === 'ar') {
      this.form.controls.locale.setValue('ar');
    }

    this.loadBranches();

    // Read pre-populated params
    this.route.queryParamMap.subscribe((params) => {
      const kindParam = params.get('kind') as ReportKind | null;
      const formatParam = params.get('format') as ReportFormat | null;
      const branchParam = params.get('branch_id');

      if (
        kindParam &&
        ['savings_ledger', 'spend_by_supplier', 'alerts_summary'].includes(kindParam)
      ) {
        this.form.controls.kind.setValue(kindParam);
      }
      if (formatParam && ['csv', 'xlsx', 'pdf'].includes(formatParam)) {
        this.form.controls.format.setValue(formatParam);
      }
      if (branchParam) {
        this.form.controls.branch_id.setValue(branchParam);
      }
    });

    // Reset format if current selection is invalid for new kind
    this.form.controls.kind.valueChanges.subscribe(() => {
      const currentFmt = this.form.controls.format.value;
      const validFmts = this.availableFormats();
      if (!validFmts.includes(currentFmt)) {
        this.form.controls.format.setValue(validFmts[0]);
      }
    });
  }

  loadBranches(): void {
    this.apiService.listBranches({ is_active: true }).subscribe({
      next: (res) => this.branches.set(res.items || []),
      error: () => this.branches.set([]),
    });
  }

  onSubmit(): void {
    if (this.form.invalid || this.isSubmitting()) {
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const values = this.form.getRawValue();
    const payload = {
      kind: values.kind,
      format: values.format,
      weekday: Number(values.weekday),
      locale: values.locale,
      filters: {
        branch_id: values.branch_id ? values.branch_id : null,
      },
    };

    this.reportsApi.createSchedule(payload).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.router.navigate(['/reports']);
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        if (err.status === 409) {
          this.errorMessage.set(
            this.translate.instant('reports.scheduleForm.errors.conflict')
          );
        } else {
          const body = err.error as ApiErrorShape | null;
          this.errorMessage.set(body?.message ?? err.message ?? 'An error occurred.');
          this.errorTraceId.set(body?.trace_id ?? null);
        }
      },
    });
  }
}
