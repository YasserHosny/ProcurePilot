import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators, FormArray } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { forkJoin } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import { Rfq, RfqApi, RfqDetail } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { Product, Supplier } from '../../../core/api/models';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';

@Component({
  selector: 'app-rfq-create',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatProgressSpinnerModule,
    TranslateModule,
  ],
  templateUrl: './create.component.html',
  styleUrl: './create.component.scss',
})
export class RfqCreateComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly rfqApi = inject(RfqApi);
  private readonly apiService = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly route = inject(ActivatedRoute, { optional: true });
  private readonly router = inject(Router, { optional: true });

  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly form = this.fb.nonNullable.group({
    lines: this.fb.array(
      [
        this.fb.nonNullable.group({
          workspace_product_id: ['', Validators.required],
          quantity: ['', [Validators.required, Validators.min(0.01)]],
        }),
      ],
      Validators.required,
    ),
    supplierIds: [[] as string[], Validators.required],
    neededByDate: this.fb.control<Date | null>(null, Validators.required),
    tenantTerms: ['', Validators.maxLength(4000)],
  });

  readonly isEditMode = signal(false);
  readonly isLoadingRfq = signal(false);
  readonly isNotDraft = signal(false);
  readonly isSaving = signal(false);
  readonly isSending = signal(false);
  readonly rfqId = signal<string | null>(null);
  readonly rfqStatus = signal<Rfq['status'] | null>(null);
  readonly rejectedSuppliers = signal<{ supplier_id: string; reason: string }[]>([]);
  readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    const routeId = this.route?.snapshot?.paramMap?.get('id') ?? null;
    if (routeId) {
      this.isEditMode.set(true);
      this.rfqId.set(routeId);
      this.loadEditModeData(routeId);
      return;
    }

    this.apiService.products({ limit: 100, status: 'active' }).subscribe((res) => {
      this.products.set(res.items);
    });
    this.apiService.suppliers({ limit: 100, status: 'active' }).subscribe((res) => {
      this.suppliers.set(res.items.filter((s) => !!s.contact_email));
    });
  }

  private loadEditModeData(rfqId: string): void {
    this.isLoadingRfq.set(true);
    this.errorMessage.set(null);

    forkJoin({
      products: this.apiService.products({ limit: 100, status: 'active' }),
      suppliers: this.apiService.suppliers({ limit: 100, status: 'active' }),
      detail: this.rfqApi.getRfq(rfqId),
    }).subscribe({
      next: ({ products, suppliers, detail }) => {
        this.products.set(products.items);
        this.suppliers.set(suppliers.items.filter((s) => !!s.contact_email));
        this.applyRfqDetail(detail);
        this.isLoadingRfq.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingRfq.set(false);
        this.errorMessage.set(this.getErrorMessage(err, 'rfq.create.saveError'));
      },
    });
  }

  private applyRfqDetail(detail: RfqDetail): void {
    this.rfqId.set(detail.rfq.id);
    this.rfqStatus.set(detail.rfq.status);

    if (detail.rfq.status !== 'draft') {
      this.isNotDraft.set(true);
      return;
    }

    this.isNotDraft.set(false);
    this.linesFormArray.clear();
    const linesToLoad =
      detail.lines.length > 0
        ? detail.lines
        : [{ workspace_product_id: '', quantity: '' }];
    for (const line of linesToLoad) {
      this.linesFormArray.push(
        this.fb.nonNullable.group({
          workspace_product_id: [line.workspace_product_id, Validators.required],
          quantity: [String(line.quantity), [Validators.required, Validators.min(0.01)]],
        }),
      );
    }

    this.form.patchValue({
      supplierIds: detail.recipients.map((r) => r.supplier_id),
      neededByDate: parseIsoDateLocal(detail.rfq.needed_by_date),
      tenantTerms: detail.rfq.tenant_terms ?? '',
    });
  }

  get linesFormArray(): FormArray {
    return this.form.get('lines') as FormArray;
  }

  addLine(): void {
    this.linesFormArray.push(
      this.fb.nonNullable.group({
        workspace_product_id: ['', Validators.required],
        quantity: ['', [Validators.required, Validators.min(0.01)]],
      }),
    );
  }

  removeLine(index: number): void {
    if (this.linesFormArray.length > 1) {
      this.linesFormArray.removeAt(index);
    }
  }

  onSave(): void {
    if (this.form.invalid) return;

    this.isSaving.set(true);
    this.errorMessage.set(null);
    this.rejectedSuppliers.set([]);

    const val = this.form.getRawValue();
    const payload = {
      lines: val.lines.map((line) => ({
        workspace_product_id: line.workspace_product_id,
        quantity: String(line.quantity),
      })),
      recipient_supplier_ids: val.supplierIds,
      needed_by_date: toIsoDateOrNull(val.neededByDate)!,
      tenant_terms: val.tenantTerms || undefined,
    };

    const existingId = this.rfqId();
    const request$ = existingId
      ? this.rfqApi.updateRfq(existingId, payload)
      : this.rfqApi.createRfq(payload);

    request$.subscribe({
      next: (res) => {
        const wasCreate = existingId === null;
        this.rfqId.set(res.rfq.id);
        this.rfqStatus.set(res.rfq.status);
        this.rejectedSuppliers.set(res.rejected_recipients ?? []);
        this.isSaving.set(false);
        this.isEditMode.set(true);
        this.snackBar.open(
          this.translate.instant('rfq.create.draftSaved'),
          this.translate.instant('rfq.history.dismiss'),
          { duration: 4000 },
        );
        if (wasCreate && this.router) {
          void this.router
            .navigate(['/rfq', res.rfq.id, 'edit'], { replaceUrl: true })
            ?.catch(() => undefined);
        }
      },
      error: (err: unknown) => {
        this.isSaving.set(false);
        this.errorMessage.set(this.getErrorMessage(err, 'rfq.create.saveError'));
      },
    });
  }

  onSend(): void {
    const id = this.rfqId();
    if (!id) return;

    this.isSending.set(true);
    this.errorMessage.set(null);
    this.rfqApi.sendRfq(id).subscribe({
      next: (res) => {
        this.rfqStatus.set(res.rfq.status);
        this.isSending.set(false);
        const count = res.recipients?.length || this.form.controls.supplierIds.value.length;
        this.snackBar.open(
          this.translate.instant('rfq.create.sentSuccess', { count }),
          this.translate.instant('rfq.history.dismiss'),
          { duration: 5000 },
        );
        if (this.router) {
          void this.router.navigate(['/rfq/history'])?.catch(() => undefined);
        }
      },
      error: (err: unknown) => {
        this.isSending.set(false);
        this.errorMessage.set(this.getErrorMessage(err, 'rfq.create.sendError'));
      },
    });
  }

  private getErrorMessage(err: unknown, fallbackKey: string): string {
    const fallback = this.translate.instant(fallbackKey);
    if (!(err instanceof HttpErrorResponse) || err.status >= 500) return fallback;

    const envelope = err.error as {
      code?: unknown;
      message?: unknown;
      details?: { loc?: unknown }[];
    } | null;
    if (envelope?.code === 'validation.invalid_request') {
      const fieldKeys: Record<string, string> = {
        lines: 'rfq.create.itemsLabel',
        recipient_supplier_ids: 'rfq.create.suppliersLabel',
        needed_by_date: 'rfq.create.neededByDateLabel',
        tenant_terms: 'rfq.create.tenantTermsLabel',
      };
      const labels = [
        ...new Set(
          (Array.isArray(envelope.details) ? envelope.details : [])
            .map((detail) => (Array.isArray(detail?.loc) ? detail.loc.at(-1) : undefined))
            .filter((field): field is string => typeof field === 'string' && field in fieldKeys),
        ),
      ].map((field) => this.translate.instant(fieldKeys[field]));
      return labels.length
        ? `${this.translate.instant('rfq.create.validationError')} ${labels.join(', ')}`
        : this.translate.instant('rfq.create.validationError');
    }
    const errorKeys: Record<string, string> = {
      'auth.permission_denied': 'rfq.create.errors.permissionDenied',
      'auth.unauthenticated': 'rfq.create.errors.unauthenticated',
      not_found: 'rfq.create.errors.notFound',
      conflict: 'rfq.create.errors.conflict',
      'validation.invalid_value': 'rfq.create.errors.invalidValue',
      service_unavailable: 'rfq.create.errors.serviceUnavailable',
    };
    const key = typeof envelope?.code === 'string' ? errorKeys[envelope.code] : undefined;
    return key ? this.translate.instant(key) : fallback;
  }
}
