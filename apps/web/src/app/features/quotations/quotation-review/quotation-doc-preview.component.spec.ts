import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { FieldExtraction, QuotationDetail } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { QuotationDocPreviewComponent } from './quotation-doc-preview.component';

describe('QuotationDocPreviewComponent provenance', () => {
  let fixture: ComponentFixture<QuotationDocPreviewComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationDocPreviewComponent, TranslateModule.forRoot()],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(QuotationDocPreviewComponent);
    fixture.componentRef.setInput('quotation', { document: { mime_type: 'application/pdf' } } as QuotationDetail);
    fixture.componentRef.setInput('safePreviewUrl', null);
    fixture.componentRef.setInput('documentFileName', 'quote.pdf');
    fixture.componentRef.setInput('activeExtraction', {
      id: 'field-1',
      field_name: 'supplier_name',
      extracted_value: 'الأمانة للتجارة',
      corrected_value: 'الأمانة للتجارة',
      extraction_method: 'bedrock',
      model_version: 'test-model',
      source_page: 1,
      confidence: '0.6790',
    } as FieldExtraction);
    fixture.componentRef.setInput('isWriter', true);
    fixture.componentRef.setInput('isReplacingDocument', false);
    fixture.detectChanges();
  });

  it('renders Arabic string provenance as plain auto-direction text without JSON quotes', () => {
    const values = Array.from(fixture.nativeElement.querySelectorAll('.prov-val[dir="auto"]')) as HTMLElement[];
    expect(values.length).toBe(2);
    expect(values[0].textContent?.trim()).toBe('الأمانة للتجارة');
    expect(values[0].textContent).not.toContain('"');
    expect(values[1].textContent?.trim()).toBe('الأمانة للتجارة');
  });

  it('keeps extraction internals off the screen and labels fields from the catalogue', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('ar', { quotations: { review: { fieldLabels: { supplier_name: 'اسم المورد' } } } });
    translate.use('ar');
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('application/pdf');
    expect(text).not.toContain('bedrock');
    expect(text).not.toContain('test-model');
    expect(text).not.toContain('Supplier Name');
    expect(fixture.nativeElement.querySelector('.extraction-field-label').textContent.trim()).toBe('اسم المورد');
    const icon = fixture.nativeElement.querySelector('.prov-details-icon') as HTMLElement;
    expect(icon.getAttribute('aria-label')).toContain('bedrock · test-model');
  });

  it('renders a money-shaped value in provenance original value via FormatService.formatMoney in en and ar without .mono class', () => {
    const formatService = TestBed.inject(FormatService);
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    fixture.componentRef.setInput('activeExtraction', {
      id: 'field-total',
      field_name: 'stated_total',
      extracted_value: { amount: '24220.00', currency: 'EGP' },
      corrected_value: null,
      extraction_method: 'bedrock',
      model_version: 'test-model',
      source_page: 1,
      confidence: '0.6790',
    } as FieldExtraction);
    fixture.detectChanges();

    const provVals = Array.from(fixture.nativeElement.querySelectorAll('.prov-val')) as HTMLElement[];
    const origVal = provVals[1];
    expect(origVal).toBeTruthy();
    expect(origVal.classList.contains('mono')).toBeFalse();
    expect(origVal.textContent).not.toContain('"amount"');
    expect(origVal.textContent).not.toContain('{');
    expect(origVal.textContent?.trim()).toBe(formatService.formatMoney({ amount: '24220.00', currency: 'EGP' }));

    translate.use('ar');
    fixture.detectChanges();

    expect(origVal.classList.contains('mono')).toBeFalse();
    expect(origVal.textContent).not.toContain('"amount"');
    expect(origVal.textContent).not.toContain('{');
    expect(origVal.textContent?.trim()).toBe(formatService.formatMoney({ amount: '24220.00', currency: 'EGP' }));
    expect(origVal.textContent).toContain('٢٤');
  });

  it('renders plain string provenance without reformatting and keeps raw text', () => {
    fixture.componentRef.setInput('activeExtraction', {
      id: 'field-supplier',
      field_name: 'supplier_name',
      extracted_value: 'Acme Corporation',
      corrected_value: null,
      extraction_method: 'bedrock',
      model_version: 'test-model',
      source_page: 1,
      confidence: '0.9000',
    } as FieldExtraction);
    fixture.detectChanges();

    const provVals = Array.from(fixture.nativeElement.querySelectorAll('.prov-val')) as HTMLElement[];
    const origVal = provVals[1];
    expect(origVal.textContent?.trim()).toBe('Acme Corporation');
    expect(origVal.classList.contains('mono')).toBeFalse();
  });

  it('renders an issue_date ISO date in provenance through date formatting', () => {
    const formatService = TestBed.inject(FormatService);
    const translate = TestBed.inject(TranslateService);
    translate.use('en');

    fixture.componentRef.setInput('activeExtraction', {
      id: 'field-date',
      field_name: 'issue_date',
      extracted_value: '2026-08-20',
      corrected_value: null,
      extraction_method: 'bedrock',
      model_version: 'test-model',
      source_page: 1,
      confidence: '0.9000',
    } as FieldExtraction);
    fixture.detectChanges();

    const provVals = Array.from(fixture.nativeElement.querySelectorAll('.prov-val')) as HTMLElement[];
    const origVal = provVals[1];
    expect(origVal.textContent?.trim()).not.toBe('2026-08-20');
    expect(origVal.textContent?.trim()).toBe(formatService.formatDate(new Date(2026, 7, 20)));
    expect(origVal.classList.contains('mono')).toBeFalse();
  });
});
