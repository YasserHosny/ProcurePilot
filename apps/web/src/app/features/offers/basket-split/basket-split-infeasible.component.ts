
import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { Product, Supplier } from '../../../core/api/models';
import type { BasketSplitJob, ViolatedOptimisationConstraint } from '../offers-api';
import { constraintText } from './constraint-text';
import type { BasketSplitUIState } from './basket-split-state';

@Component({
  selector: 'app-basket-split-infeasible',
  standalone: true,
  imports: [
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    TranslatePipe
],
  templateUrl: './basket-split-infeasible.component.html',
  styleUrl: './basket-split-infeasible.component.scss',
})
export class BasketSplitInfeasibleComponent {
  private readonly translate = inject(TranslateService);

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

  /** Specific copy when the solver service never ran the job; null falls back to the generic text. */
  failureMessageKey(): string | null {
    const code = this.currentJob?.error?.['code'];
    if (code === 'optimiser_unavailable') return 'basketSplit.status.unavailableMessage';
    if (code === 'optimiser_timeout') return 'basketSplit.status.timeoutMessage';
    if (code === 'no_offers_for_products') return 'basketSplit.status.noCurrentOffers';
    return null;
  }

  failureMessageParams(): Record<string, string> {
    const ids = this.currentJob?.error?.['product_ids'];
    const names = Array.isArray(ids) ? ids.map((id) => this.getProductName(String(id))).join(', ') : '';
    return { products: names };
  }

  constraintLabel(constraint: ViolatedOptimisationConstraint): string {
    return constraintText(
      constraint,
      this.translate,
      (id) => this.getSupplierName(id),
      'violated',
    );
  }

  getSupplierName(supplierId: string): string {
    const s = this.suppliers.find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getProductName(productId: string): string {
    const p = this.products.find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }
}
