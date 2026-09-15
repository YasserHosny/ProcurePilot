import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import {
  type PurchaseDeliveryResult,
  type PurchaseOutcomeCreate,
  SavingsApiService,
} from '../savings-api';

@Component({
  selector: 'app-outcome-capture',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
  ],
  templateUrl: './outcome-capture.component.html',
  styleUrl: './outcome-capture.component.scss',
})
export class OutcomeCaptureComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly savingsApi = inject(SavingsApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isSubmitting = signal<boolean>(false);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly deliveryResults: PurchaseDeliveryResult[] = [
    'delivered',
    'ordered',
    'partially_delivered',
    'cancelled',
    'disputed',
  ];

  readonly form = this.fb.group({
    workspace_product_id: ['', [Validators.required]],
    supplier_id: [''],
    quotation_line_id: [''],
    match_decision_id: [''],
    landed_cost_id: [''],
    quantity: ['10', [Validators.required, Validators.pattern(/^\d+(\.\d{1,6})?$/)]],
    base_unit: ['each', [Validators.required]],
    unit_price_amount: ['', [Validators.required, Validators.pattern(/^-?\d+(\.\d{1,4})?$/)]],
    currency: ['GBP', [Validators.required, Validators.pattern(/^[A-Z]{3}$/)]],
    total_paid_amount: ['', [Validators.required, Validators.pattern(/^-?\d+(\.\d{1,4})?$/)]],
    delivery_result: ['delivered' as PurchaseDeliveryResult, [Validators.required]],
    ordered_at: [null as Date | null],
    delivered_at: [null as Date | null],
    notes: ['', [Validators.maxLength(2000)]],
  });

  ngOnInit(): void {
    this.loadProductsAndSuppliers();
    this.setupAutoTotalCalculation();
  }

  private loadProductsAndSuppliers(): void {
    this.isLoading.set(true);

    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (prodRes) => {
        this.products.set(prodRes.items);

        this.api.suppliers({ limit: 100, status: 'active' }).subscribe({
          next: (suppRes) => {
            this.suppliers.set(suppRes.items);
            this.isLoading.set(false);
            this.handleQueryParams();
          },
          error: () => {
            this.isLoading.set(false);
            this.handleQueryParams();
          },
        });
      },
      error: () => {
        this.isLoading.set(false);
      },
    });
  }

  private handleQueryParams(): void {
    const qp = this.route.snapshot.queryParamMap;
    const productId = qp.get('product_id') || qp.get('workspace_product_id');
    const supplierId = qp.get('supplier_id');
    const quotationLineId = qp.get('quotation_line_id');
    const matchDecisionId = qp.get('match_decision_id');
    const landedCostId = qp.get('landed_cost_id');
    const quantity = qp.get('quantity');
    const unitPrice = qp.get('unit_price') || qp.get('unit_price_amount');
    const currency = qp.get('currency') || qp.get('realised_currency');
    const totalPaid = qp.get('total_paid') || qp.get('total_paid_amount') || qp.get('realised_amount');
    const baseUnit = qp.get('base_unit') || qp.get('unit');

    if (productId) {
      this.form.patchValue({ workspace_product_id: productId });
      const foundProduct = this.products().find((p) => p.id === productId);
      if (foundProduct) {
        this.form.patchValue({ base_unit: foundProduct.base_unit });
      }
    }
    if (supplierId) {
      this.form.patchValue({ supplier_id: supplierId });
    }
    if (quotationLineId) {
      this.form.patchValue({ quotation_line_id: quotationLineId });
    }
    if (matchDecisionId) {
      this.form.patchValue({ match_decision_id: matchDecisionId });
    }
    if (landedCostId) {
      this.form.patchValue({ landed_cost_id: landedCostId });
    }
    if (quantity) {
      this.form.patchValue({ quantity });
    }
    if (unitPrice) {
      this.form.patchValue({ unit_price_amount: unitPrice });
    } else if (totalPaid && quantity) {
      const q = parseFloat(quantity);
      const t = parseFloat(totalPaid);
      if (!isNaN(q) && !isNaN(t) && q > 0) {
        this.form.patchValue({ unit_price_amount: (t / q).toFixed(4) });
      }
    }
    if (currency) {
      this.form.patchValue({ currency: currency.toUpperCase() });
    }
    if (baseUnit) {
      const normalizedUnit = this.normalizeBaseUnit(baseUnit);
      if (normalizedUnit) {
        this.form.patchValue({ base_unit: normalizedUnit });
      }
    }
    if (totalPaid) {
      this.form.patchValue({ total_paid_amount: totalPaid });
    } else if (quantity && unitPrice) {
      const q = parseFloat(quantity);
      const u = parseFloat(unitPrice);
      if (!isNaN(q) && !isNaN(u)) {
        this.form.patchValue({ total_paid_amount: (q * u).toFixed(4) });
      }
    }
  }

  private normalizeBaseUnit(rawUnit: string | null | undefined): string | null {
    if (!rawUnit) return null;
    const lower = rawUnit.trim().toLowerCase();
    const map: Record<string, string> = {
      kg: 'kilogram',
      kgs: 'kilogram',
      kilogram: 'kilogram',
      kilograms: 'kilogram',
      g: 'gram',
      gm: 'gram',
      gms: 'gram',
      gram: 'gram',
      grams: 'gram',
      l: 'litre',
      lt: 'litre',
      ltr: 'litre',
      liter: 'litre',
      litre: 'litre',
      litres: 'litre',
      liters: 'litre',
      ml: 'millilitre',
      millilitre: 'millilitre',
      milliliter: 'millilitre',
      ea: 'each',
      pc: 'each',
      pcs: 'each',
      unit: 'each',
      units: 'each',
      each: 'each',
    };
    return map[lower] || lower;
  }

  private setupAutoTotalCalculation(): void {
    // When quantity or unit price changes, compute total paid if not explicitly edited
    this.form.get('quantity')?.valueChanges.subscribe(() => this.recalculateTotal());
    this.form.get('unit_price_amount')?.valueChanges.subscribe(() => this.recalculateTotal());
    this.form.get('workspace_product_id')?.valueChanges.subscribe((prodId) => {
      if (prodId) {
        const prod = this.products().find((p) => p.id === prodId);
        if (prod) {
          this.form.patchValue({ base_unit: prod.base_unit });
        }
      }
    });
  }

  private recalculateTotal(): void {
    const qStr = this.form.get('quantity')?.value;
    const uStr = this.form.get('unit_price_amount')?.value;
    if (qStr && uStr) {
      const q = parseFloat(qStr);
      const u = parseFloat(uStr);
      if (!isNaN(q) && !isNaN(u) && q > 0 && u >= 0) {
        this.form.patchValue({ total_paid_amount: (q * u).toFixed(4) }, { emitEvent: false });
      }
    }
  }

  onSubmit(): void {
    if (this.form.invalid || !this.isWriter()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const fv = this.form.getRawValue();

    // Construct full payload ensuring EVERY user selection is transmitted
    const payload: PurchaseOutcomeCreate = {
      workspace_product_id: fv.workspace_product_id!,
      supplier_id: fv.supplier_id ? fv.supplier_id : null,
      quotation_line_id: fv.quotation_line_id ? fv.quotation_line_id : null,
      match_decision_id: fv.match_decision_id ? fv.match_decision_id : null,
      landed_cost_id: fv.landed_cost_id ? fv.landed_cost_id : null,
      quantity: String(fv.quantity).trim(),
      base_unit: String(fv.base_unit).trim(),
      unit_price: {
        amount: String(fv.unit_price_amount).trim(),
        currency: String(fv.currency).trim().toUpperCase(),
      },
      total_paid: {
        amount: String(fv.total_paid_amount).trim(),
        currency: String(fv.currency).trim().toUpperCase(),
      },
      delivery_result: fv.delivery_result as PurchaseDeliveryResult,
      ordered_at: fv.ordered_at ? new Date(fv.ordered_at).toISOString() : null,
      delivered_at: fv.delivered_at ? new Date(fv.delivered_at).toISOString() : null,
      notes: fv.notes?.trim() || null,
    };

    this.savingsApi.recordPurchase(payload).subscribe({
      next: (created) => {
        this.isSubmitting.set(false);
        this.snackBar.open(
          this.translate.instant('savings.outcomeCapture.successMessage'),
          undefined,
          { duration: 4000 },
        );
        void this.router.navigate(['/savings', created.saving_record.id, 'evidence']);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleError(err);
      },
    });
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(apiError?.message ?? err.message);
      return;
    }
    if (err && typeof err === 'object' && 'error' in err) {
      const apiError = (err as { error?: ApiError }).error;
      if (apiError) {
        this.errorTraceId.set(apiError.trace_id ?? null);
        this.errorMessage.set(apiError.message ?? null);
        return;
      }
    }
    this.errorMessage.set(this.translate.instant('savings.outcomeCapture.validation.productRequired'));
  }
}
