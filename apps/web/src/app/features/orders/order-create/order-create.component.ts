import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatOptionModule, provideNativeDateAdapter } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { catchError, forkJoin, of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Product, Supplier } from '../../../core/api/models';
import { OrdersApiService, type PurchaseOrderCreate } from '../orders-api';

interface OrderLineForm {
  workspace_product_id: FormControl<string | null>;
  description: FormControl<string>;
  quantity: FormControl<number | null>;
  base_unit: FormControl<string>;
  unit_price: FormControl<number | null>;
  line_tax: FormControl<number | null>;
}

@Component({
  selector: 'app-order-create',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatOptionModule,
    RouterLink,
    TranslatePipe,
    DecimalPipe,
  ],
  providers: [provideNativeDateAdapter()],
  templateUrl: './order-create.component.html',
  styleUrl: './order-create.component.scss',
})
export class OrderCreateComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly api = inject(ApiService);
  private readonly ordersApi = inject(OrdersApiService);

  readonly suppliers = signal<Supplier[]>([]);
  readonly products = signal<Product[]>([]);

  readonly isSubmitting = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly form = new FormGroup({
    order_number: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    supplier_id: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    order_date: new FormControl<Date | null>(new Date(), { validators: [Validators.required] }),
    expected_delivery_date: new FormControl<Date | null>(null),
    currency: new FormControl<string>('USD', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^[A-Z]{3}$/)] }),
    order_tax: new FormControl<number>(0, { nonNullable: true, validators: [Validators.min(0)] }),
    lines: new FormArray<FormGroup<OrderLineForm>>([]),
  });

  get lines(): FormArray<FormGroup<OrderLineForm>> {
    return this.form.controls.lines;
  }

  get computedTotals() {
    return () => {
      let linesTotal = 0;
      const lines = this.lines.getRawValue();
      for (const line of lines) {
        const qty = line.quantity || 0;
        const price = line.unit_price || 0;
        const tax = line.line_tax || 0;
        linesTotal += (qty * price) + tax;
      }
      return {
        linesTotal,
        orderTotal: linesTotal,
      };
    };
  }

  ngOnInit(): void {
    forkJoin({
      suppliers: this.api.suppliers({ limit: 100 }).pipe(catchError(() => of({ items: [], next_cursor: null }))),
      products: this.api.products({ status: 'all', limit: 100 }).pipe(catchError(() => of({ items: [], next_cursor: null }))),
    }).subscribe(({ suppliers, products }) => {
      this.suppliers.set(suppliers.items);
      this.products.set(products.items);
      this.addLine();
    });
  }

  addLine(): void {
    this.lines.push(
      new FormGroup<OrderLineForm>({
        workspace_product_id: new FormControl<string | null>(null),
        description: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
        quantity: new FormControl<number | null>(1, { validators: [Validators.required, Validators.min(0.0001)] }),
        base_unit: new FormControl<string>('EA', { nonNullable: true, validators: [Validators.required] }),
        unit_price: new FormControl<number | null>(0, { validators: [Validators.required, Validators.min(0)] }),
        line_tax: new FormControl<number | null>(0, { validators: [Validators.min(0)] }),
      })
    );
  }

  removeLine(index: number): void {
    this.lines.removeAt(index);
  }

  onProductSelected(index: number, productId: string | null): void {
    if (!productId) return;
    const product = this.products().find(p => p.id === productId);
    if (!product) return;

    const lineGroup = this.lines.at(index);
    lineGroup.patchValue({
      description: product.tenant_name,
      base_unit: product.base_unit,
    });
  }

  submit(): void {
    if (this.form.invalid || this.lines.length === 0) return;

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    const value = this.form.getRawValue();
    const currency = value.currency;

    const formatDate = (date: Date | null) => {
      if (!date) return null;
      const d = new Date(date);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    };

    let linesTotalAmount = 0;
    const mappedLines = value.lines.map((line, i) => {
      const qty = line.quantity || 0;
      const price = line.unit_price || 0;
      const tax = line.line_tax || 0;
      const lineTotal = (qty * price) + tax;
      linesTotalAmount += lineTotal;

      return {
        line_number: i + 1,
        workspace_product_id: line.workspace_product_id,
        description: line.description,
        ordered_quantity: qty.toFixed(6), // up to 6 decimal places as per api schema
        base_unit: line.base_unit,
        unit_price: { amount: price.toFixed(4), currency },
        tax: { amount: tax.toFixed(4), currency },
        line_total: { amount: lineTotal.toFixed(4), currency },
      };
    });

    const orderTaxAmount = value.order_tax || 0;

    const payload: PurchaseOrderCreate = {
      order_number: value.order_number,
      supplier_id: value.supplier_id,
      order_date: formatDate(value.order_date)!,
      expected_delivery_date: formatDate(value.expected_delivery_date),
      total: { amount: linesTotalAmount.toFixed(4), currency },
      tax: { amount: orderTaxAmount.toFixed(4), currency },
      source_kind: 'manual',
      source_reference: value.order_number,
      lines: mappedLines,
    };

    this.ordersApi.createOrder(payload).subscribe({
      next: (order) => {
        this.isSubmitting.set(false);
        this.snackBar.open(this.translate.instant('orders.create.success'), undefined, { duration: 3500 });
        this.router.navigate(['/orders', order.id]);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (err instanceof HttpErrorResponse && err.error?.message) {
          this.errorMessage.set(err.error.message);
        } else {
          this.errorMessage.set(this.translate.instant('orders.saveError'));
        }
      },
    });
  }
}
