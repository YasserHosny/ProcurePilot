import { CommonModule, NgClass } from '@angular/common';
import { Component, Input, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { Product, Supplier } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import type {
  BasketSplitJob,
  OptimisationConstraint,
  ViolatedOptimisationConstraint,
} from '../offers-api';
import { constraintText, isUserFacingConstraint } from './constraint-text';

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
  private readonly format = inject(FormatService);

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

  /** Applied constraints worth showing a buyer (solver internals filtered out). */
  get visibleAppliedConstraints(): readonly OptimisationConstraint[] {
    return this.appliedConstraints.filter(isUserFacingConstraint);
  }

  constraintLabel(constraint: OptimisationConstraint | ViolatedOptimisationConstraint): string {
    return constraintText(constraint, this.translate, (id) => this.getSupplierName(id));
  }

  /**
   * ADR-020: quantities are bought in packs. The solver works in base units, so show
   * "20 × 25 kg" first and the base total secondary. Loose goods (pack of 1) show base only.
   */
  quantityDisplay(line: { workspace_product_id: string; quantity: string }): {
    primary: string;
    secondary: string | null;
  } {
    const product = this.products.find((p) => p.id === line.workspace_product_id);
    const base = parseFloat(line.quantity);
    const rawUnit = product?.base_unit ?? '';
    const unitKey = `rfq.email.units.${rawUnit}`;
    const translatedUnit: string = this.translate.instant(unitKey);
    const unit = translatedUnit === unitKey ? rawUnit : translatedUnit;
    const fmt = (n: number): string =>
      this.format.formatNumber(n, { maximumFractionDigits: 6 });
    const pack = product?.pack;
    const size = pack
      ? parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)))
      : 0;
    if (!Number.isFinite(base) || !Number.isFinite(size) || size <= 1) {
      return { primary: `${Number.isFinite(base) ? fmt(base) : line.quantity} ${unit}`.trim(), secondary: null };
    }
    const packs = base / size;
    return {
      primary: this.translate.instant('basketSplit.result.packQuantity', {
        count: fmt(packs),
        size: fmt(size),
        unit,
      }),
      secondary: this.translate.instant('basketSplit.result.baseEquivalent', {
        total: fmt(base),
        unit,
      }),
    };
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
