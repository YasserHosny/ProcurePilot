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

export function parsePackInput(raw: unknown): { pack_count: number; unit_size: string; pack_unit?: string } | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === 'object' && raw !== null && 'pack_count' in raw && 'unit_size' in raw) {
    const obj = raw as { pack_count: unknown; unit_size: unknown; pack_unit?: unknown; unit?: unknown };
    return {
      pack_count: Math.round(Number(obj.pack_count)),
      unit_size: String(obj.unit_size),
      pack_unit: obj.pack_unit ? String(obj.pack_unit) : (obj.unit ? String(obj.unit) : undefined),
    };
  }
  if (typeof raw !== 'string') return null;
  let str = raw.trim();
  if (!str || str === '—') return null;

  str = str.replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660));
  str = str.replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0));

  const match = str.match(/^(\d+(?:\.\d+)?)\s*(?:[×x*X]|times|\*)\s*(\d+(?:\.\d+)?)(?:\s+(.+))?$/);
  if (match) {
    const countNum = Math.round(Number(match[1]));
    const sizeNum = match[2];
    const unitStr = match[3]?.trim();
    if (countNum > 0 && Number(sizeNum) > 0) {
      return {
        pack_count: countNum,
        unit_size: sizeNum,
        pack_unit: unitStr || undefined,
      };
    }
  }

  const single = parseMoneyInput(str);
  if (single !== null && Number(single) > 0) {
    return {
      pack_count: Math.round(Number(single)),
      unit_size: '1',
    };
  }

  return null;
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

  getDisplayDescription(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'description');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    return this.getEffectiveDescription(line);
  }

  getDisplayQuantity(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'quantity');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    return this.getEffectiveQuantity(line);
  }

  getDisplayPack(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'pack');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    const count = this.getEffectivePackCount(line);
    const size = this.getEffectiveUnitSize(line);
    const unit = this.getEffectivePackUnit(line);
    if (count !== null && size) {
      return `${count} × ${size}${unit ? ' ' + unit : ''}`;
    }
    if (line.pack) {
      return `${line.pack.pack_count} × ${line.pack.unit_size}${line.pack.unit ? ' ' + line.pack.unit : ''}`;
    }
    return '—';
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

  getDisplayDeliveryFee(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'delivery_fee');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    const amount = this.getEffectiveDeliveryFeeAmount(line);
    if (!amount) return '';
    return trimDecimalZeros(amount);
  }

  getDisplayDiscount(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'discount');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    const amount = this.getEffectiveDiscountAmount(line);
    if (!amount) return '';
    return trimDecimalZeros(amount);
  }

  getDisplayVatRate(line: QuotationLine): string {
    const key = this.fieldKey(line.id, 'vat_rate');
    if (this.activeFieldKey === key && this.drafts.has(key)) {
      return this.drafts.get(key)!;
    }
    const rate = this.getEffectiveVatRate(line);
    if (!rate) return '';
    const num = parseFloat(rate);
    if (isNaN(num)) return rate;
    return String(Math.round(num * 10000) / 100);
  }

  onFieldFocus(line: QuotationLine, fieldName: string, currentValue: string): void {
    const key = this.fieldKey(line.id, fieldName);
    this.activeFieldKey = key;
    this.drafts.set(key, currentValue);
  }

  onDescriptionInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'description');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onQuantityInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'quantity');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onPackInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'pack');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onUnitPriceInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'unit_price');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onDeliveryFeeInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'delivery_fee');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onDiscountInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'discount');
    this.activeFieldKey = key;
    this.drafts.set(key, targetValue);
  }

  onVatRateInput(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'vat_rate');
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
  @Output() readonly correctionReverted = new EventEmitter<string>();
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

  getLineTextExtraction(line: QuotationLine): FieldExtraction | undefined {
    return (
      this.getFieldExtraction('quotation_line', line.id, 'description') ??
      this.getFieldExtraction('quotation_line', line.id, 'original_text')
    );
  }

  getLineTextFieldName(line: QuotationLine): string {
    const fe = this.getLineTextExtraction(line);
    return fe?.field_name || 'original_text';
  }

  getEffectiveDescription(line: QuotationLine): string {
    const fe = this.getLineTextExtraction(line);
    if (fe && this.pendingCorrections.has(fe.id)) {
      return String(this.pendingCorrections.get(fe.id) ?? '');
    }
    if (fe?.corrected_value) {
      return String(fe.corrected_value);
    }
    return (fe?.extracted_value as string) || line.original_text || '';
  }

  isLineTextChanged(line: QuotationLine): boolean {
    const fe = this.getLineTextExtraction(line);
    if (!fe) return false;
    return this.isFieldChanged('quotation_line', line.id, fe.field_name);
  }

  isLineTextConfirmedAsIs(line: QuotationLine): boolean {
    const fe = this.getLineTextExtraction(line);
    if (!fe) return false;
    return this.isFieldConfirmedAsIs('quotation_line', line.id, fe.field_name);
  }

  isLineTextCorrected(line: QuotationLine): boolean {
    const fe = this.getLineTextExtraction(line);
    if (!fe) return false;
    return this.isFieldCorrected('quotation_line', line.id, fe.field_name);
  }

  getLineTextConfidence(line: QuotationLine): number {
    const fe = this.getLineTextExtraction(line);
    return fe ? parseFloat(fe.confidence) : 1;
  }

  confirmLineTextAsIs(line: QuotationLine): void {
    const fe = this.getLineTextExtraction(line);
    if (fe) {
      this.fieldConfirmedAsIs.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: fe.field_name,
      });
    }
  }

  revertLineText(line: QuotationLine): void {
    const fe = this.getLineTextExtraction(line);
    if (fe && this.pendingCorrections.has(fe.id)) {
      this.revertField(fe.id);
    }
  }

  onDescriptionChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'description');
    this.drafts.delete(key);
    this.commitDescription(line, targetValue);
  }

  onDescriptionBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'description');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) this.activeFieldKey = null;
    this.commitDescription(line, raw);
  }

  private commitDescription(line: QuotationLine, rawValue: string): void {
    const trimmed = rawValue.trim();
    if (!trimmed) return;
    const effective = this.getEffectiveDescription(line).trim();
    if (trimmed === effective) return;

    const fe = this.getLineTextExtraction(line);
    if (fe) {
      this.pendingCorrections.set(fe.id, trimmed);
      this.correctionUpdated.emit({ feId: fe.id, newValue: trimmed });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: fe?.field_name || 'original_text',
      reviewedValue: trimmed,
    });
  }

  getEffectivePackCount(line: QuotationLine): number | null {
    const val = this.getEffectiveValue('quotation_line', line.id, 'pack_count', line.pack?.pack_count ?? null);
    if (val !== null && val !== undefined && val !== '') {
      const n = Number(val);
      return Number.isFinite(n) ? Math.round(n) : null;
    }
    const packVal = this.getEffectiveValue('quotation_line', line.id, 'pack', null);
    if (packVal && typeof packVal === 'object' && 'pack_count' in packVal) {
      const n = Number((packVal as { pack_count: unknown }).pack_count);
      return Number.isFinite(n) ? Math.round(n) : null;
    }
    return null;
  }

  getEffectiveUnitSize(line: QuotationLine): string {
    const val = this.getEffectiveValue('quotation_line', line.id, 'unit_size', line.pack?.unit_size ?? '');
    if (val !== null && val !== undefined && val !== '') {
      return String(val);
    }
    const packVal = this.getEffectiveValue('quotation_line', line.id, 'pack', null);
    if (packVal && typeof packVal === 'object' && 'unit_size' in packVal) {
      return String((packVal as { unit_size: unknown }).unit_size ?? '');
    }
    return '';
  }

  getEffectivePackUnit(line: QuotationLine): string {
    const val = this.getEffectiveValue('quotation_line', line.id, 'pack_unit', line.pack?.unit ?? '');
    if (val !== null && val !== undefined && val !== '') {
      return String(val);
    }
    const packVal = this.getEffectiveValue('quotation_line', line.id, 'pack', null);
    if (packVal && typeof packVal === 'object') {
      const u =
        (packVal as { unit?: unknown; pack_unit?: unknown }).unit ??
        (packVal as { unit?: unknown; pack_unit?: unknown }).pack_unit;
      return u ? String(u) : '';
    }
    return '';
  }

  isPackChanged(line: QuotationLine): boolean {
    return (
      this.isFieldChanged('quotation_line', line.id, 'pack') ||
      this.isFieldChanged('quotation_line', line.id, 'pack_count') ||
      this.isFieldChanged('quotation_line', line.id, 'unit_size') ||
      this.isFieldChanged('quotation_line', line.id, 'pack_unit')
    );
  }

  isPackConfirmedAsIs(line: QuotationLine): boolean {
    return (
      this.isFieldConfirmedAsIs('quotation_line', line.id, 'pack') ||
      this.isFieldConfirmedAsIs('quotation_line', line.id, 'pack_count') ||
      this.isFieldConfirmedAsIs('quotation_line', line.id, 'unit_size') ||
      this.isFieldConfirmedAsIs('quotation_line', line.id, 'pack_unit')
    );
  }

  isPackCorrected(line: QuotationLine): boolean {
    return (
      this.isFieldCorrected('quotation_line', line.id, 'pack') ||
      this.isFieldCorrected('quotation_line', line.id, 'pack_count') ||
      this.isFieldCorrected('quotation_line', line.id, 'unit_size') ||
      this.isFieldCorrected('quotation_line', line.id, 'pack_unit')
    );
  }

  hasPersistablePackExtraction(line: QuotationLine): boolean {
    return Boolean(
      this.getFieldExtraction('quotation_line', line.id, 'pack_count') ||
      this.getFieldExtraction('quotation_line', line.id, 'unit_size') ||
      this.getFieldExtraction('quotation_line', line.id, 'pack_unit') ||
      this.getFieldExtraction('quotation_line', line.id, 'pack'),
    );
  }

  getPackConfidence(line: QuotationLine): number {
    const fe =
      this.getFieldExtraction('quotation_line', line.id, 'pack') ??
      this.getFieldExtraction('quotation_line', line.id, 'pack_count') ??
      this.getFieldExtraction('quotation_line', line.id, 'unit_size');
    return fe ? parseFloat(fe.confidence) : 1;
  }

  confirmPackAsIs(line: QuotationLine): void {
    const fe =
      this.getFieldExtraction('quotation_line', line.id, 'pack') ??
      this.getFieldExtraction('quotation_line', line.id, 'pack_count');
    if (fe) {
      this.fieldConfirmedAsIs.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: fe.field_name,
      });
    }
  }

  revertPack(line: QuotationLine): void {
    const fields = ['pack', 'pack_count', 'unit_size', 'pack_unit'];
    for (const f of fields) {
      const fe = this.getFieldExtraction('quotation_line', line.id, f);
      if (fe && this.pendingCorrections.has(fe.id)) {
        this.revertField(fe.id);
      }
    }
  }

  onPackChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'pack');
    this.drafts.delete(key);
    this.commitPack(line, targetValue);
  }

  onPackBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'pack');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) this.activeFieldKey = null;
    this.commitPack(line, raw);
  }

  private commitPack(line: QuotationLine, rawValue: string): void {
    const parsed = parsePackInput(rawValue);
    if (parsed === null) return;

    const effectiveCount = this.getEffectivePackCount(line);
    const effectiveSize = this.getEffectiveUnitSize(line);
    const effectiveUnit = this.getEffectivePackUnit(line);

    const countMatches = effectiveCount !== null && parsed.pack_count === effectiveCount;
    const trimmedTargetSize = trimDecimalZeros(parsed.unit_size);
    const trimmedEffectiveSize = trimDecimalZeros(effectiveSize.trim());
    const sizeMatches =
      parsed.unit_size === effectiveSize ||
      trimmedTargetSize === trimmedEffectiveSize ||
      this.isNumericEqual(parsed.unit_size, effectiveSize);
    const unitMatches = (parsed.pack_unit?.trim() ?? '') === effectiveUnit.trim();

    if (countMatches && sizeMatches && unitMatches) {
      return;
    }

    const feCount = this.getFieldExtraction('quotation_line', line.id, 'pack_count');
    const feSize = this.getFieldExtraction('quotation_line', line.id, 'unit_size');
    const feUnit = this.getFieldExtraction('quotation_line', line.id, 'pack_unit');
    const fePack = this.getFieldExtraction('quotation_line', line.id, 'pack');

    if (feCount && !countMatches) {
      this.pendingCorrections.set(feCount.id, parsed.pack_count);
      this.correctionUpdated.emit({ feId: feCount.id, newValue: parsed.pack_count });
      this.fieldReviewed.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: 'pack_count',
        reviewedValue: parsed.pack_count,
      });
    }

    if (feSize && !sizeMatches) {
      this.pendingCorrections.set(feSize.id, parsed.unit_size);
      this.correctionUpdated.emit({ feId: feSize.id, newValue: parsed.unit_size });
      this.fieldReviewed.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: 'unit_size',
        reviewedValue: parsed.unit_size,
      });
    }

    if (feUnit && !unitMatches && parsed.pack_unit) {
      this.pendingCorrections.set(feUnit.id, parsed.pack_unit);
      this.correctionUpdated.emit({ feId: feUnit.id, newValue: parsed.pack_unit });
      this.fieldReviewed.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: 'pack_unit',
        reviewedValue: parsed.pack_unit,
      });
    }

    if (fePack) {
      const packVal = {
        pack_count: parsed.pack_count,
        unit_size: parsed.unit_size,
        unit: parsed.pack_unit || line.pack?.unit || null,
      };
      this.pendingCorrections.set(fePack.id, packVal);
      this.correctionUpdated.emit({ feId: fePack.id, newValue: packVal });
      this.fieldReviewed.emit({
        entityType: 'quotation_line',
        entityId: line.id,
        fieldName: 'pack',
        reviewedValue: packVal,
      });
    }
  }

  getEffectiveDeliveryFeeAmount(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'delivery_fee');
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
    return line.delivery_fee?.amount ?? '';
  }

  getEffectiveDeliveryFeeCurrency(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'delivery_fee');
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
    return line.delivery_fee?.currency || line.unit_price?.currency || this.effectiveCurrency || 'USD';
  }

  onDeliveryFeeChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'delivery_fee');
    this.drafts.delete(key);
    this.commitDeliveryFee(line, targetValue);
  }

  onDeliveryFeeBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'delivery_fee');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) this.activeFieldKey = null;
    this.commitDeliveryFee(line, raw);
  }

  private commitDeliveryFee(line: QuotationLine, rawValue: string): void {
    const parsed = parseMoneyInput(rawValue);
    if (parsed === null) return;
    const effective = this.getEffectiveDeliveryFeeAmount(line);
    const trimmedTarget = trimDecimalZeros(parsed);
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (parsed === effective || trimmedTarget === trimmedEffective || this.isNumericEqual(parsed, effective)) {
      return;
    }

    const currency = this.getEffectiveDeliveryFeeCurrency(line);
    const newValue = { amount: parsed, currency };
    const fe = this.getFieldExtraction('quotation_line', line.id, 'delivery_fee');
    if (fe) {
      this.pendingCorrections.set(fe.id, newValue);
      this.correctionUpdated.emit({ feId: fe.id, newValue });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'delivery_fee',
      reviewedValue: newValue,
    });
  }

  getEffectiveDiscountAmount(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'discount');
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
    return line.discount?.amount ?? '';
  }

  getEffectiveDiscountCurrency(line: QuotationLine): string {
    const fe = this.getFieldExtraction('quotation_line', line.id, 'discount');
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
    return line.discount?.currency || line.unit_price?.currency || this.effectiveCurrency || 'USD';
  }

  onDiscountChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'discount');
    this.drafts.delete(key);
    this.commitDiscount(line, targetValue);
  }

  onDiscountBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'discount');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) this.activeFieldKey = null;
    this.commitDiscount(line, raw);
  }

  private commitDiscount(line: QuotationLine, rawValue: string): void {
    const parsed = parseMoneyInput(rawValue);
    if (parsed === null) return;
    const effective = this.getEffectiveDiscountAmount(line);
    const trimmedTarget = trimDecimalZeros(parsed);
    const trimmedEffective = trimDecimalZeros(effective.trim());

    if (parsed === effective || trimmedTarget === trimmedEffective || this.isNumericEqual(parsed, effective)) {
      return;
    }

    const currency = this.getEffectiveDiscountCurrency(line);
    const newValue = { amount: parsed, currency };
    const fe = this.getFieldExtraction('quotation_line', line.id, 'discount');
    if (fe) {
      this.pendingCorrections.set(fe.id, newValue);
      this.correctionUpdated.emit({ feId: fe.id, newValue });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'discount',
      reviewedValue: newValue,
    });
  }

  getEffectiveVatRate(line: QuotationLine): string {
    const val = this.getEffectiveValue('quotation_line', line.id, 'vat_rate', line.vat_rate ?? '');
    return val !== null && val !== undefined ? String(val) : '';
  }

  onVatRateChange(line: QuotationLine, targetValue: string): void {
    const key = this.fieldKey(line.id, 'vat_rate');
    this.drafts.delete(key);
    this.commitVatRate(line, targetValue);
  }

  onVatRateBlur(line: QuotationLine, targetValue?: string): void {
    const key = this.fieldKey(line.id, 'vat_rate');
    const raw = targetValue !== undefined ? targetValue : (this.drafts.get(key) ?? '');
    this.drafts.delete(key);
    if (this.activeFieldKey === key) this.activeFieldKey = null;
    this.commitVatRate(line, raw);
  }

  private commitVatRate(line: QuotationLine, rawValue: string): void {
    const parsed = parseMoneyInput(rawValue);
    if (parsed === null) return;
    const num = Number(parsed);
    if (!Number.isFinite(num) || num < 0 || num > 100) return;
    const fraction = Number((num / 100).toFixed(4)).toString();
    const effective = this.getEffectiveVatRate(line);

    if (fraction === effective || this.isNumericEqual(fraction, effective)) {
      return;
    }

    const fe = this.getFieldExtraction('quotation_line', line.id, 'vat_rate');
    if (fe) {
      this.pendingCorrections.set(fe.id, fraction);
      this.correctionUpdated.emit({ feId: fe.id, newValue: fraction });
    }
    this.fieldReviewed.emit({
      entityType: 'quotation_line',
      entityId: line.id,
      fieldName: 'vat_rate',
      reviewedValue: fraction,
    });
  }

  revertField(feId: string): void {
    this.pendingCorrections.delete(feId);
    this.correctionReverted.emit(feId);
  }
}
