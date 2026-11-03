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
  NewQuotationLine,
  QuotationDetail,
  QuotationLine,
} from '../../../core/api/models';
import { CurrencySymbolPipe } from '../../../core/format/currency-symbol.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { FormatService } from '../../../core/format/format.service';
import { parseMoneyInput } from '../../../core/format/money-input';
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

  private readonly drafts = new Map<string, string>();
  private activeFieldKey: string | null = null;

  private fieldKey(lineId: string, fieldName: string): string {
    return `${lineId}:${fieldName}`;
  }

  getDisplayQuantity(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'quantity');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    return this.getEffectiveQuantity(line);
  }

  getDisplayUnitPrice(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'unit_price');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    const amount = this.getEffectiveUnitPriceAmount(line);
    if (!this.isWriter || this.quotation.status === 'reviewed' || this.quotation.status === 'refused') {
      return this.formatUnitPrice(amount);
    }
    return trimDecimalZeros(amount);
  }

  onFieldFocus(line: QuotationLine, fieldName: 'quantity' | 'unit_price', currentValue: string): void {
    const key = this.fieldKey(line.id, fieldName);
    this.activeFieldKey = key;
    this.drafts.set(key, currentValue);
  }

  onQuantityInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'quantity');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onUnitPriceInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'unit_price');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  @Input({ required: true }) quotation!: QuotationDetail;
  @Input({ required: true }) lineTotals: Record<string, string | null> = {};
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
    const parsed = parseMoneyInput(value);
    if (parsed === null) return '0';
    const num = Number(parsed);
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

  getEffectiveQuantity(line: QuotationLine): string {
    const val = this.getEffectiveValue('quotation_line', line.id, 'quantity', line.quantity ?? '');
    return val !== null && val !== undefined ? String(val) : '';
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
    const parsedA = parseMoneyInput(trimmedA);
    const parsedB = parseMoneyInput(trimmedB);
    if (parsedA === null || parsedB === null) {
      return false;
    }
    return Number(parsedA) === Number(parsedB);
  }

  onQuantityChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'quantity');
    this.drafts.delete(key);
    this.commitQuantity(line, targetValue);
  }

  onQuantityBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'quantity');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) {
      this.activeFieldKey = null;
    }
    this.commitQuantity(line, raw);
  }

  private commitQuantity(line: QuotationLine, rawValue: string): void {
    const parsed = parseMoneyInput(rawValue);
    if (parsed === null) {
      return;
    }
    const effective = this.getEffectiveQuantity(line);
    const trimmedTarget = trimDecimalZeros(parsed);
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (
      parsed === effective ||
      trimmedTarget === trimmedEffective ||
      this.isNumericEqual(parsed, effective)
    ) {
      return;
    }

    const fe = this.getFieldExtraction('quotation_line', line.id, 'quantity');
    if (fe) {
      this.pendingCorrections.set(fe.id, parsed);
      this.correctionUpdated.emit({
        feId: fe.id,
        newValue: parsed,
      });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'quantity',
      reviewedValue: parsed,
    });
  }

  getEffectiveUnitPriceCurrency(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'unit_price');
    if (fe && this.pendingCorrections.has(fe.id)) {
      const pending = this.pendingCorrections.get(fe.id);
      if (pending && typeof pending === 'object' && 'currency' in pending) {
        const c = (pending as { currency: unknown }).currency;
        if (typeof c === 'string' && c) return c;
      }
    }
    if (fe?.corrected_value && typeof fe.corrected_value === 'object' && 'currency' in fe.corrected_value) {
      const c = (fe.corrected_value as { currency: unknown }).currency;
      if (typeof c === 'string' && c) return c;
    }
    return line.unit_price?.currency || this.effectiveCurrency || 'USD';
  }

  onUnitPriceChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'unit_price');
    this.drafts.delete(key);
    this.commitUnitPrice(line, targetValue);
  }

  onUnitPriceBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'unit_price');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) {
      this.activeFieldKey = null;
    }
    this.commitUnitPrice(line, raw);
  }

  private commitUnitPrice(line: QuotationLine, rawValue: string): void {
    const parsed = parseMoneyInput(rawValue);
    if (parsed === null) {
      return;
    }
    const effective = this.getEffectiveUnitPriceAmount(line);
    const trimmedTarget = trimDecimalZeros(parsed);
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (
      parsed === effective ||
      trimmedTarget === trimmedEffective ||
      this.isNumericEqual(parsed, effective)
    ) {
      return;
    }

    const currency = this.getEffectiveUnitPriceCurrency(line);
    const newValue = {
      amount: parsed,
      currency,
    };

    const fe = this.getFieldExtraction('quotation_line', line.id, 'unit_price');
    if (fe) {
      this.pendingCorrections.set(fe.id, newValue);
      this.correctionUpdated.emit({
        feId: fe.id,
        newValue,
      });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'unit_price',
      reviewedValue: newValue,
    });
  }

  formatLineTotalDisplay(line: QuotationLine): string {
    const rawTotal = this.lineTotals[line.id];
    if (rawTotal === null || rawTotal === undefined || rawTotal === '') {
      return '—';
    }
    const parsed = parseMoneyInput(rawTotal);
    if (parsed === null) return '—';
    const num = Number(parsed);

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

  formatConfidence(score: string | number): number {
    const numeric = typeof score === 'string' ? parseFloat(score) : score;
    return isNaN(numeric) ? 0 : Math.round(numeric * 100);
  }
}
