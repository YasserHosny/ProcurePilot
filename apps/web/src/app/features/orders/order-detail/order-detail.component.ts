import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { catchError, forkJoin, of } from 'rxjs';
import { packLabel } from '../pack-label';

import { ApiService } from '../../../core/api/api.service';
import { FormatService } from '../../../core/format/format.service';
import type { Product } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import {
  OrdersApiService,
  type EvidenceState,
  type LifecycleLineSummary,
  type OrderEvidenceProjection,
  type PurchaseOrderLine,
} from '../orders-api';

@Component({
  selector: 'app-order-detail',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './order-detail.component.html',
  styleUrl: './order-detail.component.scss',
})
export class OrderDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly ordersApi = inject(OrdersApiService);
  private readonly translate = inject(TranslateService);
  private readonly api = inject(ApiService);
  private readonly formatService = inject(FormatService);

  readonly evidence = signal<OrderEvidenceProjection | null>(null);
  readonly products = signal<Map<string, Product>>(new Map());
  readonly isLoading = signal(true);
  readonly isSaving = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly confirmationOpen = signal(false);
  readonly receiptOpen = signal(false);
  readonly cancelOpen = signal(false);
  readonly confirmationReference = signal('');
  readonly confirmationDate = signal('');
  readonly receiptReference = signal('');
  readonly receiptDate = signal('');
  readonly confirmationQuantities = signal<Record<string, string>>({});
  readonly receiptQuantities = signal<Record<string, string>>({});

  private orderId = '';

  ngOnInit(): void {
    this.orderId = this.route.snapshot.paramMap.get('id') ?? '';
    this.loadOrder();
  }

  loadOrder(): void {
    if (!this.orderId) return;
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.ordersApi.getOrder(this.orderId).subscribe({
      next: (value) => {
        this.evidence.set(value);
        this.products.set(new Map());
        const ids = [...new Set(value.order.lines.flatMap(line =>
          line.workspace_product_id ? [line.workspace_product_id] : [],
        ))];
        if (ids.length === 0) {
          this.isLoading.set(false);
          return;
        }
        forkJoin(ids.map(id => this.api.product(id).pipe(catchError(() => of(null)))))
          .subscribe(products => {
            this.products.set(new Map(
              products.flatMap(product => product ? [[product.id, product] as const] : []),
            ));
            this.isLoading.set(false);
          });
      },
      error: () => { this.errorMessage.set(this.translate.instant('orders.loadError')); this.isLoading.set(false); },
    });
  }

  linePriceLabel(line: PurchaseOrderLine): string {
    const product = line.workspace_product_id ? this.products().get(line.workspace_product_id) : undefined;
    const { size, unit, label } = packLabel(product, line.base_unit, this.translate, this.formatService);
    const amount = this.formatService.formatMoney(line.unit_price);
    if (size > 1) {
      const base = this.formatService.formatMoney({ amount: String(parseFloat(line.unit_price.amount) / size), currency: line.unit_price.currency });
      return `${amount} / ${label} · ${base} / ${unit}`;
    }
    return `${amount} / ${unit}`;
  }

  formatQuantity(value: string | null): string {
    return value === null
      ? this.translate.instant('orders.notProvided')
      : this.formatService.formatQuantity(value);
  }

  getStatusLabel(status: string): string { return this.translate.instant(`orders.status.${status}`); }
  getEvidenceLabel(state: EvidenceState): string { return this.translate.instant(`orders.evidence.${state}`); }

  lineSummary(lineId: string): LifecycleLineSummary | undefined {
    return this.evidence()?.lifecycle.lines.find((line) => line.purchase_order_line_id === lineId);
  }

  quantityValue(values: Record<string, string>, line: PurchaseOrderLine): string {
    return values[line.id] ?? '';
  }

  setQuantity(kind: 'confirmation' | 'receipt', lineId: string, value: string): void {
    const target = kind === 'confirmation' ? this.confirmationQuantities : this.receiptQuantities;
    target.set({ ...target(), [lineId]: value });
  }

  submitOrder(): void {
    this.isSaving.set(true);
    this.ordersApi.submitOrder(this.orderId).subscribe({
      next: () => { this.loadOrder(); this.isSaving.set(false); },
      error: () => { this.errorMessage.set(this.translate.instant('orders.saveError')); this.isSaving.set(false); },
    });
  }

  
  cancelOrder(): void {
    this.cancelOpen.set(true);
  }

  confirmCancel(): void {
    this.isSaving.set(true);
    this.ordersApi.cancelOrder(this.orderId).subscribe({
      next: () => { 
        this.loadOrder(); 
        this.cancelOpen.set(false); 
        this.isSaving.set(false); 
      },
      error: () => { 
        this.errorMessage.set(this.translate.instant('orders.saveError')); 
        this.isSaving.set(false); 
      },
    });
  }

  recordConfirmation(): void {
    const current = this.evidence();
    if (!current || !this.confirmationReference().trim() || !this.confirmationDate()) return;
    this.isSaving.set(true);
    this.ordersApi.recordConfirmation(this.orderId, {
      supplier_reference: this.confirmationReference().trim(),
      confirmed_at: `${this.confirmationDate()}T12:00:00Z`,
      expected_delivery_date: null,
      source_kind: 'manual',
      source_reference: this.confirmationReference().trim(),
      lines: current.order.lines.map((line) => ({
        purchase_order_line_id: line.id,
        confirmed_quantity: this.quantityValue(this.confirmationQuantities(), line) || '0',
        confirmed_unit_price: null,
      })),
    }).subscribe({
      next: (value) => { this.evidence.set(value); this.confirmationOpen.set(false); this.isSaving.set(false); },
      error: () => { this.errorMessage.set(this.translate.instant('orders.saveError')); this.isSaving.set(false); },
    });
  }

  recordReceipt(): void {
    const current = this.evidence();
    if (!current || !this.receiptReference().trim() || !this.receiptDate()) return;
    this.isSaving.set(true);
    this.ordersApi.recordReceipt(this.orderId, {
      receipt_reference: this.receiptReference().trim(),
      receipt_date: this.receiptDate(),
      source_kind: 'manual',
      source_reference: this.receiptReference().trim(),
      lines: current.order.lines.map((line) => ({
        purchase_order_line_id: line.id,
        received_quantity: this.quantityValue(this.receiptQuantities(), line) || '0',
      })),
    }).subscribe({
      next: (value) => { this.evidence.set(value); this.receiptOpen.set(false); this.isSaving.set(false); },
      error: () => { this.errorMessage.set(this.translate.instant('orders.saveError')); this.isSaving.set(false); },
    });
  }
}
