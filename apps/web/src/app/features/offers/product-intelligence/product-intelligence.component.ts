import { DecimalPipe, NgClass, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { ApiError, Product, Supplier } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import type { PriceHistoryResponse } from '../offers-api';
import { PriceHistoryChartComponent } from './price-history-chart.component';

@Component({
  selector: 'app-product-intelligence',
  standalone: true,
  imports: [
    FormsModule,
    NgIf,
    NgClass,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    DecimalPipe,
    PriceHistoryChartComponent,
  ],
  templateUrl: './product-intelligence.component.html',
  styleUrl: './product-intelligence.component.scss',
})
export class ProductIntelligenceComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(false);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);
  readonly selectedProductId = signal<string>('');
  readonly selectedSupplierId = signal<string>('');
  readonly selectedWindowMonths = signal<number>(6);

  readonly history = signal<PriceHistoryResponse | null>(null);
  readonly errorMessage = signal<string | null>(null);

  readonly windowOptions = [3, 6, 12, 24];

  readonly tableColumns = [
    'recordedAt',
    'supplier',
    'unitPrice',
    'totalCost',
    'quantity',
    'validity',
  ];

  readonly selectedProduct = computed<Product | null>(() => {
    const id = this.selectedProductId();
    return this.products().find((p) => p.id === id) ?? null;
  });

  ngOnInit(): void {
    this.loadDropdownData();

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id') || params.get('productId');
      if (id) {
        this.selectedProductId.set(id);
        this.fetchPriceHistory(id);
      }
    });

    this.route.queryParamMap.subscribe((queryParams) => {
      const pId = queryParams.get('product_id');
      const sId = queryParams.get('supplier_id');
      const win = queryParams.get('window_months');

      if (win) {
        const parsed = parseInt(win, 10);
        if (!isNaN(parsed) && parsed > 0) {
          this.selectedWindowMonths.set(parsed);
        }
      }
      if (sId !== null && sId !== undefined) {
        this.selectedSupplierId.set(sId);
      }
      if (pId && pId !== this.selectedProductId()) {
        this.selectedProductId.set(pId);
        this.fetchPriceHistory(pId);
      }
    });
  }

  loadDropdownData(): void {
    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.products.set(res.items);
        if (!this.selectedProductId() && res.items.length > 0) {
          const firstId = res.items[0].id;
          this.selectedProductId.set(firstId);
          this.fetchPriceHistory(firstId);
        }
      },
      error: () => {
        // Fallback silently if product dropdown load fails
      },
    });

    this.api.suppliers({ limit: 100, status: 'active' }).subscribe({
      next: (res) => {
        this.suppliers.set(res.items);
      },
      error: () => {
        // Fallback silently if supplier dropdown load fails
      },
    });
  }

  onProductChange(productId: string): void {
    this.selectedProductId.set(productId);
    this.updateUrlAndFetch();
  }

  onSupplierChange(supplierId: string): void {
    this.selectedSupplierId.set(supplierId);
    this.updateUrlAndFetch();
  }

  onWindowChange(months: number): void {
    this.selectedWindowMonths.set(months);
    this.updateUrlAndFetch();
  }

  private updateUrlAndFetch(): void {
    const pId = this.selectedProductId();
    if (!pId) return;

    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        product_id: pId,
        supplier_id: this.selectedSupplierId() || null,
        window_months: this.selectedWindowMonths(),
      },
      queryParamsHandling: 'merge',
    });

    this.fetchPriceHistory(pId);
  }

  fetchPriceHistory(productId: string): void {
    if (!productId) return;
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.api
      .getPriceHistory(productId, {
        supplier_id: this.selectedSupplierId() || undefined,
        window_months: this.selectedWindowMonths(),
      })
      .subscribe({
        next: (res) => {
          this.history.set(res);
          this.isLoading.set(false);
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.history.set(null);
          if (err instanceof HttpErrorResponse) {
            const apiError = err.error as ApiError | undefined;
            if (err.status === 404) {
              this.errorMessage.set(this.translate.instant('productIntelligence.empty.message'));
            } else {
              this.errorMessage.set(apiError?.message ?? err.message);
            }
          } else {
            this.errorMessage.set(this.translate.instant('productIntelligence.empty.message'));
          }
        },
      });
  }
}
