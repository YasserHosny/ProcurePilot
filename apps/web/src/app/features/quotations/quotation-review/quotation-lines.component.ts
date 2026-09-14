import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe } from '@ngx-translate/core';

import type {
  FieldExtraction,
  Money,
  NewQuotationLine,
  QuotationDetail,
  QuotationLine,
} from '../../../core/api/models';

@Component({
  selector: 'app-quotation-lines',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
    TranslatePipe,
  ],
  templateUrl: './quotation-lines.component.html',
  styleUrl: './quotation-lines.component.scss',
})
export class QuotationLinesComponent {
  @Input({ required: true }) quotation!: QuotationDetail;
  @Input({ required: true }) activeExtraction: FieldExtraction | null = null;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) pendingRemoveLineIds = new Set<string>();
  @Input({ required: true }) pendingCorrections = new Map<string, unknown>();
  @Input({ required: true }) pendingNewLines: NewQuotationLine[] = [];
  @Input({ required: true }) isAddingLine = false;
  @Input({ required: true }) newLineText = '';
  @Input({ required: true }) newLineQuantity = '';
  @Input({ required: true }) newLinePriceAmount = '';

  @Output() readonly fieldSelected = new EventEmitter<{
    entityType: 'quotation' | 'quotation_line';
    entityId: string;
    fieldName: string;
  }>();
  @Output() readonly lineMarkedForRemoval = new EventEmitter<string>();
  @Output() readonly lineUnmarkedForRemoval = new EventEmitter<string>();
  @Output() readonly correctionUpdated = new EventEmitter<{
    feId: string;
    newValue: unknown;
  }>();
  @Output() readonly fieldReviewed = new EventEmitter<{
    entityType: 'quotation' | 'quotation_line';
    entityId: string;
    fieldName: string;
    reviewedValue: unknown;
  }>();
  @Output() readonly fieldConfirmedAsIs = new EventEmitter<{
    entityType: 'quotation' | 'quotation_line';
    entityId: string;
    fieldName: string;
  }>();
  @Output() readonly showAddLine = new EventEmitter<void>();
  @Output() readonly cancelAddLine = new EventEmitter<void>();
  @Output() readonly addNewLine = new EventEmitter<void>();
  @Output() readonly newLineTextChange = new EventEmitter<string>();
  @Output() readonly newLineQuantityChange = new EventEmitter<string>();
  @Output() readonly newLinePriceAmountChange = new EventEmitter<string>();

  getFieldExtraction(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
  ): FieldExtraction | undefined {
    return this.quotation?.field_extractions?.find(
      (fe) =>
        fe.entity_type === entityType &&
        fe.entity_id === entityId &&
        fe.field_name === fieldName,
    );
  }

  getEffectiveValue(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
    defaultValue: unknown,
  ): unknown {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return defaultValue;
    if (this.pendingCorrections.has(fe.id)) {
      return this.pendingCorrections.get(fe.id);
    }
    if (fe.corrected_value !== null && fe.corrected_value !== undefined) {
      return fe.corrected_value;
    }
    return fe.extracted_value ?? defaultValue;
  }

  isFieldCorrected(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
  ): boolean {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return false;
    return (
      this.pendingCorrections.has(fe.id) ||
      (fe.corrected_value !== null && fe.corrected_value !== undefined)
    );
  }

  getFieldConfidence(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
  ): number {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    return fe ? parseFloat(fe.confidence) : 1;
  }

  computeLineTotal(line: QuotationLine): string | null {
    const qtyVal = this.getEffectiveValue(
      'quotation_line',
      line.id,
      'quantity',
      line.quantity || '1',
    );
    const priceVal = this.getEffectiveValue(
      'quotation_line',
      line.id,
      'unit_price',
      line.unit_price,
    );
    const qty = parseFloat(String(qtyVal));
    const priceObj = priceVal as Money | null | undefined;
    const price = priceObj ? parseFloat(priceObj.amount) : 0;
    if (isNaN(qty) || isNaN(price)) return null;
    return (qty * price).toFixed(2);
  }

  formatConfidence(score: string | number): number {
    const numeric = typeof score === 'string' ? parseFloat(score) : score;
    return isNaN(numeric) ? 0 : Math.round(numeric * 100);
  }
}
