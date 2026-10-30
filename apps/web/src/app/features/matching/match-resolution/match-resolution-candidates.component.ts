
import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe } from '@ngx-translate/core';

import type { MatchCandidate, MatchOutcome } from '../../../core/api/models';
import { FormatQuantityPipe } from '../../../core/format/quantity.pipe';
import { UnitLabelPipe } from '../../../core/format/unit-label';

export type MeasuredSignalType =
  | 'lexical'
  | 'semantic'
  | 'brand'
  | 'variant'
  | 'pack_unit'
  | 'pack_size'
  | 'price';

export interface RenderedSignal {
  readonly type: MeasuredSignalType;
  readonly labelKey?: string;
  readonly textKey?: string;
  readonly percent?: number;
  readonly isFullSentence?: boolean;
  readonly isTextOnly?: boolean;
}

@Component({
  selector: 'app-match-resolution-candidates',
  standalone: true,
  imports: [
    MatCardModule,
    MatIconModule,
    MatDividerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatQuantityPipe,
    UnitLabelPipe,
  ],
  templateUrl: './match-resolution-candidates.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './match-resolution-candidates.component.scss',
})
export class MatchResolutionCandidatesComponent {
  @Input({ required: true }) candidates: MatchCandidate[] = [];
  @Input({ required: true }) selectedCandidateId: string | null = null;
  @Input({ required: true }) selectedOutcome: MatchOutcome = 'same_product';
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) hasDecision = false;

  @Output() readonly candidateSelected = new EventEmitter<string>();

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  isRfqCandidate(candidate: MatchCandidate): boolean {
    return Boolean(candidate.reasons?.rfq && !candidate.reasons.rfq.not_in_rfq && candidate.reasons.rfq.rfq_line_id);
  }

  getDeterministicHit(cand: MatchCandidate): { key: string; icon: string } | null {
    if (cand.reasons?.alias_hit) {
      return { key: 'matching.resolution.candidates.signals.aliasHit', icon: 'check' };
    }
    if (cand.reasons?.gtin_match) {
      return { key: 'matching.resolution.candidates.signals.gtinMatch', icon: 'qr_code_2' };
    }
    if (cand.reasons?.supplier_code_match) {
      return { key: 'matching.resolution.candidates.signals.supplierCodeMatch', icon: 'tag' };
    }
    return null;
  }

  getMeasuredSignals(cand: MatchCandidate): RenderedSignal[] {
    const reasons = cand.reasons;
    if (!reasons) return [];

    // Deterministic hits show only the deterministic hit line, no measured signals.
    if (reasons.alias_hit || reasons.gtin_match || reasons.supplier_code_match) {
      return [];
    }

    const signals: RenderedSignal[] = [];

    if (reasons.measured != null) {
      const measured = reasons.measured;
      if (measured['lexical_similarity'] !== undefined) {
        signals.push({
          type: 'lexical',
          labelKey: 'matching.resolution.candidates.signals.lexicalMeasured',
          percent: this.formatScore(measured['lexical_similarity']),
          isFullSentence: true,
        });
      }
      if (measured['semantic_similarity'] !== undefined) {
        signals.push({
          type: 'semantic',
          labelKey: 'matching.resolution.candidates.signals.semanticSimilarity',
          percent: this.formatScore(measured['semantic_similarity']),
        });
      }
      if (measured['brand_match'] !== undefined) {
        signals.push({
          type: 'brand',
          labelKey: 'matching.resolution.candidates.signals.brandMatch',
          percent: this.formatScore(measured['brand_match']),
        });
      }
      if (measured['variant_match'] !== undefined) {
        signals.push({
          type: 'variant',
          labelKey: 'matching.resolution.candidates.signals.variantMatch',
          percent: this.formatScore(measured['variant_match']),
        });
      }
      if (measured['pack_unit_match'] !== undefined) {
        const val = measured['pack_unit_match'];
        const isMatch = val === '1.0000' || val === '1' || parseFloat(val) >= 0.5;
        signals.push({
          type: 'pack_unit',
          textKey: isMatch
            ? 'matching.resolution.candidates.signals.packMatches'
            : 'matching.resolution.candidates.signals.packDiffers',
          isTextOnly: true,
        });
      }
      if (measured['pack_size_plausibility'] !== undefined) {
        signals.push({
          type: 'pack_size',
          labelKey: 'matching.resolution.candidates.signals.packSizePlausibility',
          percent: this.formatScore(measured['pack_size_plausibility']),
        });
      }
      if (measured['price_plausibility'] !== undefined) {
        signals.push({
          type: 'price',
          labelKey: 'matching.resolution.candidates.signals.pricePlausibility',
          percent: this.formatScore(measured['price_plausibility']),
        });
      }
    } else {
      // Legacy candidate without measured map (research R4):
      // Treat lexical_similarity as measured; semantic_similarity as measured only when
      // candidate.embedding_model is not stub-hash-v1. If model is not available on candidate,
      // do not show semantic; never show any feature_score entry.
      if (reasons.lexical_similarity != null) {
        signals.push({
          type: 'lexical',
          labelKey: 'matching.resolution.candidates.signals.lexicalMeasured',
          percent: this.formatScore(reasons.lexical_similarity),
          isFullSentence: true,
        });
      }
      if (
        cand.embedding_model &&
        cand.embedding_model !== 'stub-hash-v1' &&
        reasons.semantic_similarity != null
      ) {
        signals.push({
          type: 'semantic',
          labelKey: 'matching.resolution.candidates.signals.semanticSimilarity',
          percent: this.formatScore(reasons.semantic_similarity),
        });
      }
    }

    return signals;
  }
}
