import { Component, OnInit, inject, signal, ChangeDetectionStrategy, ElementRef, viewChildren } from '@angular/core';

import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, Validators, FormArray, AbstractControl, ValidationErrors } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { EMPTY, Observable, expand, forkJoin, reduce } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import { Rfq, RfqApi, RfqDetail } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { Product, Supplier } from '../../../core/api/models';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';
import { trimDecimal } from '../../../core/format/trim-decimal';
import { normaliseSearchText } from '../../../core/format/search-normalise';

@Component({
  providers: [provideAppDateAdapter()],
  selector: 'app-rfq-create',
  standalone: true,
  imports: [
    RouterModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatIconModule,
    MatDatepickerModule,
    MatProgressSpinnerModule,
    TranslatePipe,
],
  templateUrl: './create.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
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

  readonly quantityInputs = viewChildren<ElementRef<HTMLInputElement>>('quantityInput');

  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  private readonly productValidator = (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    if (!value || typeof value !== 'string' || value.trim() === '') {
      return { required: true };
    }
    const products = this.products();
    if (products.length > 0 && !products.some((p) => p.id === value)) {
      return { required: true, invalidProduct: true };
    }
    return null;
  };

  readonly form = this.fb.nonNullable.group({
    lines: this.fb.array(
      [
        this.fb.nonNullable.group({
          workspace_product_id: ['', [Validators.required, this.productValidator]],
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
  readonly isDuplicated = signal(false);
  readonly isLoadingRfq = signal(false);
  readonly isNotDraft = signal(false);
  readonly isSaving = signal(false);
  readonly isSending = signal(false);
  readonly rfqId = signal<string | null>(null);
  readonly rfqStatus = signal<Rfq['status'] | null>(null);
  readonly rejectedSuppliers = signal<{ supplier_id: string; reason: string }[]>([]);
  readonly errorMessage = signal<string | null>(null);

  productLabel(prod: Product): string {
    return prod.variant ? `${prod.tenant_name} (${prod.variant})` : prod.tenant_name;
  }

  readonly displayProduct = (value: string): string => {
    if (!value) return '';
    const prod = this.products().find((p) => p.id === value);
    return prod ? this.productLabel(prod) : '';
  };

  getFilteredProducts(value: string | null | undefined): Product[] {
    const prods = this.products();
    if (!value) return prods;
    if (prods.some((p) => p.id === value)) {
      return prods;
    }
    const q = normaliseSearchText(value);
    if (!q) return prods;
    return prods.filter((p) => {
      const name = normaliseSearchText(p.tenant_name);
      const variant = p.variant ? normaliseSearchText(p.variant) : '';
      return name.includes(q) || variant.includes(q);
    });
  }

  onProductSelected(index: number): void {
    const inputs = this.quantityInputs();
    const target = inputs[index]?.nativeElement;
    if (target) {
      target.focus();
      setTimeout(() => target.focus(), 0);
    }
  }

  selectedSupplierNames(): string {
    const selectedIds = this.form.controls.supplierIds.value;
    if (!selectedIds || selectedIds.length === 0) return '';
    const map = new Map(this.suppliers().map((s) => [s.id, s.name]));
    return selectedIds
      .map((id) => map.get(id))
      .filter((name): name is string => !!name)
      .join(', ');
  }

  private revalidateLines(): void {
    this.linesFormArray.controls.forEach((c) => {
      c.get('workspace_product_id')?.updateValueAndValidity();
    });
  }

  ngOnInit(): void {
    const routeId = this.route?.snapshot?.paramMap?.get('id') ?? null;
    if (routeId) {
      this.isEditMode.set(true);
      this.rfqId.set(routeId);
      this.loadEditModeData(routeId);
      return;
    }

    const fromId = this.route?.snapshot?.queryParamMap?.get('from') ?? null;
    if (fromId) {
      this.loadDuplicateData(fromId);
      return;
    }

    this.loadAllActiveProducts().subscribe((items) => {
      this.products.set(items);
      this.revalidateLines();
    });
    this.apiService.suppliers({ limit: 100, status: 'active' }).subscribe((res) => {
      this.suppliers.set(res.items.filter((s) => !!s.contact_email));
    });
  }

  private loadAllActiveProducts(): Observable<Product[]> {
    return this.apiService.products({ limit: 100, status: 'active' }).pipe(
      expand((res) =>
        res.next_cursor
          ? this.apiService.products({ limit: 100, status: 'active', cursor: res.next_cursor })
          : EMPTY,
      ),
      reduce((acc, res) => acc.concat(res.items), [] as Product[]),
    );
  }

  private loadDuplicateData(fromId: string): void {
    this.isLoadingRfq.set(true);
    this.errorMessage.set(null);

    forkJoin({
      products: this.loadAllActiveProducts(),
      suppliers: this.apiService.suppliers({ limit: 100, status: 'active' }),
      detail: this.rfqApi.getRfq(fromId),
    }).subscribe({
      next: ({ products, suppliers, detail }) => {
        this.products.set(products);
        const validSuppliers = suppliers.items.filter((s) => !!s.contact_email);
        this.suppliers.set(validSuppliers);
        this.applyDuplicateDetail(detail, validSuppliers);
        this.isLoadingRfq.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingRfq.set(false);
        this.errorMessage.set(
          err instanceof HttpErrorResponse && err.status === 403
            ? this.translate.instant('rfq.creatorOnly')
            : this.getErrorMessage(err, 'rfq.create.saveError'),
        );
      },
    });
  }

  private applyDuplicateDetail(detail: RfqDetail, activeSuppliers: Supplier[]): void {
    this.isDuplicated.set(true);
    this.isEditMode.set(false);
    this.rfqId.set(null);
    this.rfqStatus.set(null);
    this.isNotDraft.set(false);

    this.linesFormArray.clear();
    const linesToLoad =
      detail.lines.length > 0
        ? detail.lines
        : [{ workspace_product_id: '', quantity: '' }];
    for (const line of linesToLoad) {
      const lineGroup = this.fb.nonNullable.group({
        workspace_product_id: [line.workspace_product_id, [Validators.required, this.productValidator]],
        quantity: [trimDecimal(String(line.quantity)), [Validators.required, Validators.min(0.01)]],
      });
      if (line.workspace_product_id && !this.products().some((p) => p.id === line.workspace_product_id)) {
        lineGroup.get('workspace_product_id')?.markAsTouched();
      }
      this.linesFormArray.push(lineGroup);
    }

    const activeSupplierIds = new Set(activeSuppliers.map((s) => s.id));
    const prefilledSuppliers = detail.recipients
      .map((r) => r.supplier_id)
      .filter((id) => activeSupplierIds.has(id));

    this.form.patchValue({
      supplierIds: prefilledSuppliers,
      neededByDate: null,
      tenantTerms: detail.rfq.tenant_terms ?? '',
    });
  }

  private loadEditModeData(rfqId: string): void {
    this.isLoadingRfq.set(true);
    this.errorMessage.set(null);

    forkJoin({
      products: this.loadAllActiveProducts(),
      suppliers: this.apiService.suppliers({ limit: 100, status: 'active' }),
      detail: this.rfqApi.getRfq(rfqId),
    }).subscribe({
      next: ({ products, suppliers, detail }) => {
        this.products.set(products);
        this.suppliers.set(suppliers.items.filter((s) => !!s.contact_email));
        this.applyRfqDetail(detail);
        this.isLoadingRfq.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingRfq.set(false);
        this.errorMessage.set(err instanceof HttpErrorResponse && err.status === 403
          ? this.translate.instant('rfq.creatorOnly') : this.getErrorMessage(err, 'rfq.create.saveError'));
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
      const lineGroup = this.fb.nonNullable.group({
        workspace_product_id: [line.workspace_product_id, [Validators.required, this.productValidator]],
        // numeric(18,6) comes back as '120.000000'; the narrow field would show only its tail.
        quantity: [trimDecimal(String(line.quantity)), [Validators.required, Validators.min(0.01)]],
      });
      if (line.workspace_product_id && !this.products().some((p) => p.id === line.workspace_product_id)) {
        lineGroup.get('workspace_product_id')?.markAsTouched();
      }
      this.linesFormArray.push(lineGroup);
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
        workspace_product_id: ['', [Validators.required, this.productValidator]],
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
        if (err instanceof HttpErrorResponse && err.status === 403) {
          this.errorMessage.set(this.translate.instant('rfq.creatorOnly'));
          return;
        }
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
        const total = res.recipients.length;
        const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
        const key = sent === total && total > 0 ? 'rfq.create.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
        const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
        this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
        if (sent === total && total > 0 && this.router) {
          void this.router.navigate(['/rfq/history'])?.catch(() => undefined);
        }
      },
      error: (err: unknown) => {
        this.isSending.set(false);
        if (err instanceof HttpErrorResponse && err.status === 403) {
          this.errorMessage.set(this.translate.instant('rfq.creatorOnly'));
          return;
        }
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
