import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy, inject } from '@angular/core';
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
import { CurrencySymbolPipe } from '../../../core/format/currency-symbol.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { FormatService } from '../../../core/format/format.service';
import { sameReviewedValue } from './reviewed-value';

export function trimDecimalZeros(value: string): string {
  if (typeof value !== 'string') return '';
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) return value;
  if (!value.includes('.')) return value;
  return value.replace(/0+$/, '').replace(/\.$/, '');
}

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
    FormatMoneyPipe,
    CurrencySymbolPipe,
  ],
  templateUrl: './quotation-lines.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './quotation-lines.component.scss',
})
export class QuotationLinesComponent {
  private readonly formatService = inject(FormatService);
  readonly trimDecimalZeros = trimDecimalZeros;

  @Input({ required: true }) quotation!: QuotationDetail;
  @Input({ required: true }) effectiveCurrency = 'USD';
  @Input({ required: true }) activeExtraction: FieldExtraction | null = null;
  @Input({ required: true }) isWriter = false;
  @Input() isConfirming = false;
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

  isFieldChanged(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
  ): boolean {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return false;
    const effective = this.pendingCorrections.has(fe.id)
      ? this.pendingCorrections.get(fe.id)
      : fe.corrected_value;
    if (effective === null || effective === undefined) return false;
    return !sameReviewedValue(effective, fe.extracted_value);
  }

  isFieldConfirmedAsIs(
    entityType: 'quotation' | 'quotation_line',
    entityId: string,
    fieldName: string,
  ): boolean {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return false;
    const hasCorrection =
      this.pendingCorrections.has(fe.id) ||
      (fe.corrected_value !== null && fe.corrected_value !== undefined);
    if (!hasCorrection) return false;
    const effective = this.pendingCorrections.has(fe.id)
      ? this.pendingCorrections.get(fe.id)
      : fe.corrected_value;
    return sameReviewedValue(effective, fe.extracted_value);
  }

  formatUnitPrice(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') return '0';
    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num)) return '0';
    const rounded = Math.round(num * 100) / 100;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
  }

  getEffectiveUnitPriceAmount(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'unit_price');
    if (fe && this.pendingCorrections.has(fe.id)) {
      const pending = this.pendingCorrections.get(fe.id);
      if (pending && typeof pending === 'object' && 'amount' in pending) {
        return String((pending as { amount: unknown }).amount ?? '');
      }
      if (typeof pending === 'string') return pending;
    }
    if (fe?.corrected_value) {
      if (typeof fe.corrected_value === 'object' && 'amount' in fe.corrected_value) {
        return String((fe.corrected_value as { amount: unknown }).amount ?? '');
      }
      if (typeof fe.corrected_value === 'string') return fe.corrected_value;
    }
    return line.unit_price?.amount ?? '';
  }

  private isNumericEqual(a: string, b: string): boolean {
    const trimmedA = a.trim();
    const trimmedB = b.trim();
    if (!trimmedA && !trimmedB) {
      return true;
    }
    if (!trimmedA || !trimmedB) {
      return false;
    }
    const na = Number(trimmedA);
    const nb = Number(trimmedB);
    return !isNaN(na) && !isNaN(nb) && na === nb;
  }

  onUnitPriceChange(line: QuotationLine, targetValue: string): void {
    const effective = this.getEffectiveUnitPriceAmount(line);
    const trimmedTarget = trimDecimalZeros(targetValue.trim());
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (
      targetValue === effective ||
      trimmedTarget === trimmedEffective ||
      this.isNumericEqual(targetValue, effective)
    ) {
      return;
    }

    const fe = this.getFieldExtraction('quotation_line', line.id, 'unit_price');
    if (fe) {
      this.correctionUpdated.emit({
        feId: fe.id,
        newValue: {
          amount: targetValue,
          currency: line.unit_price?.currency || this.effectiveCurrency,
        },
      });
    }
  }

  onUnitPriceBlur(line: QuotationLine, targetValue: string): void {
    const effective = this.getEffectiveUnitPriceAmount(line);
    const trimmedTarget = trimDecimalZeros(targetValue.trim());
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (
      targetValue === effective ||
      trimmedTarget === trimmedEffective ||
      this.isNumericEqual(targetValue, effective)
    ) {
      return;
    }

    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'unit_price',
      reviewedValue: {
        amount: targetValue,
        currency: line.unit_price?.currency || this.effectiveCurrency,
      },
    });
  }

  formatLineTotalDisplay(line: QuotationLine): string {
    const rawTotal = this.computeLineTotal(line);
    if (rawTotal === null || rawTotal === undefined || rawTotal === '') {
      return '—';
    }
    const num = parseFloat(rawTotal);
    if (isNaN(num)) return '—';

    const isZero = Math.abs(num) < 0.005;
    const normalized = isZero ? 0 : num;
    const rounded = isZero
      ? 0
      : (Math.sign(normalized) * Math.round(Math.abs(normalized) * 100)) / 100;
    const fractionDigits = Number.isInteger(rounded) ? 0 : 2;

    return this.formatService.formatNumber(normalized, {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
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
