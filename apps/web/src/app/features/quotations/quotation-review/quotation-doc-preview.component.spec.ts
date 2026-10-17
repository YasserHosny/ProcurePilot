import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TranslateModule } from '@ngx-translate/core';

import type { FieldExtraction, QuotationDetail } from '../../../core/api/models';
import { QuotationDocPreviewComponent } from './quotation-doc-preview.component';

describe('QuotationDocPreviewComponent provenance', () => {
  let fixture: ComponentFixture<QuotationDocPreviewComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationDocPreviewComponent, TranslateModule.forRoot()],
      providers: [provideHttpClient(), provideHttpClientTesting()],
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
});
