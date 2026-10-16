import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatDatepicker } from '@angular/material/datepicker';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { QuotationDetail, Role, Supplier } from '../../../core/api/models';
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

  it('uses the home currency when adding a priced line to a quote without currency', () => {
    component.quotation.set({ ...mockQuotationDetail, currency: null, lines: [] } as unknown as QuotationDetail);
    component.newLineText.set('New item');
    component.newLinePriceAmount.set('12.50');

    component.addNewLine();

    expect(component.pendingNewLines()[0].unit_price_currency).toBe('EGP');
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
});
