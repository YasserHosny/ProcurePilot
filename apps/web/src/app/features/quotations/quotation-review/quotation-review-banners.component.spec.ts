import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { provideRouter } from '@angular/router';

import type { QuotationDetail } from '../../../core/api/models';
import { QuotationReviewBannersComponent } from './quotation-review-banners.component';

describe('QuotationReviewBannersComponent', () => {
  let component: QuotationReviewBannersComponent;
  let fixture: ComponentFixture<QuotationReviewBannersComponent>;

  const mockQuotation: QuotationDetail = {
    id: 'q-1',
    document_id: 'doc-1',
    supplier_id: 'sup-1',
    currency: 'GBP',
    issue_date: '2026-08-20',
    expiry_date: null,
    status: 'extracted',
    previous_quotation_id: null,
    stated_total: { amount: '100.00', currency: 'GBP' },
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
    lines: [],
    field_extractions: [],
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationReviewBannersComponent],
      providers: [provideTranslateService(), provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(QuotationReviewBannersComponent);
    component = fixture.componentInstance;
    component.quotation = mockQuotation;
  });

  it('displays effective statedTotal when provided on mismatch banner', () => {
    component.hasArithmeticMismatch = true;
    component.statedTotal = { amount: '200.00', currency: 'GBP' };
    fixture.detectChanges();

    const bannerEl = fixture.nativeElement as HTMLElement;
    expect(bannerEl.textContent).toContain('GBP 200');
    expect(bannerEl.textContent).not.toContain('GBP 100');
  });

  it('displays effective statedTotal when provided on reconciled banner', () => {
    component.isReconciled = true;
    component.statedTotal = { amount: '200.00', currency: 'GBP' };
    fixture.detectChanges();

    const bannerEl = fixture.nativeElement as HTMLElement;
    expect(bannerEl.textContent).toContain('GBP 200');
    expect(bannerEl.textContent).not.toContain('GBP 100');
  });

  it('displays quotation stated_total as fallback when statedTotal is null', () => {
    component.hasArithmeticMismatch = true;
    component.statedTotal = null;
    fixture.detectChanges();

    const bannerEl = fixture.nativeElement as HTMLElement;
    expect(bannerEl.textContent).toContain('GBP 100');
  });
});
