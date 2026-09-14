import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe } from '@ngx-translate/core';

import type { Product, Supplier } from '../../../core/api/models';
import type { BasketSplitJob, ViolatedOptimisationConstraint } from '../offers-api';
import type { BasketSplitUIState } from './basket-split-state';

@Component({
  selector: 'app-basket-split-infeasible',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    TranslatePipe,
  ],
  templateUrl: './basket-split-infeasible.component.html',
  styleUrl: './basket-split-infeasible.component.scss',
})
export class BasketSplitInfeasibleComponent {
  @Input({ required: true }) uiState!: BasketSplitUIState;
  @Input({ required: true }) currentJob!: BasketSplitJob | null;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) isSubmitting = false;
  @Input({ required: true }) errorMessage: string | null = null;
  @Input({ required: true }) suppliers: readonly Supplier[] = [];
  @Input({ required: true }) products: readonly Product[] = [];
  @Input({ required: true }) violatedConstraints: readonly ViolatedOptimisationConstraint[] = [];

  @Output() readonly rerun = new EventEmitter<void>();
  @Output() readonly resetBasket = new EventEmitter<void>();

  getSupplierName(supplierId: string): string {
    const s = this.suppliers.find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getProductName(productId: string): string {
    const p = this.products.find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }
}
