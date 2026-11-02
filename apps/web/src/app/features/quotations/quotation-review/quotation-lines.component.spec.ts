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
});
