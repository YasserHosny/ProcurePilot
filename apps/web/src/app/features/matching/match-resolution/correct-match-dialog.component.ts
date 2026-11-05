import { Component, ChangeDetectionStrategy, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe } from '@ngx-translate/core';

import type {
  BaseUnit,
  MatchCandidate,
  MatchCorrectionRequest,
  MatchOutcome,
  ProductCreate,
  QuotationLineSummary,
} from '../../../core/api/models';
import { FormatPercentPipe } from '../../../core/format/percent.pipe';
import { FormatQuantityPipe } from '../../../core/format/quantity.pipe';
import { UnitLabelPipe } from '../../../core/format/unit-label';
import { ProductPickerComponent } from './product-picker.component';

export interface CorrectMatchDialogData {
  readonly line: QuotationLineSummary;
  readonly candidates: readonly MatchCandidate[];
  readonly expectedCurrentDecisionId: string;
  readonly currentCandidateId?: string | null;
  readonly baseUnits?: readonly SelectableUnit[];
  readonly quotationSupplierId?: string | null;
}

/**
 * A unit the pickers can offer. A unit from the API carries the server's labels; the built-in
 * fallback carries only its code and takes its label from the i18n catalogue (`unitNames`).
 */
export type SelectableUnit = Pick<BaseUnit, 'code' | 'dimension'> & Partial<BaseUnit>;

export const FALLBACK_BASE_UNITS: SelectableUnit[] = [
  { code: 'litre', dimension: 'volume' },
  { code: 'millilitre', dimension: 'volume' },
  { code: 'kilogram', dimension: 'mass' },
  { code: 'gram', dimension: 'mass' },
  { code: 'each', dimension: 'count' },
];

@Component({
  selector: 'app-correct-match-dialog',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatRadioModule,
    MatCheckboxModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    TranslatePipe,
    UnitLabelPipe,
    FormatPercentPipe,
    FormatQuantityPipe,
    ProductPickerComponent,
  ],
  templateUrl: './correct-match-dialog.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './correct-match-dialog.component.scss',
})
export class CorrectMatchDialogComponent {
  private readonly fb = inject(FormBuilder);
  readonly dialogRef = inject(MatDialogRef<CorrectMatchDialogComponent, MatchCorrectionRequest | null>);
  readonly data: CorrectMatchDialogData = inject(MAT_DIALOG_DATA);

  readonly selectedOutcome = signal<MatchOutcome>('same_product');
  readonly selectedCandidateId = signal<string | null>(
    this.data.currentCandidateId ?? (this.data.candidates.length > 0 ? this.data.candidates[0].id : null),
  );
  readonly learnAlias = signal<boolean>(true);

  /** Catalogue products the buyer picked in this dialog, recorded as manual candidates (P-151). */
  private readonly pickedCandidates = signal<MatchCandidate[]>([]);
  readonly allCandidates = computed<readonly MatchCandidate[]>(() => [
    ...this.data.candidates,
    ...this.pickedCandidates().filter((p) => !this.data.candidates.some((c) => c.id === p.id)),
  ]);

  onManualCandidate(candidate: MatchCandidate): void {
    if (!this.pickedCandidates().some((c) => c.id === candidate.id)) {
      this.pickedCandidates.update((list) => [...list, candidate]);
    }
    this.selectCandidate(candidate.id);
  }

  readonly productForm: FormGroup = this.fb.group({
    tenant_name: [this.data.line.original_text, [Validators.required, Validators.maxLength(200)]],
    brand: [''],
    canonical_name: [''],
    variant: [''],
    gtin: ['', [Validators.pattern(/^(\d{8}|\d{12}|\d{13}|\d{14})?$/)]],
    // Left blank on purpose: a default would silently normalise a 10 kg pack as «pcs».
    base_unit: ['', [Validators.required]],
    pack_count: [this.data.line.pack?.pack_count ?? 1, [Validators.required, Validators.min(1)]],
    // Blank when the line has no pack: a made-up «1.0» would turn a 10 kg pack into a 1 kg one.
    unit_size: [this.data.line.pack?.unit_size ?? '', [Validators.required, Validators.pattern(/^\d+(\.\d+)?$/)]],
    preferred_supplier_id: [this.data.quotationSupplierId ?? null],
  });

  selectCandidate(candidateId: string): void {
    this.selectedCandidateId.set(candidateId);
    this.selectedOutcome.set('same_product');
  }

  selectOutcome(outcome: MatchOutcome): void {
    this.selectedOutcome.set(outcome);
    if (outcome === 'no_match_new_product') {
      // Save stays disabled until the form is valid, so it cannot be clicked to reveal what is missing.
      this.productForm.markAllAsTouched();
    }
  }

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  isRfqCandidate(cand: MatchCandidate): boolean {
    return Boolean(cand.reasons?.rfq && !cand.reasons.rfq.not_in_rfq && cand.reasons.rfq.rfq_line_id);
  }

  /** Save only changes something: a different match, or a valid new product. */
  canSave(): boolean {
    if (this.selectedOutcome() === 'no_match_new_product') {
      return this.productForm.valid;
    }
    const chosen = this.selectedCandidateId();
    return chosen !== null && chosen !== (this.data.currentCandidateId ?? null);
  }

  onConfirm(): void {
    const outcome = this.selectedOutcome();

    if (outcome === 'no_match_new_product') {
      if (this.productForm.invalid) {
        this.productForm.markAllAsTouched();
        return;
      }
      const fv = this.productForm.value;
      const productCreate: ProductCreate = {
        tenant_name: String(fv.tenant_name).trim(),
        brand: fv.brand ? String(fv.brand).trim() : null,
        canonical_name: fv.canonical_name ? String(fv.canonical_name).trim() : null,
        variant: fv.variant ? String(fv.variant).trim() : null,
        gtin: fv.gtin ? String(fv.gtin).trim() : null,
        base_unit: fv.base_unit,
        pack: {
          pack_count: Number(fv.pack_count),
          unit_size: String(fv.unit_size).trim(),
        },
        preferred_supplier_id: fv.preferred_supplier_id || null,
      };

      const request: MatchCorrectionRequest = {
        expected_current_decision_id: this.data.expectedCurrentDecisionId,
        outcome: 'no_match_new_product',
        selected_match_candidate_id: null,
        new_product: productCreate,
        learn_alias: this.learnAlias(),
      };
      this.dialogRef.close(request);
      return;
    }

    const request: MatchCorrectionRequest = {
      expected_current_decision_id: this.data.expectedCurrentDecisionId,
      outcome: 'same_product',
      selected_match_candidate_id: this.selectedCandidateId(),
      new_product: null,
      learn_alias: this.learnAlias(),
    };
    this.dialogRef.close(request);
  }

  onCancel(): void {
    this.dialogRef.close(null);
  }
}
