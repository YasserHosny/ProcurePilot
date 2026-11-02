import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import { FormatService } from '../../../core/format/format.service';
import type { QuotationDetail, QuotationLine } from '../../../core/api/models';
import { QuotationLinesComponent } from './quotation-lines.component';

describe('QuotationLinesComponent', () => {
  let component: QuotationLinesComponent;
  let fixture: ComponentFixture<QuotationLinesComponent>;

  const mockLine: QuotationLine = {
    id: 'line-1',
    line_number: 1,
    original_text: 'Test item',
    quantity: '2',
    pack: null,
    unit_price: { amount: '10.00', currency: 'GBP' },
    vat_rate: '0.15',
    delivery_fee: null,
    discount: null,
  };

  const mockQuotation: QuotationDetail = {
    id: 'q-1',
    document_id: 'doc-1',
    supplier_id: 'sup-1',
    currency: 'GBP',
    issue_date: '2026-08-20',
    expiry_date: null,
    status: 'extracted',
    previous_quotation_id: null,
    stated_total: { amount: '20.00', currency: 'GBP' },
    arithmetic_status: 'reconciled',
    prices_include_vat: false,
    vat_rate: null,
    created_at: '2026-08-20T12:00:00Z',
    document: {
      id: 'doc-1',
      storage_bucket: 'quotations',
      storage_path: 'tenant-1/doc-1.pdf',
      mime_type: 'application/pdf',
      content_hash: 'abc',
      source_channel: 'upload',
      status: 'uploaded',
      created_at: '2026-08-20T12:00:00Z',
    },
    lines: [mockLine],
    field_extractions: [],
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationLinesComponent],
      providers: [provideTranslateService(), FormatService],
    }).compileComponents();

    fixture = TestBed.createComponent(QuotationLinesComponent);
    component = fixture.componentInstance;
    component.quotation = mockQuotation;
    component.lineTotals = { 'line-1': '23.00' };
  });

  it('renders line total from lineTotals input', () => {
    fixture.detectChanges();
    expect(component.lineTotals['line-1']).toBe('23.00');
    expect(component.formatLineTotalDisplay(mockLine)).toBe('23');
  });

  it('formatUnitPrice parses Arabic and formatted numbers correctly', () => {
    expect(component.formatUnitPrice('٣٠٠')).toBe('300');
    expect(component.formatUnitPrice('1.234,56')).toBe('1234.56');
    expect(component.formatUnitPrice('12.50')).toBe('12.50');
    expect(component.formatUnitPrice('')).toBe('0');
    expect(component.formatUnitPrice(null)).toBe('0');
  });

  it('formatLineTotalDisplay returns dash when line total is absent or invalid', () => {
    component.lineTotals = {};
    expect(component.formatLineTotalDisplay(mockLine)).toBe('—');
  });

  it('onUnitPriceChange parses localized text to canonical and emits correctionUpdated', () => {
    component.quotation = {
      ...mockQuotation,
      field_extractions: [
        {
          id: 'fe-price-1',
          quotation_id: 'q-1',
          entity_type: 'quotation_line',
          entity_id: 'line-1',
          field_name: 'unit_price',
          extracted_value: { amount: '10.00', currency: 'GBP' },
          confidence: '0.90',
          extraction_method: 'structured_parse',
          model_version: 'v1',
          corrected_value: null,
          corrected_by: null,
          corrected_at: null,
        },
      ],
    };
    spyOn(component.correctionUpdated, 'emit');

    component.onUnitPriceChange(mockLine, '1,234.50');
    expect(component.correctionUpdated.emit).toHaveBeenCalledWith({
      feId: 'fe-price-1',
      newValue: { amount: '1234.50', currency: 'GBP' },
    });

    // Unparseable input emits nothing
    (component.correctionUpdated.emit as jasmine.Spy).calls.reset();
    component.onUnitPriceChange(mockLine, 'abc');
    expect(component.correctionUpdated.emit).not.toHaveBeenCalled();
  });

  it('onQuantityChange parses Arabic digits to canonical and emits correctionUpdated', () => {
    component.quotation = {
      ...mockQuotation,
      field_extractions: [
        {
          id: 'fe-qty-1',
          quotation_id: 'q-1',
          entity_type: 'quotation_line',
          entity_id: 'line-1',
          field_name: 'quantity',
          extracted_value: '2',
          confidence: '0.90',
          extraction_method: 'structured_parse',
          model_version: 'v1',
          corrected_value: null,
          corrected_by: null,
          corrected_at: null,
        },
      ],
    };
    spyOn(component.correctionUpdated, 'emit');

    component.onQuantityChange(mockLine, '١٢٫٥');
    expect(component.correctionUpdated.emit).toHaveBeenCalledWith({
      feId: 'fe-qty-1',
      newValue: '12.5',
    });

    (component.correctionUpdated.emit as jasmine.Spy).calls.reset();
    component.onQuantityChange(mockLine, 'abc');
    expect(component.correctionUpdated.emit).not.toHaveBeenCalled();
  });

  describe('Input draft isolation and character-by-character editing', () => {
    beforeEach(() => {
      component.isWriter = true;
      component.quotation = {
        ...mockQuotation,
        field_extractions: [
          {
            id: 'fe-qty-1',
            quotation_id: 'q-1',
            entity_type: 'quotation_line',
            entity_id: 'line-1',
            field_name: 'quantity',
            extracted_value: '2',
            confidence: '0.90',
            extraction_method: 'structured_parse',
            model_version: 'v1',
            corrected_value: null,
            corrected_by: null,
            corrected_at: null,
          },
          {
            id: 'fe-price-1',
            quotation_id: 'q-1',
            entity_type: 'quotation_line',
            entity_id: 'line-1',
            field_name: 'unit_price',
            extracted_value: { amount: '10.00', currency: 'GBP' },
            confidence: '0.90',
            extraction_method: 'structured_parse',
            model_version: 'v1',
            corrected_value: null,
            corrected_by: null,
            corrected_at: null,
          },
        ],
      };
      component.pendingCorrections = new Map<string, unknown>();
      component.correctionUpdated.subscribe(({ feId, newValue }) => {
        component.pendingCorrections.set(feId, newValue);
      });
      fixture.detectChanges();
    });

    it('types "1,500" one character at a time into quantity input without rewriting and stages "1500" on blur/change', () => {
      const qtyInput = fixture.nativeElement.querySelector('#field-fe-qty-1 input') as HTMLInputElement;
      expect(qtyInput).toBeTruthy();
      expect(qtyInput.value).toBe('2');

      const text = '1,500';
      for (let i = 1; i <= text.length; i++) {
        const prefix = text.slice(0, i);
        qtyInput.value = prefix;
        qtyInput.dispatchEvent(new Event('input'));
        fixture.detectChanges();
        expect(qtyInput.value).toBe(prefix);
      }

      qtyInput.dispatchEvent(new Event('blur'));
      qtyInput.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(component.pendingCorrections.get('fe-qty-1')).toBe('1500');
      expect(qtyInput.value).toBe('1500');
    });

    it('types "2,750" one character at a time into unit price input without rewriting and stages amount "2750" on blur/change', () => {
      const priceInput = fixture.nativeElement.querySelector('#field-fe-price-1 input') as HTMLInputElement;
      expect(priceInput).toBeTruthy();

      const text = '2,750';
      for (let i = 1; i <= text.length; i++) {
        const prefix = text.slice(0, i);
        priceInput.value = prefix;
        priceInput.dispatchEvent(new Event('input'));
        fixture.detectChanges();
        expect(priceInput.value).toBe(prefix);
      }

      priceInput.dispatchEvent(new Event('blur'));
      priceInput.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(component.pendingCorrections.get('fe-price-1')).toEqual({
        amount: '2750',
        currency: 'GBP',
      });
      expect(priceInput.value).toBe('2750');
    });

    it('types "1.234,56" char by char into unit price and stages "1234.56"', () => {
      const priceInput = fixture.nativeElement.querySelector('#field-fe-price-1 input') as HTMLInputElement;
      expect(priceInput).toBeTruthy();

      const text = '1.234,56';
      for (let i = 1; i <= text.length; i++) {
        const prefix = text.slice(0, i);
        priceInput.value = prefix;
        priceInput.dispatchEvent(new Event('input'));
        fixture.detectChanges();
        expect(priceInput.value).toBe(prefix);
      }

      priceInput.dispatchEvent(new Event('blur'));
      priceInput.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(component.pendingCorrections.get('fe-price-1')).toEqual({
        amount: '1234.56',
        currency: 'GBP',
      });
      expect(priceInput.value).toBe('1234.56');
    });

    it('typing "abc" stages nothing and blur restores the previous value', () => {
      const qtyInput = fixture.nativeElement.querySelector('#field-fe-qty-1 input') as HTMLInputElement;
      expect(qtyInput.value).toBe('2');

      qtyInput.value = 'abc';
      qtyInput.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      expect(qtyInput.value).toBe('abc');

      qtyInput.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections.has('fe-qty-1')).toBeFalse();
      expect(qtyInput.value).toBe('2');
    });

    it('a Money-like unit price keeps its currency', () => {
      component.pendingCorrections = new Map<string, unknown>([
        ['fe-price-1', { amount: '50.00', currency: 'SAR' }],
      ]);
      fixture.detectChanges();

      const priceInput = fixture.nativeElement.querySelector('#field-fe-price-1 input') as HTMLInputElement;
      expect(priceInput.value).toBe('50');

      priceInput.value = '75';
      priceInput.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      expect(priceInput.value).toBe('75');

      priceInput.dispatchEvent(new Event('blur'));
      priceInput.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(component.pendingCorrections.get('fe-price-1')).toEqual({
        amount: '75',
        currency: 'SAR',
      });
    });
  });
});
