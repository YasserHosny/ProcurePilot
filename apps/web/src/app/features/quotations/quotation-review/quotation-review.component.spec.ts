import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatDatepicker } from '@angular/material/datepicker';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { QuotationDetail, Role, Supplier } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { SessionService } from '../../../core/auth/session.service';
import { QuotationReviewComponent } from './quotation-review.component';

describe('QuotationReviewComponent (T051, T057, T062)', () => {
  let component: QuotationReviewComponent;
  let fixture: ComponentFixture<QuotationReviewComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  const homeCurrency = signal<string | undefined>('EGP');

  const mockQuotationDetail: QuotationDetail = {
    id: 'q-review-1',
    document_id: 'doc-1',
    supplier_id: null,
    currency: 'GBP',
    issue_date: '2026-08-20',
    expiry_date: '2026-09-20',
    status: 'extracted',
    previous_quotation_id: null,
    stated_total: { amount: '250.00', currency: 'GBP' },
    arithmetic_status: 'reconciled',
    created_at: '2026-08-20T12:00:00Z',
    document: {
      id: 'doc-1',
      storage_bucket: 'quotations',
      storage_path: 'tenant-1/doc-1.pdf',
      mime_type: 'application/pdf',
      content_hash: 'abc123hash',
      source_channel: 'upload',
      status: 'uploaded',
      created_at: '2026-08-20T12:00:00Z',
    },
    lines: [
      {
        id: 'line-1',
        line_number: 1,
        original_text: 'Fresh Whole Milk 2L',
        quantity: '10',
        pack: { pack_count: 1, unit_size: '2.0', unit: 'litre' },
        unit_price: { amount: '25.00', currency: 'GBP' },
        vat_rate: '0.20',
        delivery_fee: null,
        discount: null,
      },
    ],
    field_extractions: [
      {
        id: 'fe-supplier',
        quotation_id: 'q-review-1',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'supplier_id',
        extracted_value: null,
        confidence: '0.4000', // Low confidence -> flagged
        source_page: 1,
        source_region: { bbox: [10, 10, 100, 30] },
        extraction_method: 'bedrock',
        model_version: 'claude-3-haiku-20240307',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      },
      {
        id: 'fe-line1-price',
        quotation_id: 'q-review-1',
        entity_type: 'quotation_line',
        entity_id: 'line-1',
        field_name: 'unit_price',
        extracted_value: { amount: '25.00', currency: 'GBP' },
        confidence: '0.9800',
        source_page: 1,
        source_region: { bbox: [50, 120, 80, 20] },
        extraction_method: 'bedrock',
        model_version: 'claude-3-haiku-20240307',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      },
    ],
  };

  const mockSuppliers: Supplier[] = [
    {
      id: 'sup-1',
      name: 'Dairy Direct Ltd',
      status: 'active',
      created_at: '2026-08-01T00:00:00Z',
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'getQuotation',
      'suppliers',
      'patchQuotation',
      'confirmQuotation',
      'exportQuotation',
      'createSupplier',
      'getQuotationMatches',
      'getDocumentDownloadUrl',
      'getAuditTrail',
      'getReviewTasks',
    ]);
    apiService.getQuotation.and.returnValue(of(mockQuotationDetail));
    apiService.suppliers.and.returnValue(of({ items: mockSuppliers, next_cursor: null }));
    apiService.getQuotationMatches.and.returnValue(of({ quotation_id: 'q-review-1', lines: [] }));
    apiService.getDocumentDownloadUrl.and.returnValue(of({ download_url: 'https://storage.example.com/doc-1.pdf' }));
    apiService.getAuditTrail.and.returnValue(of({ items: [] }));
    apiService.getReviewTasks.and.returnValue(of({ items: [], next_cursor: null }));

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
      homeCurrency,
    };

    await TestBed.configureTestingModule({
      imports: [QuotationReviewComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (k: string) => (k === 'id' ? 'q-review-1' : null),
              },
            },
          },
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(QuotationReviewComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('prefers the original Unicode filename over the ASCII storage key', () => {
    component.quotation.set({
      ...mockQuotationDetail,
      document: { ...mockQuotationDetail.document, original_filename: 'عرض-سعر-النور.pdf' },
    });
    expect(component.documentFileName()).toBe('عرض-سعر-النور.pdf');
  });

  it('should load quotation details and suppliers on init', () => {
    expect(apiService.getQuotation).toHaveBeenCalledWith('q-review-1');
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(component.quotation()?.id).toBe('q-review-1');
    expect(component.suppliers().length).toBe(1);
    expect(component.flaggedFields().length).toBe(1);
  });

  it('removes low-confidence supplier_name from flagged fields after selecting a supplier', () => {
    const supplierName = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-supplier-name',
      field_name: 'supplier_name',
      extracted_value: 'الأمانة للتجارة',
      confidence: '0.6700',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [supplierName] });
    component.selectedSupplierId.set(null);
    expect(component.flaggedFields().map((field) => field.id)).toContain(supplierName.id);
    component.selectedSupplierId.set('sup-1');
    expect(component.flaggedFields().map((field) => field.id)).not.toContain(supplierName.id);
  });

  it('opens low-confidence supplier name evidence and renders its Go to field action without a supplier selected', () => {
    const supplierName = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-supplier-name',
      field_name: 'supplier_name',
      extracted_value: 'الأمانة للتجارة',
      confidence: '0.6700',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [supplierName] });
    component.selectedSupplierId.set(null);
    const flaggedSupplierName = component.flaggedFields().find((field) => field.id === supplierName.id);
    expect(flaggedSupplierName).toBeDefined();
    component.goToFlaggedField(flaggedSupplierName!);
    expect(component.activeExtraction()?.id).toBe(supplierName.id);

    fixture.detectChanges();
    const supplierRow = fixture.nativeElement.querySelector('#flagged-fe-supplier-name') as HTMLElement;
    expect(supplierRow.querySelector('button')?.textContent).toContain(
      enCatalog.quotations.review.flagged.goToField,
    );
  });

  it('stages confirm-as-is for a low-confidence unit price extraction', () => {
    const unitPrice = {
      ...mockQuotationDetail.field_extractions[1],
      confidence: '0.5000',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [unitPrice] });
    component.confirmFieldAsIs('quotation_line', 'line-1', 'unit_price');
    expect(component.pendingCorrections().get(unitPrice.id)).toEqual(unitPrice.extracted_value);
  });

  it('requests inline preview URLs and attachment URLs from the download button', () => {
    expect(apiService.getDocumentDownloadUrl).toHaveBeenCalledWith('doc-1');

    const downloadWindow = { opener: window, location: { href: '' }, close: jasmine.createSpy() };
    spyOn(window, 'open').and.returnValue(downloadWindow as unknown as Window);
    fixture.debugElement.query(By.css('.download-original-btn')).nativeElement.click();

    expect(apiService.getDocumentDownloadUrl).toHaveBeenCalledWith('doc-1', 'attachment');
  });

  it('uses the home currency for a quote total when the quote and its lines omit currency', () => {
    component.quotation.set({
      ...mockQuotationDetail,
      currency: null,
      lines: [{ ...mockQuotationDetail.lines[0], unit_price: { amount: '25.00', currency: null } }],
    } as unknown as QuotationDetail);

    expect(component.computedLinesTotal()?.currency).toBe('EGP');
  });

  it('uses a staged currency for totals and newly added priced lines when the quote has no currency', () => {
    component.quotation.set({
      ...mockQuotationDetail,
      currency: null,
      stated_total: null,
      lines: [],
    } as unknown as QuotationDetail);
    component.currencySelectionChanged('EUR');
    component.newLineText.set('New item');
    component.newLinePriceAmount.set('12.50');

    component.addNewLine();

    expect(component.pendingNewLines()[0].unit_price_currency).toBe('EUR');
    expect(component.computedLinesTotal()?.currency).toBe('EUR');
  });

  it('uses the home currency when adding a priced line to a quote without currency', () => {
    component.quotation.set({ ...mockQuotationDetail, currency: null, lines: [] } as unknown as QuotationDetail);
    component.newLineText.set('New item');
    component.newLinePriceAmount.set('12.50');

    component.addNewLine();

    expect(component.pendingNewLines()[0].unit_price_currency).toBe('EGP');
  });

  it('saves an explicitly selected currency when no currency extraction row exists', () => {
    const missingCurrency = { ...mockQuotationDetail, currency: null, supplier_id: 'sup-1', field_extractions: [] };
    component.quotation.set(missingCurrency as unknown as QuotationDetail);
    component.selectedSupplierId.set('sup-1');
    apiService.patchQuotation.and.returnValue(of({ ...missingCurrency, currency: 'EGP' } as QuotationDetail));
    apiService.confirmQuotation.and.returnValue(of({ ...missingCurrency, currency: 'EGP', status: 'reviewed' } as QuotationDetail));

    component.currencySelectionChanged('EGP');
    component.confirmQuotation();

    expect(apiService.patchQuotation).toHaveBeenCalledWith('q-review-1', jasmine.objectContaining({ currency: 'EGP' }));
    expect(apiService.confirmQuotation).toHaveBeenCalled();
  });

  it('keeps a quote currency when adding a priced line', () => {
    component.newLineText.set('New item');
    component.newLinePriceAmount.set('12.50');

    component.addNewLine();

    expect(component.pendingNewLines()[0].unit_price_currency).toBe('GBP');
  });

  it('should offer to create an extracted supplier even when other suppliers exist', () => {
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: [
        ...mockQuotationDetail.field_extractions,
        {
          ...mockQuotationDetail.field_extractions[0],
          id: 'fe-supplier-name',
          field_name: 'supplier_name',
          extracted_value: 'New Vendor Ltd',
          confidence: '0.9200',
        },
      ],
    });
    component.selectedSupplierId.set(null);
    fixture.detectChanges();

    const createButton = fixture.debugElement.query(By.css('.supplier-match-missing button'));

    expect(createButton).not.toBeNull();
    expect(createButton.nativeElement.textContent).toContain('Create supplier');
  });

  it('should show a manual add supplier link while the supplier field is editable', () => {
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: mockQuotationDetail.field_extractions.filter((fe) => fe.field_name !== 'supplier_name'),
    });
    component.selectedSupplierId.set(null);
    fixture.detectChanges();

    const addSupplierLink = fixture.debugElement.query(By.css('.supplier-manual-add-link'));

    expect(addSupplierLink).not.toBeNull();
    expect(addSupplierLink.nativeElement.textContent).toContain('Add a supplier');
    expect(addSupplierLink.nativeElement.getAttribute('href')).toBe('/suppliers/new');
  });

  it('should render the add-line cancel action with translated text', () => {
    component.showAddLineForm();
    fixture.detectChanges();

    const addLineForm = fixture.debugElement.query(By.css('.add-line-form'));

    expect(addLineForm).not.toBeNull();
    expect(addLineForm.nativeElement.textContent).toContain('Cancel');
    expect(addLineForm.nativeElement.textContent).not.toContain('common.cancel');
  });

  it('should navigate through flagged fields with keyboard navigation (FR-014)', () => {
    expect(component.flaggedFields().length).toBeGreaterThan(0);
    const initialIndex = component.currentFlaggedIndex();

    component.nextFlaggedField();
    expect(component.currentFlaggedIndex()).toBe((initialIndex + 1) % component.flaggedFields().length);

    component.prevFlaggedField();
    expect(component.currentFlaggedIndex()).toBe(initialIndex);
  });

  it('should record correction and submit PATCH /quotations/{id}', () => {
    const updatedQuotation = {
      ...mockQuotationDetail,
      field_extractions: [
        {
          ...mockQuotationDetail.field_extractions[1],
          corrected_value: { amount: '26.50', currency: 'GBP' },
        },
      ],
    };
    apiService.patchQuotation.and.returnValue(of(updatedQuotation));

    component.updateCorrection('fe-line1-price', { amount: '26.50', currency: 'GBP' });
    expect(component.pendingCorrections().size).toBe(1);

    component.saveCorrections();

    expect(apiService.patchQuotation).toHaveBeenCalledWith('q-review-1', {
      supplier_id: null,
      reviewer_notes: null,
      corrections: [
        {
          field_extraction_id: 'fe-line1-price',
          corrected_value: { amount: '26.50', currency: 'GBP' },
        },
      ],
      add_lines: [],
      remove_line_ids: [],
    });
    expect(component.pendingCorrections().size).toBe(0);
  });

  it('should refresh the audit trail after saving review changes', () => {
    const updatedQuotation = {
      ...mockQuotationDetail,
      field_extractions: [
        {
          ...mockQuotationDetail.field_extractions[1],
          corrected_value: { amount: '26.50', currency: 'GBP' },
        },
      ],
    };
    apiService.patchQuotation.and.returnValue(of(updatedQuotation));
    apiService.getAuditTrail.calls.reset();

    component.updateCorrection('fe-line1-price', { amount: '26.50', currency: 'GBP' });
    component.saveCorrections();

    expect(apiService.getAuditTrail).toHaveBeenCalledOnceWith('q-review-1');
  });

  it('should refresh the audit trail after exporting quotation data', () => {
    apiService.exportQuotation.and.returnValue(of(new Blob(['csv'], { type: 'text/csv' })));
    spyOn(window.URL, 'createObjectURL').and.returnValue('blob:quotation-export');
    spyOn(window.URL, 'revokeObjectURL');
    apiService.getAuditTrail.calls.reset();

    component.exportQuotation();

    expect(apiService.getAuditTrail).toHaveBeenCalledOnceWith('q-review-1');
  });

  it('should treat reviewing a low-confidence field without changing its value as a pending correction', () => {
    const lowConfidenceExpiry = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-expiry',
      field_name: 'expiry_date',
      extracted_value: '2026-09-20',
      confidence: '0.5400',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: [lowConfidenceExpiry, mockQuotationDetail.field_extractions[1]],
    });

    component.reviewFieldValue('quotation', 'q-review-1', 'expiry_date', '2026-09-20');

    expect(component.pendingCorrections().get('fe-expiry')).toBe('2026-09-20');
    expect(component.hasPendingReviewChanges()).toBeTrue();
  });

  it('parses only ISO dates as local calendar dates and keeps non-ISO evidence visible', () => {
    const parsed = component.toDate('2026-10-16');
    expect(parsed?.getFullYear()).toBe(2026);
    expect(parsed?.getMonth()).toBe(9);
    expect(parsed?.getDate()).toBe(16);
    expect(component.toDate('05/10/2026')).toBeNull();
    expect(component.isRawDateEvidence('16 Octobre 2026')).toBeTrue();
    const rawIssueDate = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-raw-issue-date',
      field_name: 'issue_date',
      extracted_value: '16 Octobre 2026',
      confidence: '0.0000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      issue_date: null,
      field_extractions: [rawIssueDate, ...mockQuotationDetail.field_extractions.slice(1)],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Text in document: 16 Octobre 2026');
    expect(fixture.nativeElement.textContent).not.toContain('Text in document: true');
  });

  it('does not submit a raw non-ISO date as a reviewed correction', () => {
    const rawDate = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-raw-date',
      field_name: 'issue_date',
      extracted_value: '16 Octobre 2026',
      confidence: '0.0000',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [rawDate] });
    component.reviewFieldValue('quotation', 'q-review-1', 'issue_date', '16 Octobre 2026');
    expect(component.pendingCorrections().has('fe-raw-date')).toBeFalse();
  });

  it('confirms a date using the canonical quotation value while preserving raw evidence', () => {
    const rawDate = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-raw-confirm-date',
      field_name: 'issue_date',
      extracted_value: '05/10/2026',
      confidence: '0.5000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      issue_date: '2026-10-05',
      field_extractions: [rawDate],
    });

    component.confirmFieldAsIs('quotation', 'q-review-1', 'issue_date');

    expect(component.pendingCorrections().get(rawDate.id)).toBe('2026-10-05');
    expect(component.dateEvidence('q-review-1', 'issue_date', '2026-10-05')).toBe('05/10/2026');
  });

  it('does not stage confirm-as-is when the canonical date is missing', () => {
    const rawDate = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-unparsed-confirm-date',
      field_name: 'issue_date',
      extracted_value: 'soon',
      confidence: '0.0000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      issue_date: null,
      field_extractions: [rawDate],
    });
    fixture.detectChanges();

    component.confirmFieldAsIs('quotation', 'q-review-1', 'issue_date');

    expect(component.pendingCorrections().has(rawDate.id)).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('Choose a date to confirm this value.');
  });

  it('should stage an unchanged low-confidence expiry date when the datepicker closes', () => {
    const lowConfidenceExpiry = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-expiry',
      field_name: 'expiry_date',
      extracted_value: '2026-09-20',
      confidence: '0.5400',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: [lowConfidenceExpiry, mockQuotationDetail.field_extractions[1]],
    });
    fixture.detectChanges();

    const datepickers = fixture.debugElement.queryAll(By.directive(MatDatepicker));
    expect(datepickers.length).toBeGreaterThanOrEqual(2);

    const expiryDatepicker = datepickers[1].componentInstance as MatDatepicker<Date>;
    expiryDatepicker.closedStream.emit();

    expect(component.pendingCorrections().get('fe-expiry')).toBe('2026-09-20');
    expect(component.hasPendingReviewChanges()).toBeTrue();
  });

  it('should stage an unchanged low-confidence expiry date when the datepicker toggle is opened', () => {
    const lowConfidenceExpiry = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-expiry',
      field_name: 'expiry_date',
      extracted_value: '2026-09-20',
      confidence: '0.5400',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: [lowConfidenceExpiry, mockQuotationDetail.field_extractions[1]],
    });
    fixture.detectChanges();

    const datepickerToggles = fixture.debugElement.queryAll(By.css('mat-datepicker-toggle'));
    expect(datepickerToggles.length).toBeGreaterThanOrEqual(2);

    datepickerToggles[1].triggerEventHandler('click', {
      stopPropagation: () => undefined,
    });

    expect(component.pendingCorrections().get('fe-expiry')).toBe('2026-09-20');
    expect(component.hasPendingReviewChanges()).toBeTrue();
  });

  it('should confirm quotation with selected supplier and previous quotation id', () => {
    const confirmedQuotation = {
      ...mockQuotationDetail,
      status: 'reviewed' as const,
      supplier_id: 'sup-1',
    };
    // Selecting a supplier with no other field correction still needs saving before confirm —
    // the backend only sees supplier_id once this PATCH lands (regression guard: a supplier-only
    // change must not be silently skipped just because pendingCorrections is empty).
    apiService.patchQuotation.and.returnValue(of({ ...mockQuotationDetail, supplier_id: 'sup-1' }));
    apiService.confirmQuotation.and.returnValue(of(confirmedQuotation));

    component.selectedSupplierId.set('sup-1');
    component.isRequote.set(true);
    component.selectedPreviousQuotationId.set('q-prior-99');

    component.confirmQuotation();

    expect(apiService.patchQuotation).toHaveBeenCalledWith('q-review-1', {
      supplier_id: 'sup-1',
      reviewer_notes: null,
      corrections: [],
      add_lines: [],
      remove_line_ids: [],
    });
    expect(apiService.confirmQuotation).toHaveBeenCalledWith('q-review-1', {
      previous_quotation_id: 'q-prior-99',
      acknowledge_mismatch: undefined,
    });
  });

  it('should save staged line changes before confirming', () => {
    const confirmedQuotation = {
      ...mockQuotationDetail,
      status: 'reviewed' as const,
      supplier_id: 'sup-1',
    };
    apiService.patchQuotation.and.returnValue(of({ ...mockQuotationDetail, supplier_id: 'sup-1' }));
    apiService.confirmQuotation.and.returnValue(of(confirmedQuotation));

    component.selectedSupplierId.set('sup-1');
    component.pendingNewLines.set([
      {
        original_text: 'A4 paper',
        quantity: '3',
        unit_price_amount: '12.50',
        unit_price_currency: 'GBP',
      },
    ]);
    component.pendingRemoveLineIds.set(new Set(['line-1']));

    component.confirmQuotation();

    expect(apiService.patchQuotation).toHaveBeenCalledWith('q-review-1', {
      supplier_id: 'sup-1',
      reviewer_notes: null,
      corrections: [],
      add_lines: [
        {
          original_text: 'A4 paper',
          quantity: '3',
          unit_price_amount: '12.50',
          unit_price_currency: 'GBP',
        },
      ],
      remove_line_ids: ['line-1'],
    });
    expect(component.pendingNewLines()).toEqual([]);
    expect(component.pendingRemoveLineIds().size).toBe(0);
    expect(apiService.confirmQuotation).toHaveBeenCalled();
  });

  it('should confirm directly without a patch when the supplier was already saved', () => {
    const alreadyConfirmedSupplier = { ...mockQuotationDetail, supplier_id: 'sup-1' };
    component.quotation.set(alreadyConfirmedSupplier);
    const confirmedQuotation = { ...alreadyConfirmedSupplier, status: 'reviewed' as const };
    apiService.confirmQuotation.and.returnValue(of(confirmedQuotation));

    component.selectedSupplierId.set('sup-1');

    component.confirmQuotation();

    expect(apiService.patchQuotation).not.toHaveBeenCalled();
    expect(apiService.confirmQuotation).toHaveBeenCalledWith('q-review-1', {
      previous_quotation_id: null,
      acknowledge_mismatch: undefined,
    });
  });

  it('shows the localized reason for a confirm 409 instead of the envelope message', () => {
    const alreadyMatched = { ...mockQuotationDetail, supplier_id: 'sup-1' };
    component.quotation.set(alreadyMatched);
    component.selectedSupplierId.set('sup-1');
    apiService.confirmQuotation.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 409,
      error: { message: 'Request conflicts with the current state.', details: { reason: 'currency_unresolved' } },
    })));

    component.confirmQuotation();

    expect(component.confirmBlockedReason()).toBe('Set the quotation currency before confirming.');
    expect(component.confirmBlockedReason()).not.toBe('Request conflicts with the current state.');
  });

  it('falls back to the unknown confirm conflict translation for unrecognized reasons', () => {
    const alreadyMatched = { ...mockQuotationDetail, supplier_id: 'sup-1' };
    component.quotation.set(alreadyMatched);
    component.selectedSupplierId.set('sup-1');
    apiService.confirmQuotation.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 409,
      error: { message: 'Request conflicts with the current state.', details: { reason: 'something_new' } },
    })));

    component.confirmQuotation();
    fixture.detectChanges();

    const shown = component.confirmBlockedReason() ?? '';
    expect(shown).toBe(enCatalog.quotations.review.confirmBlocked.unknown);
    expect(shown.startsWith('quotations.')).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain(enCatalog.quotations.review.confirmBlocked.unknown);
  });

  it('falls back to the unknown PATCH conflict translation for unrecognized reasons', () => {
    component.quotation.set(mockQuotationDetail);
    apiService.patchQuotation.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 409,
      error: { message: 'Request conflicts with the current state.', details: { reason: 'something_new' } },
    })));
    component.saveCorrections();

    fixture.detectChanges();
    const shown = component.errorMessage();
    expect(shown).toBe(enCatalog.quotations.review.conflict.unknown);
    expect(shown?.startsWith('quotations.')).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain(enCatalog.quotations.review.conflict.unknown);
  });

  it('treats prototype property names as unknown conflict reasons', () => {
    const alreadyMatched = { ...mockQuotationDetail, supplier_id: 'sup-1' };
    component.quotation.set(alreadyMatched);
    component.selectedSupplierId.set('sup-1');
    apiService.confirmQuotation.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 409,
      error: { message: 'Request conflicts with the current state.', details: { reason: 'toString' } },
    })));

    component.confirmQuotation();

    expect(component.confirmBlockedReason()).toBe(enCatalog.quotations.review.confirmBlocked.unknown);
  });

  it('should display arithmetic mismatch banner and block confirmation when totals mismatch (US3)', () => {
    const mismatchedDetail: QuotationDetail = {
      ...mockQuotationDetail,
      stated_total: { amount: '999.00', currency: 'GBP' },
      arithmetic_status: 'mismatch',
    };
    component.quotation.set(mismatchedDetail);
    fixture.detectChanges();

    expect(component.hasArithmeticMismatch()).toBeTrue();
  });

  it('renders a flagged stated_total through FormatService.formatMoney in English and Arabic without raw JSON', () => {
    const formatService = TestBed.inject(FormatService);
    const translate = TestBed.inject(TranslateService);
    const statedTotal = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-stated-total',
      field_name: 'stated_total',
      extracted_value: { amount: '24220.00', currency: 'EGP' },
      confidence: '0.5000',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [statedTotal] });
    fixture.detectChanges();

    const valueElEn = fixture.nativeElement.querySelector('#flagged-fe-stated-total .flagged-value') as HTMLElement;
    expect(valueElEn).toBeTruthy();
    expect(valueElEn.textContent).not.toContain('"amount"');
    expect(valueElEn.textContent).not.toContain('{');
    expect(valueElEn.textContent?.trim()).toBe(formatService.formatMoney({ amount: '24220.00', currency: 'EGP' }));

    translate.use('ar');
    fixture.detectChanges();

    const valueElAr = fixture.nativeElement.querySelector('#flagged-fe-stated-total .flagged-value') as HTMLElement;
    expect(valueElAr).toBeTruthy();
    expect(valueElAr.textContent).not.toContain('"amount"');
    expect(valueElAr.textContent).not.toContain('{');
    expect(valueElAr.textContent?.trim()).toBe(formatService.formatMoney({ amount: '24220.00', currency: 'EGP' }));
    expect(valueElAr.textContent).toContain('٢٤');
  });

  it('renders a flagged plain string field as raw text without reformatting', () => {
    const plainStringField = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-supplier-name',
      field_name: 'supplier_name',
      extracted_value: 'الأمانة للتجارة',
      confidence: '0.6700',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [plainStringField] });
    component.selectedSupplierId.set(null);
    fixture.detectChanges();

    const valueEl = fixture.nativeElement.querySelector('#flagged-fe-supplier-name .flagged-value') as HTMLElement;
    expect(valueEl).toBeTruthy();
    expect(valueEl.textContent?.trim()).toBe('الأمانة للتجارة');
  });

  it('renders a flagged issue_date ISO date through date formatting instead of raw string', () => {
    const formatService = TestBed.inject(FormatService);
    const dateField = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-issue-date',
      field_name: 'issue_date',
      extracted_value: '2026-08-20',
      confidence: '0.5000',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [dateField] });
    fixture.detectChanges();

    const valueEl = fixture.nativeElement.querySelector('#flagged-fe-issue-date .flagged-value') as HTMLElement;
    expect(valueEl).toBeTruthy();
    expect(valueEl.textContent?.trim()).not.toBe('2026-08-20');
    expect(valueEl.textContent?.trim()).toBe(formatService.formatDate(new Date(2026, 7, 20)));
  });
});
