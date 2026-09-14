import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { formatConfidenceClass, formatScorePercent } from '../offer-formatting';
import type { Recommendation, RecommendationConfidence } from '../offers-api';
import type { ProjectedOffer } from './compare-projection';

@Component({
  selector: 'app-compare-recommendation',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './compare-recommendation.component.html',
  styleUrl: './compare-recommendation.component.scss',
})
export class CompareRecommendationComponent {
  @Input({ required: true }) recommendation!: Recommendation;
  @Input({ required: true }) bestOffer!: ProjectedOffer | null;
  @Input({ required: true }) requestedQuantity = '1';
  @Input({ required: true }) baseUnit = 'unit';

  getConfidenceClass(confidence: string): string {
    return formatConfidenceClass(confidence as RecommendationConfidence);
  }

  formatScore(score: string | null | undefined): string {
    return formatScorePercent(score);
  }

  formatPercent(val: string | number | null | undefined): string {
    if (val === null || val === undefined || val === '') return '—';
    const n = typeof val === 'number' ? val : parseFloat(val);
    if (isNaN(n)) return '—';
    return `${(n * 100).toFixed(0)}%`;
  }

  getRecordPurchaseParams(offer: ProjectedOffer): Record<string, string> {
    const params: Record<string, string> = {
      product_id: offer.workspace_product_id,
      supplier_id: offer.supplier_id,
      realised_amount: offer.projected_landed_cost.amount,
      realised_currency: offer.projected_landed_cost.currency,
      quantity: this.requestedQuantity,
      unit: this.baseUnit,
    };
    if (offer.quotation_line_id) {
      params['quotation_line_id'] = offer.quotation_line_id;
    }
    return params;
  }

  hasSupplierRiskEvidence(rec: Recommendation | null | undefined): boolean {
    if (!rec?.evidence?.components) return false;
    return !!(
      rec.evidence.components['supplier_risk'] ||
      rec.evidence.components['risk_score'] ||
      rec.evidence.components['supplier_iq']
    );
  }

  hasSupplierRiskNote(riskNotes: readonly string[] | undefined): boolean {
    if (!riskNotes) return false;
    return riskNotes.some(
      (note) =>
        note.includes('supplier_risk') ||
        note.includes('quality') ||
        note === 'high_supplier_risk' ||
        note === 'elevated_supplier_risk',
    );
  }

  getSupplierRiskScore(rec: Recommendation | null | undefined): string | null {
    if (!rec?.evidence?.components) return null;
    return (
      rec.evidence.components['supplier_risk'] ||
      rec.evidence.components['risk_score'] ||
      rec.evidence.components['supplier_iq'] ||
      null
    );
  }

  getSupplierRiskWeight(rec: Recommendation | null | undefined): string {
    if (!rec?.evidence?.weights) return '15';
    const rawWeight = (
      rec.evidence.weights['supplier_risk'] ||
      rec.evidence.weights['risk_score'] ||
      rec.evidence.weights['supplier_iq'] ||
      '15'
    );
    const numericWeight = parseFloat(rawWeight);
    if (!isNaN(numericWeight) && numericWeight > 0 && numericWeight <= 1) {
      return `${Math.round(numericWeight * 100)}`;
    }
    return rawWeight;
  }
}
