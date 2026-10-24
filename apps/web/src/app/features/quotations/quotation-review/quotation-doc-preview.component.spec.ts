import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { FieldExtraction, QuotationDetail } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { QuotationDocPreviewComponent } from './quotation-doc-preview.component';

describe('QuotationDocPreviewComponent provenance', () => {
  let fixture: ComponentFixture<QuotationDocPreviewComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationDocPreviewComponent],
      providers: [provideTranslateService(), provideHttpClient(withXhr()), provideHttpClientTesting()],
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

describe('QuotationDocPreviewComponent focus guard (PPS-57)', () => {
  let fixture: ComponentFixture<QuotationDocPreviewComponent>;
  let externalInput: HTMLInputElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationDocPreviewComponent],
      providers: [provideTranslateService(), provideHttpClient(withXhr()), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(QuotationDocPreviewComponent);
    fixture.componentRef.setInput('quotation', { document: { mime_type: 'application/pdf' } } as QuotationDetail);
    const sanitizer = TestBed.inject(DomSanitizer);
    fixture.componentRef.setInput('safePreviewUrl', sanitizer.bypassSecurityTrustResourceUrl('about:blank'));
    fixture.componentRef.setInput('documentFileName', 'quote.pdf');
    fixture.componentRef.setInput('activeExtraction', null);
    fixture.componentRef.setInput('isWriter', true);
    fixture.componentRef.setInput('isReplacingDocument', false);
    fixture.detectChanges();

    document.body.appendChild(fixture.nativeElement);

    externalInput = document.createElement('input');
    externalInput.type = 'text';
    externalInput.value = '75.00';
    document.body.appendChild(externalInput);
  });

  afterEach(() => {
    externalInput.remove();
    fixture.nativeElement.remove();
  });

  it('refocuses the input and restores selection when iframe steals focus during the guard window', fakeAsync(() => {
    const iframe = fixture.nativeElement.querySelector('iframe.pdf-preview-frame') as HTMLIFrameElement;
    expect(iframe).toBeTruthy();

    // Trigger load on iframe to open 1500 ms guard window (PPS-57: real PDF loading is not needed in unit tests)
    iframe.dispatchEvent(new Event('load'));

    externalInput.focus();
    externalInput.setSelectionRange(1, 1);
    expect(document.activeElement).toBe(externalInput);
    expect(externalInput.selectionStart).toBe(1);

    // Programmatic focus on iframe simulates focus steal and triggers focusout on the active input
    iframe.focus();
    tick(0); // Macrotask scheduled in focusout handler

    expect(document.activeElement).toBe(externalInput);
    expect(externalInput.selectionStart).toBe(1);
    expect(externalInput.selectionEnd).toBe(1);

    tick(1500); // Flush the remaining guard window timer
  }));

  it('leaves focus on the iframe when focus moves after the guard window has expired (>1500 ms)', fakeAsync(() => {
    const iframe = fixture.nativeElement.querySelector('iframe.pdf-preview-frame') as HTMLIFrameElement;
    expect(iframe).toBeTruthy();

    // Trigger load on iframe (PPS-57: real PDF loading is not needed in unit tests)
    iframe.dispatchEvent(new Event('load'));
    tick(1501); // Advance time beyond the 1500ms guard window

    externalInput.focus();
    externalInput.setSelectionRange(1, 1);
    expect(document.activeElement).toBe(externalInput);

    iframe.focus();
    tick(0);

    expect(document.activeElement).toBe(iframe);
  }));

  it('leaves focus on the iframe after component destruction', fakeAsync(() => {
    const iframe = fixture.nativeElement.querySelector('iframe.pdf-preview-frame') as HTMLIFrameElement;
    expect(iframe).toBeTruthy();

    // Trigger load on iframe (PPS-57: real PDF loading is not needed in unit tests)
    iframe.dispatchEvent(new Event('load'));
    fixture.destroy();

    externalInput.focus();
    externalInput.setSelectionRange(1, 1);
    expect(document.activeElement).toBe(externalInput);

    iframe.focus();
    tick(0);

    expect(document.activeElement).toBe(iframe);
  }));

  it('sets data-preview-loaded="true" on load and clears it when safePreviewUrl changes', () => {
    const sanitizer = TestBed.inject(DomSanitizer);
    fixture.componentRef.setInput('safePreviewUrl', sanitizer.bypassSecurityTrustResourceUrl('about:blank?init'));
    fixture.detectChanges();

    let iframe = fixture.nativeElement.querySelector('iframe.pdf-preview-frame') as HTMLIFrameElement;
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute('data-preview-loaded')).toBeNull();

    // Trigger load on iframe
    iframe.dispatchEvent(new Event('load'));
    fixture.detectChanges();

    expect(iframe.getAttribute('data-preview-loaded')).toBe('true');

    // Change safePreviewUrl to simulate a new document
    fixture.componentRef.setInput('safePreviewUrl', sanitizer.bypassSecurityTrustResourceUrl('about:blank?next'));
    fixture.detectChanges();

    iframe = fixture.nativeElement.querySelector('iframe.pdf-preview-frame') as HTMLIFrameElement;
    expect(iframe.getAttribute('data-preview-loaded')).toBeNull();
  });
});
