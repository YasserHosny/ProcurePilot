import { CommonModule, NgClass } from '@angular/common';
import { Component, Input, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { Product, Supplier } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import type {
  BasketSplitJob,
  OptimisationConstraint,
  ViolatedOptimisationConstraint,
} from '../offers-api';

@Component({
  selector: 'app-basket-split-results',
  standalone: true,
  imports: [
    CommonModule,
    NgClass,
    MatCardModule,
    MatIconModule,
    MatDividerModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './basket-split-results.component.html',
  styleUrl: './basket-split-results.component.scss',
})
export class BasketSplitResultsComponent {
  private readonly translate = inject(TranslateService);

  @Input({ required: true }) currentJob!: BasketSplitJob | null;
  @Input({ required: true }) suppliers: readonly Supplier[] = [];
  @Input({ required: true }) products: readonly Product[] = [];
  @Input({ required: true }) solverConfidence: string | null | undefined = null;
  @Input({ required: true }) validUntil: string | null | undefined = null;
  @Input({ required: true }) appliedConstraints: readonly OptimisationConstraint[] = [];
  @Input({ required: true }) violatedConstraints: readonly ViolatedOptimisationConstraint[] = [];
  @Input({ required: true }) riskNotes: readonly string[] = [];
  @Input({ required: true }) singleSupplierSavings!: {
    type: 'split_saves' | 'no_savings' | 'single_only' | 'neither_feasible';
    cheaperSupplierName?: string;
    savingsAmount?: string;
    currency?: string;
  };

  translateRiskNote(note: string): string {
    const key = `advancedBasket.riskNotes.${note}`;
    const translated = this.translate.instant(key);
    return translated !== key ? translated : note;
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
