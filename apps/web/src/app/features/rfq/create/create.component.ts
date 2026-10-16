import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
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
import { TranslateModule } from '@ngx-translate/core';
import { RfqApi } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { Product, Supplier } from '../../../core/api/models';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslateService } from '@ngx-translate/core';
import { toIsoDateOrNull } from '../../../core/format/iso-date';

@Component({
  selector: 'app-rfq-create',
  standalone: true,
  imports: [
    CommonModule, 
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
    TranslateModule
  ],
  templateUrl: './create.component.html',
  styleUrl: './create.component.scss'
})
export class RfqCreateComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly rfqApi = inject(RfqApi);
  private readonly apiService = inject(ApiService);
  private readonly translate = inject(TranslateService);

  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly form = this.fb.nonNullable.group({
    lines: this.fb.array([
      this.fb.nonNullable.group({
        workspace_product_id: ['', Validators.required],
        quantity: ['', [Validators.required, Validators.min(0.01)]],
      })
    ], Validators.required),
    supplierIds: [[] as string[], Validators.required],
    neededByDate: this.fb.control<Date | null>(null, Validators.required),
    tenantTerms: ['', Validators.maxLength(4000)],
  });

  readonly isSaving = signal(false);
  readonly isSending = signal(false);
  readonly rfqId = signal<string | null>(null);
  readonly rfqStatus = signal<'draft' | 'sent' | null>(null);
  readonly rejectedSuppliers = signal<{ supplier_id: string; reason: string }[]>([]);
  readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.apiService.products({ limit: 100, status: 'active' }).subscribe(res => {
      this.products.set(res.items);
    });
    this.apiService.suppliers({ limit: 100, status: 'active' }).subscribe(res => {
      // Filter out suppliers with no contact_email as requested in the prompt
      this.suppliers.set(res.items.filter(s => !!s.contact_email));
    });
  }

  get linesFormArray() {
    return this.form.get('lines') as FormArray;
  }

  addLine() {
    this.linesFormArray.push(
      this.fb.nonNullable.group({
        workspace_product_id: ['', Validators.required],
        quantity: ['', [Validators.required, Validators.min(0.01)]],
      })
    );
  }

  removeLine(index: number) {
    if (this.linesFormArray.length > 1) {
      this.linesFormArray.removeAt(index);
    }
  }

  onSave() {
    if (this.form.invalid) return;

    this.isSaving.set(true);
    this.errorMessage.set(null);
    this.rejectedSuppliers.set([]);
    
    const val = this.form.getRawValue();
    const payload = {
      lines: val.lines,
      recipient_supplier_ids: val.supplierIds,
      needed_by_date: toIsoDateOrNull(val.neededByDate)!,
      tenant_terms: val.tenantTerms || undefined,
    };

    this.rfqApi.createRfq(payload).subscribe({
      next: (res) => {
        this.rfqId.set(res.rfq.id);
        this.rfqStatus.set(res.rfq.status as 'draft' | 'sent');
        this.rejectedSuppliers.set(res.rejected_recipients);
        this.isSaving.set(false);
      },
      error: (err: unknown) => {
        this.isSaving.set(false);
        this.errorMessage.set(this.getErrorMessage(err, 'rfq.create.saveError'));
      }
    });
  }

  onSend() {
    const id = this.rfqId();
    if (!id) return;
    
    this.isSending.set(true);
    this.errorMessage.set(null);
    this.rfqApi.sendRfq(id).subscribe({
      next: (res) => {
        this.rfqStatus.set(res.rfq.status as 'draft' | 'sent');
        this.isSending.set(false);
      },
      error: (err: unknown) => {
        this.isSending.set(false);
        this.errorMessage.set(this.getErrorMessage(err, 'rfq.create.sendError'));
      }
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
      const labels = [...new Set((Array.isArray(envelope.details) ? envelope.details : [])
        .map(detail => Array.isArray(detail?.loc) ? detail.loc.at(-1) : undefined)
        .filter((field): field is string => typeof field === 'string' && field in fieldKeys))]
        .map(field => this.translate.instant(fieldKeys[field]));
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
