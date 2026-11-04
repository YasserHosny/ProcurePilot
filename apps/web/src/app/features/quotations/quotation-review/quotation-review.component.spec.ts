import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatDatepicker } from '@angular/material/datepicker';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { ActivatedRoute, ParamMap, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Subject, of, throwError, timer } from 'rxjs';
import { finalize, map } from 'rxjs/operators';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { ApiError, AuditTrailEntry, FieldExtraction, Money, Quotation, QuotationDetail, ReviewTask, Role, Supplier } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { SessionService } from '../../../core/auth/session.service';
import { QuotationReviewComponent } from './quotation-review.component';

describe('QuotationReviewComponent (T051, T057, T062)', () => {
  let component: QuotationReviewComponent;
  let fixture: ComponentFixture<QuotationReviewComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let paramMapSubject: BehaviorSubject<ParamMap>;
  let queryParamMapSubject: BehaviorSubject<ParamMap>;
  const homeCurrency = signal<string | undefined>('EGP');

  const mockQuotationDetail: QuotationDetail = {
    prices_include_vat: false,
    vat_rate: null,
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
      'presignDocument',
      'uploadFileToStorage',
      'replaceDocument',
      'refuseQuotation',
      'archiveQuotation',
      'retryExtraction',
    ]);
    apiService.getQuotation.and.returnValue(of(mockQuotationDetail));
    apiService.suppliers.and.returnValue(of({ items: mockSuppliers, next_cursor: null }));
    apiService.refuseQuotation.and.returnValue(of(mockQuotationDetail));
    apiService.archiveQuotation.and.returnValue(of(mockQuotationDetail));
    apiService.retryExtraction.and.returnValue(of(mockQuotationDetail));
    apiService.getQuotationMatches.and.returnValue(of({ quotation_id: 'q-review-1', lines: [] }));
    apiService.getDocumentDownloadUrl.and.returnValue(of({ download_url: 'https://storage.example.com/doc-1.pdf' }));
    apiService.getAuditTrail.and.returnValue(of({ items: [] }));
    apiService.getReviewTasks.and.returnValue(of({ items: [], next_cursor: null }));
    apiService.presignDocument.and.returnValue(
      of({
        document_id: 'doc-2',
        storage_bucket: 'quotations',
        storage_path: 'quotes/doc-2.pdf',
        upload_url: 'https://storage.example.com/upload',
        upload_fields: {},
        expires_at: '2026-10-30T13:00:00Z',
      }),
    );

    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    paramMapSubject = new BehaviorSubject<ParamMap>(convertToParamMap({ id: 'q-review-1' }));
    queryParamMapSubject = new BehaviorSubject<ParamMap>(convertToParamMap({}));

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
      imports: [QuotationReviewComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: MatDialog, useValue: dialogSpy },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: paramMapSubject.asObservable(),
            queryParamMap: queryParamMapSubject.asObservable(),
            snapshot: {
              get paramMap() {
                return paramMapSubject.value;
              },
              get queryParamMap() {
                return queryParamMapSubject.value;
              },
            },
          },
        },
      ],
    })
      .overrideComponent(QuotationReviewComponent, {
        add: {
          providers: [{ provide: MatDialog, useValue: dialogSpy }],
        },
      })
      .compileComponents();

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
    component.newLineQuantity.set('1');
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
    apiService.patchQuotation.and.returnValue(of({ ...mockQuotationDetail, supplier_id: 'sup-1' }));
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

  it('reconciles a VAT-inclusive quote whose lines carry the rate inside the price (ADR-021)', () => {
    // 10 × 25.00 at 20% VAT already inside the price: the printed total is 250.00, not 300.00.
    const inclusive: QuotationDetail = {
      ...mockQuotationDetail,
      prices_include_vat: true,
      vat_rate: '0.20',
      stated_total: { amount: '250.00', currency: 'GBP' },
    };
    component.quotation.set(inclusive);
    fixture.detectChanges();

    expect(component.computeLineTotal(inclusive.lines[0])).toBe('250.00');
    expect(component.hasArithmeticMismatch()).toBeFalse();
  });

  it('does not infer document VAT on a VAT-inclusive quote, as the server does not (ADR-021)', () => {
    // No line rate, stated 287.50 = 250.00 × 1.15: on an inclusive quote the gap is a mismatch.
    const inclusive: QuotationDetail = {
      ...mockQuotationDetail,
      prices_include_vat: true,
      vat_rate: null,
      stated_total: { amount: '287.50', currency: 'GBP' },
      lines: [{ ...mockQuotationDetail.lines[0], vat_rate: null }],
    };
    component.quotation.set(inclusive);
    fixture.detectChanges();

    expect(component.hasArithmeticMismatch()).toBeTrue();
    expect(component.inferredVatPct()).toBeNull();
  });

  it('shows the stored VAT basis after a second change, not the first correction (ADR-021)', () => {
    // The header field keeps its first correction (true / 15%); the quote now says false / 5%.
    const corrected = (field: string, value: unknown) => ({
      ...mockQuotationDetail.field_extractions[0],
      id: `fe-${field}`,
      field_name: field,
      extracted_value: field === 'vat_rate' ? '0.10' : false,
      confidence: '0.8000',
      corrected_value: value,
      corrected_by: 'member-1',
    });
    const q: QuotationDetail = {
      ...mockQuotationDetail,
      prices_include_vat: false,
      vat_rate: '0.0500',
      field_extractions: [
        ...mockQuotationDetail.field_extractions,
        corrected('prices_include_vat', true),
        corrected('vat_rate', '0.15'),
      ],
    };
    component.quotation.set(q);
    fixture.detectChanges();

    expect(component.effectivePricesIncludeVat(q)).toBeFalse();
    expect(component.effectiveVatRate(q)).toBe('0.0500');
  });

  it('still adds VAT on top when the same lines are VAT-exclusive', () => {
    const exclusive: QuotationDetail = {
      ...mockQuotationDetail,
      prices_include_vat: false,
      stated_total: { amount: '250.00', currency: 'GBP' },
    };
    component.quotation.set(exclusive);
    fixture.detectChanges();

    expect(component.computeLineTotal(exclusive.lines[0])).toBe('300.00');
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

  it('shows success snackbar and "Next step" card with Match lines and Back to inbox after successful authorize', () => {
    const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
    spyOn(snackBar, 'open');

    const confirmedQuotation = {
      ...mockQuotationDetail,
      status: 'reviewed' as const,
      supplier_id: 'sup-1',
    };
    component.quotation.set({ ...mockQuotationDetail, supplier_id: 'sup-1' });
    component.selectedSupplierId.set('sup-1');
    apiService.patchQuotation.and.returnValue(of({ ...mockQuotationDetail, supplier_id: 'sup-1' }));
    apiService.confirmQuotation.and.returnValue(of(confirmedQuotation));
    apiService.getQuotation.and.returnValue(of(confirmedQuotation));

    component.confirmQuotation();
    fixture.detectChanges();

    expect(snackBar.open).toHaveBeenCalledWith(
      enCatalog.quotations.review.actions.confirmSuccess,
      undefined,
      { duration: 4000 },
    );

    const nextStepCard = fixture.nativeElement.querySelector('[data-testid="next-step-card"]');
    expect(nextStepCard).toBeTruthy();

    const matchBtn = fixture.nativeElement.querySelector('[data-testid="next-step-match-lines"]');
    expect(matchBtn).toBeTruthy();
    expect(matchBtn.textContent.trim()).toBe('Match lines');

    const inboxBtn = fixture.nativeElement.querySelector('[data-testid="next-step-back-inbox"]');
    expect(inboxBtn).toBeTruthy();
    expect(inboxBtn.textContent.trim()).toBe('Back to the inbox');
  });

  it('distinguishes between changed value (Corrected by Human) and confirmed-as-is (Confirmed)', () => {
    const lowConfField = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-currency',
      quotation_id: 'q-review-1',
      entity_type: 'quotation' as const,
      entity_id: 'q-review-1',
      field_name: 'currency',
      extracted_value: 'SAR',
      corrected_value: null,
      confidence: '0.6000',
      corrected_by: null,
      corrected_at: null,
    };
    component.quotation.set({
      ...mockQuotationDetail,
      field_extractions: [lowConfField],
    });
    fixture.detectChanges();

    // 1. Initially neither changed nor confirmed
    expect(component.isFieldChanged('quotation', 'q-review-1', 'currency')).toBeFalse();
    expect(component.isFieldConfirmedAsIs('quotation', 'q-review-1', 'currency')).toBeFalse();

    // 2. Confirmed as-is (value equals extracted_value)
    component.confirmFieldAsIs('quotation', 'q-review-1', 'currency');
    fixture.detectChanges();
    expect(component.isFieldChanged('quotation', 'q-review-1', 'currency')).toBeFalse();
    expect(component.isFieldConfirmedAsIs('quotation', 'q-review-1', 'currency')).toBeTrue();

    const confirmedBadge = fixture.nativeElement.querySelector('[data-testid="confirmed-badge"]');
    expect(confirmedBadge).toBeTruthy();
    expect(confirmedBadge.textContent.trim()).toBe('Confirmed');
    expect(fixture.nativeElement.querySelector('.corrected-tag')).toBeNull();

    // 3. Changed value (different from extracted_value)
    component.currencySelectionChanged('USD');
    fixture.detectChanges();
    expect(component.isFieldChanged('quotation', 'q-review-1', 'currency')).toBeTrue();
    expect(component.isFieldConfirmedAsIs('quotation', 'q-review-1', 'currency')).toBeFalse();

    const correctedTag = fixture.nativeElement.querySelector('.corrected-tag');
    expect(correctedTag).toBeTruthy();
    expect(correctedTag.textContent.trim()).toBe('Corrected by Human');
  });

  it('shows the corrected tag on the stated total field after a money correction differs from the extracted value', () => {
    const statedTotal = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-stated-total',
      field_name: 'stated_total',
      extracted_value: { amount: '88.00', currency: 'GBP' },
      confidence: '0.9500',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [statedTotal] });
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
    expect(input).toBeTruthy();
    input.value = '75.00';
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const fieldBox = fixture.nativeElement.querySelector('#field-fe-stated-total') as HTMLElement;
    expect(fieldBox.querySelector('.corrected-tag')).toBeTruthy();
    expect(fieldBox.querySelector('.confirmed-tag')).toBeNull();
  });

  it('shows the confirmed tag on the stated total field when the money correction equals the extracted value', () => {
    const statedTotal = {
      ...mockQuotationDetail.field_extractions[0],
      id: 'fe-stated-total',
      field_name: 'stated_total',
      extracted_value: { amount: '75.00', currency: 'GBP' },
      confidence: '0.9500',
    };
    component.quotation.set({ ...mockQuotationDetail, field_extractions: [statedTotal] });
    fixture.detectChanges();

    const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
    expect(input).toBeTruthy();
    input.value = '75';
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const fieldBox = fixture.nativeElement.querySelector('#field-fe-stated-total') as HTMLElement;
    expect(fieldBox.querySelector('.confirmed-tag')).toBeTruthy();
    expect(fieldBox.querySelector('.corrected-tag')).toBeNull();
  });

  it('displays exact stored amount with trailing decimal zeros removed in editable unit price input (PPS-121 B1)', () => {
    // 1. Read-only display of 85.0000 still shows "85"
    component.quotation.set({
      ...mockQuotationDetail,
      status: 'reviewed',
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          unit_price: { amount: '85.0000', currency: 'SAR' },
        },
      ],
    });
    fixture.detectChanges();

    const readOnlyInput = fixture.nativeElement.querySelector(
      '#field-fe-line1-price input',
    ) as HTMLInputElement | null;
    expect(readOnlyInput).toBeTruthy();
    expect(readOnlyInput?.value).toBe('85');

    // 2. Editable input carries exact stored amount with trailing zeros trimmed (85.0000 -> 85, 86.5000 -> 86.5, 0.1234 -> 0.1234)
    for (const status of ['extracted', 'in_review'] as const) {
      component.quotation.set({
        ...mockQuotationDetail,
        status,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            unit_price: { amount: '85.0000', currency: 'SAR' },
          },
        ],
      });
      fixture.detectChanges();

      const editableInput = fixture.nativeElement.querySelector(
        '#field-fe-line1-price input',
      ) as HTMLInputElement | null;
      expect(editableInput).toBeTruthy();
      expect(editableInput?.value).toBe('85');

      // Case 86.5000 -> 86.5
      component.quotation.set({
        ...mockQuotationDetail,
        status,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            unit_price: { amount: '86.5000', currency: 'SAR' },
          },
        ],
      });
      fixture.detectChanges();
      expect(editableInput?.value).toBe('86.5');

      // Case 0.1234 -> 0.1234
      component.quotation.set({
        ...mockQuotationDetail,
        status,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            unit_price: { amount: '0.1234', currency: 'SAR' },
          },
        ],
      });
      fixture.detectChanges();
      expect(editableInput?.value).toBe('0.1234');
    }
  });

  it('PPS-121 (B2): blurring an unedited low-confidence 86.0000 unit price stages no correction, while typing 86.125 stages exactly 86.125', () => {
    const lowConfPriceExtraction = {
      ...mockQuotationDetail.field_extractions[1],
      id: 'fe-line1-price',
      field_name: 'unit_price',
      extracted_value: { amount: '86.0000', currency: 'SAR' },
      confidence: '0.5000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      status: 'extracted',
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          unit_price: { amount: '86.0000', currency: 'SAR' },
        },
      ],
      field_extractions: [
        mockQuotationDetail.field_extractions[0],
        lowConfPriceExtraction,
      ],
    });
    fixture.detectChanges();

    const unitPriceInput = fixture.nativeElement.querySelector(
      '#field-fe-line1-price input',
    ) as HTMLInputElement;
    expect(unitPriceInput).toBeTruthy();
    expect(unitPriceInput.value).toBe('86');

    // Trigger blur on unedited field
    unitPriceInput.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    // Blurring an unedited field must stage NO correction
    expect(component.pendingCorrections().has('fe-line1-price')).toBeFalse();

    // saveCorrections sends no unit_price correction
    apiService.patchQuotation.and.returnValue(of(component.quotation()!));
    component.saveCorrections();
    if (apiService.patchQuotation.calls.count() > 0) {
      const patchPayload = apiService.patchQuotation.calls.mostRecent().args[1];
      const priceCorr = patchPayload.corrections?.find(
        (c) => c.field_extraction_id === 'fe-line1-price',
      );
      expect(priceCorr).toBeUndefined();
    }

    // Now type 86.125 and trigger blur/change
    unitPriceInput.value = '86.125';
    unitPriceInput.dispatchEvent(new Event('change'));
    unitPriceInput.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    const staged = component.pendingCorrections().get('fe-line1-price');
    expect(staged).toBeDefined();
    expect((staged as { amount: string }).amount).toBe('86.125');
  });

  it('PPS-121 (Delta): typing 0 on a line with null unit_price stages a correction with amount 0', () => {
    const missingPriceExtraction = {
      ...mockQuotationDetail.field_extractions[1],
      id: 'fe-line1-price',
      field_name: 'unit_price',
      extracted_value: null,
      confidence: '0.5000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      status: 'extracted',
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          unit_price: null,
        },
      ],
      field_extractions: [
        mockQuotationDetail.field_extractions[0],
        missingPriceExtraction,
      ],
    });
    fixture.detectChanges();

    const unitPriceInput = fixture.nativeElement.querySelector(
      '#field-fe-line1-price input',
    ) as HTMLInputElement;
    expect(unitPriceInput).toBeTruthy();
    expect(unitPriceInput.value).toBe('');

    unitPriceInput.value = '0';
    unitPriceInput.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const staged = component.pendingCorrections().get('fe-line1-price');
    expect(staged).toBeDefined();
    expect((staged as { amount: string }).amount).toBe('0');
  });

  it('PPS-121 (B3): Line Total input shows formatted amount without currency code in English and Arabic', () => {
    const priceExtraction = {
      ...mockQuotationDetail.field_extractions[1],
      id: 'fe-line1-price',
      field_name: 'unit_price',
      extracted_value: { amount: '86.0000', currency: 'SAR' },
      confidence: '0.9500',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          quantity: '20',
          unit_price: { amount: '86.0000', currency: 'SAR' },
          vat_rate: '0',
          delivery_fee: null,
          discount: null,
        },
      ],
      field_extractions: [
        mockQuotationDetail.field_extractions[0],
        priceExtraction,
      ],
    });
    fixture.detectChanges();

    const translate = TestBed.inject(TranslateService);
    translate.use('en');
    fixture.detectChanges();

    const lineTotalInput = fixture.nativeElement.querySelector(
      '.line-total-field input',
    ) as HTMLInputElement;
    expect(lineTotalInput).toBeTruthy();
    // 20 * 86 = 1720 -> "1,720"
    expect(lineTotalInput.value).toBe('1,720');

    // Arabic-Indic form in Arabic
    translate.use('ar');
    fixture.detectChanges();
    expect(lineTotalInput.value).toBe('١٬٧٢٠');

    // Non-whole total: 1720.50
    const nonWholePriceExtraction = {
      ...mockQuotationDetail.field_extractions[1],
      id: 'fe-line1-price',
      field_name: 'unit_price',
      extracted_value: { amount: '1720.50', currency: 'SAR' },
      confidence: '0.9500',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          quantity: '1',
          unit_price: { amount: '1720.50', currency: 'SAR' },
          vat_rate: '0',
          delivery_fee: null,
          discount: null,
        },
      ],
      field_extractions: [
        mockQuotationDetail.field_extractions[0],
        nonWholePriceExtraction,
      ],
    });
    translate.use('en');
    fixture.detectChanges();
    expect(lineTotalInput.value).toBe('1,720.50');

    translate.use('ar');
    fixture.detectChanges();
    expect(lineTotalInput.value).toBe('١٬٧٢٠٫٥٠');
  });

  it('PPS-120 (A1): busy state while authorizing disables actions, shows spinner in status pill, and avoids blank flash', () => {
    const confirmSubject = new Subject<Quotation>();
    apiService.confirmQuotation.and.returnValue(confirmSubject.asObservable());

    component.quotation.set({
      ...mockQuotationDetail,
      supplier_id: 'sup-1',
      status: 'in_review',
    });
    component.selectedSupplierId.set('sup-1');
    fixture.detectChanges();

    const isLoadingSpy = spyOn(component.isLoading, 'set').and.callThrough();

    component.confirmQuotation();
    fixture.detectChanges();

    expect(component.isConfirming()).toBeTrue();

    // Buttons must be disabled
    const refuseBtn = fixture.nativeElement.querySelector('.refuse-btn') as HTMLButtonElement;
    const saveBtn = fixture.nativeElement.querySelector('.save-btn') as HTMLButtonElement;
    const confirmBtn = fixture.nativeElement.querySelector('.confirm-btn') as HTMLButtonElement;
    const allHeaderBtns = Array.from(fixture.nativeElement.querySelectorAll('.header-actions button') as NodeListOf<HTMLButtonElement>);
    const retryBtn = allHeaderBtns.find((b) => b.textContent?.includes('Retry Extraction'));
    const requoteBtn = allHeaderBtns.find((b) => b.textContent?.includes('Create Re-Quote'));
    const archiveBtn = allHeaderBtns.find((b) => b.textContent?.includes('Archive'));
    const addLineBtn = fixture.nativeElement.querySelector('.add-line-btn') as HTMLButtonElement;

    expect(refuseBtn?.disabled).toBeTrue();
    expect(saveBtn?.disabled).toBeTrue();
    expect(confirmBtn?.disabled).toBeTrue();
    expect(retryBtn?.disabled).toBeTrue();
    expect(requoteBtn?.disabled).toBeTrue();
    expect(archiveBtn?.disabled).toBeTrue();
    expect(addLineBtn?.disabled).toBeTrue();

    // Replace document control must also be disabled and guard against execution
    const replaceDocBtn = fixture.nativeElement.querySelector('.replace-doc-btn') as HTMLButtonElement;
    expect(replaceDocBtn).toBeTruthy();
    expect(replaceDocBtn?.disabled).toBeTrue();

    const fakeFile = new File(['dummy'], 'replacement.pdf', { type: 'application/pdf' });
    const fakeEvent = {
      target: {
        files: [fakeFile],
        value: 'replacement.pdf',
      },
    } as unknown as Event;
    component.onReplaceDocumentSelected(fakeEvent);
    expect(apiService.presignDocument).not.toHaveBeenCalled();

    // Status pill
    const statusPill = fixture.nativeElement.querySelector('.page-header .status-pill') as HTMLElement;
    expect(statusPill).toBeTruthy();
    expect(statusPill.getAttribute('role')).toBe('status');
    expect(statusPill.getAttribute('aria-live')).toBe('polite');
    expect(statusPill.querySelector('mat-spinner')).toBeTruthy();
    expect(statusPill.textContent).toContain(enCatalog.quotations.review.status.authorizing);

    // Review section aria-busy
    const reviewSection = fixture.nativeElement.querySelector('.data-panel') as HTMLElement;
    expect(reviewSection.getAttribute('aria-busy')).toBe('true');

    // Emit reviewed quotation
    isLoadingSpy.calls.reset();
    const confirmedQuotation = {
      ...mockQuotationDetail,
      status: 'reviewed' as const,
      supplier_id: 'sup-1',
      reviewed_by: 'reviewer-1',
      reviewed_at: '2026-10-30T12:00:00Z',
    };
    apiService.getQuotation.and.returnValue(of(confirmedQuotation));
    confirmSubject.next(confirmedQuotation);
    confirmSubject.complete();
    fixture.detectChanges();

    expect(component.quotation()?.status).toBe('reviewed');
    expect(statusPill.textContent).toContain(enCatalog.quotations.review.status.reviewed);
    expect(isLoadingSpy).not.toHaveBeenCalledWith(true);
  });

  it('PPS-120 (A2): busy state holds during PATCH-first path when staged changes exist', () => {
    const patchSubject = new Subject<QuotationDetail>();
    apiService.patchQuotation.and.returnValue(patchSubject.asObservable());

    component.quotation.set({
      ...mockQuotationDetail,
      supplier_id: 'sup-1',
      status: 'in_review',
    });
    component.selectedSupplierId.set('sup-1');
    component.reviewerNotes.set('Staged change to notes');
    fixture.detectChanges();

    component.confirmQuotation();
    fixture.detectChanges();

    expect(component.isConfirming()).toBeTrue();

    const refuseBtn = fixture.nativeElement.querySelector('.refuse-btn') as HTMLButtonElement;
    const saveBtn = fixture.nativeElement.querySelector('.save-btn') as HTMLButtonElement;
    const confirmBtn = fixture.nativeElement.querySelector('.confirm-btn') as HTMLButtonElement;
    const allHeaderBtns = Array.from(fixture.nativeElement.querySelectorAll('.header-actions button') as NodeListOf<HTMLButtonElement>);
    const retryBtn = allHeaderBtns.find((b) => b.textContent?.includes('Retry Extraction'));
    const requoteBtn = allHeaderBtns.find((b) => b.textContent?.includes('Create Re-Quote'));
    const archiveBtn = allHeaderBtns.find((b) => b.textContent?.includes('Archive'));
    const addLineBtn = fixture.nativeElement.querySelector('.add-line-btn') as HTMLButtonElement;

    expect(refuseBtn?.disabled).toBeTrue();
    expect(saveBtn?.disabled).toBeTrue();
    expect(confirmBtn?.disabled).toBeTrue();
    expect(retryBtn?.disabled).toBeTrue();
    expect(requoteBtn?.disabled).toBeTrue();
    expect(archiveBtn?.disabled).toBeTrue();
    expect(addLineBtn?.disabled).toBeTrue();

    // Replace document control must also be disabled and guard against execution
    const replaceDocBtn = fixture.nativeElement.querySelector('.replace-doc-btn') as HTMLButtonElement;
    expect(replaceDocBtn).toBeTruthy();
    expect(replaceDocBtn?.disabled).toBeTrue();

    const fakeFile = new File(['dummy'], 'replacement.pdf', { type: 'application/pdf' });
    const fakeEvent = {
      target: {
        files: [fakeFile],
        value: 'replacement.pdf',
      },
    } as unknown as Event;
    component.onReplaceDocumentSelected(fakeEvent);
    expect(apiService.presignDocument).not.toHaveBeenCalled();

    const statusPill = fixture.nativeElement.querySelector('.page-header .status-pill') as HTMLElement;
    expect(statusPill.querySelector('mat-spinner')).toBeTruthy();
    expect(statusPill.textContent).toContain(enCatalog.quotations.review.status.authorizing);
  });

  it('PPS-120 (A3): on a 409 from /confirm, isConfirming becomes false and buttons are re-enabled', () => {
    apiService.confirmQuotation.and.returnValue(
      throwError(() => new HttpErrorResponse({
        status: 409,
        error: { details: { reason: 'quotation_not_confirmable' } },
      })),
    );

    component.quotation.set({
      ...mockQuotationDetail,
      supplier_id: 'sup-1',
      status: 'in_review',
    });
    component.selectedSupplierId.set('sup-1');
    fixture.detectChanges();

    component.confirmQuotation();
    fixture.detectChanges();

    expect(component.isConfirming()).toBeFalse();

    const allHeaderBtns = Array.from(fixture.nativeElement.querySelectorAll('.header-actions button') as NodeListOf<HTMLButtonElement>);
    const retryBtn = allHeaderBtns.find((b) => b.textContent?.includes('Retry Extraction'));
    const requoteBtn = allHeaderBtns.find((b) => b.textContent?.includes('Create Re-Quote'));
    const archiveBtn = allHeaderBtns.find((b) => b.textContent?.includes('Archive'));
    const addLineBtn = fixture.nativeElement.querySelector('.add-line-btn') as HTMLButtonElement;

    expect(retryBtn?.disabled).toBeFalse();
    expect(requoteBtn?.disabled).toBeFalse();
    expect(archiveBtn?.disabled).toBeFalse();
    expect(addLineBtn?.disabled).toBeFalse();
  });

  it('preserves exact 4-decimal unit price on blur and save of unchanged low-confidence price without staging rounded correction', () => {
    const lowConfPriceExtraction = {
      ...mockQuotationDetail.field_extractions[1],
      id: 'fe-line1-price',
      field_name: 'unit_price',
      extracted_value: { amount: '0.1234', currency: 'SAR' },
      confidence: '0.5000',
    };
    component.quotation.set({
      ...mockQuotationDetail,
      status: 'extracted',
      lines: [
        {
          ...mockQuotationDetail.lines[0],
          unit_price: { amount: '0.1234', currency: 'SAR' },
        },
      ],
      field_extractions: [
        mockQuotationDetail.field_extractions[0],
        lowConfPriceExtraction,
      ],
    });
    fixture.detectChanges();

    const unitPriceInput = fixture.nativeElement.querySelector(
      '#field-fe-line1-price input',
    ) as HTMLInputElement | null;
    expect(unitPriceInput).toBeTruthy();
    expect(unitPriceInput?.value).toBe('0.1234');

    // Trigger blur on unedited field
    unitPriceInput?.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    // Blur on an unedited field must not stage a correction at all (or, if staged, exactly 0.1234)
    const staged = component.pendingCorrections().get('fe-line1-price');
    if (staged) {
      expect((staged as { amount: string }).amount).toBe('0.1234');
    } else {
      expect(component.pendingCorrections().has('fe-line1-price')).toBeFalse();
    }

    // Saving must not send a rounded 0.12 correction
    apiService.patchQuotation.and.returnValue(of(component.quotation()!));
    component.saveCorrections();

    if (apiService.patchQuotation.calls.count() > 0) {
      const patchPayload = apiService.patchQuotation.calls.mostRecent().args[1];
      const priceCorr = patchPayload.corrections?.find(
        (c) => c.field_extraction_id === 'fe-line1-price',
      );
      if (priceCorr) {
        expect((priceCorr.corrected_value as { amount: string }).amount).toBe('0.1234');
      }
    }
  });

  describe('VAT-inclusive quote review (PPS-122)', () => {
    it('rejects a VAT rate outside 0–100 percent instead of patching an invalid fraction', () => {
      component.quotation.set({ ...mockQuotationDetail, field_extractions: [] });
      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.vatRateInputChanged('101');
      component.saveCorrections();
      expect(apiService.patchQuotation).not.toHaveBeenCalled();
    });

    it('confirms flagged VAT values as-is and sends both header values and corrections', () => {
      const extractions = [
        { id: 'fe-vat-inc', field_name: 'prices_include_vat', extracted_value: true },
        { id: 'fe-vat-rate', field_name: 'vat_rate', extracted_value: '0.15' },
      ].map(field => ({ ...field, quotation_id: mockQuotationDetail.id, entity_type: 'quotation' as const,
        entity_id: mockQuotationDetail.id, confidence: '0.8000', extraction_method: 'bedrock' as const,
        model_version: 'v1', corrected_value: null, corrected_by: null, corrected_at: null }));
      component.quotation.set({ ...mockQuotationDetail, prices_include_vat: true, vat_rate: '0.15', field_extractions: extractions });
      fixture.detectChanges();
      expect(component.flaggedFields().length).toBe(2);
      const host = fixture.nativeElement as HTMLElement;
      host.querySelector<HTMLButtonElement>('#field-fe-vat-inc .confirm-as-is-btn')!.click();
      host.querySelector<HTMLButtonElement>('#field-fe-vat-rate .confirm-as-is-btn')!.click();
      fixture.detectChanges();
      expect(component.flaggedFields().length).toBe(0);
      expect(host.querySelectorAll('[data-testid="confirmed-badge"]').length).toBe(2);
      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.saveCorrections();
      expect(apiService.patchQuotation.calls.mostRecent().args[1]).toEqual(jasmine.objectContaining({
        prices_include_vat: true, vat_rate: '0.15',
        corrections: jasmine.arrayContaining([
          { field_extraction_id: 'fe-vat-inc', corrected_value: true },
          { field_extraction_id: 'fe-vat-rate', corrected_value: '0.15' },
        ]),
      }));
    });

    it('enables saving when only VAT fields without extraction rows change', () => {
      component.quotation.set({ ...mockQuotationDetail, prices_include_vat: false, vat_rate: null, field_extractions: [] });
      component.reviewerNotes.set(mockQuotationDetail.reviewer_notes || '');
      expect(component.hasPendingReviewChanges()).toBeFalse();
      component.pricesIncludeVatToggled(true);
      expect(component.hasPendingReviewChanges()).toBeTrue();
      component.pendingPricesIncludeVat.set(undefined);
      component.vatRateInputChanged('15');
      expect(component.hasPendingReviewChanges()).toBeTrue();
    });

    it('(a) an extracted inclusive quote shows the checkbox checked, rate 15, flagged with the low-confidence pill and a «Confirm as is» button', () => {
      const vatIncExtraction: FieldExtraction = {
        id: 'fe-vat-inc',
        quotation_id: 'q-review-1',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'prices_include_vat',
        extracted_value: true,
        confidence: '0.8000',
        extraction_method: 'bedrock',
        model_version: 'v1',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      };
      const vatRateExtraction: FieldExtraction = {
        id: 'fe-vat-rate',
        quotation_id: 'q-review-1',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'vat_rate',
        extracted_value: '0.15',
        confidence: '0.8000',
        extraction_method: 'bedrock',
        model_version: 'v1',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      };
      component.quotation.set({
        ...mockQuotationDetail,
        prices_include_vat: true,
        vat_rate: '0.1500',
        field_extractions: [vatIncExtraction, vatRateExtraction],
      });
      fixture.detectChanges();

      const vatIncBox = fixture.nativeElement.querySelector('#field-fe-vat-inc');
      expect(vatIncBox).toBeTruthy();
      const checkbox = vatIncBox.querySelector('mat-checkbox input[type="checkbox"]') as HTMLInputElement;
      expect(checkbox).toBeTruthy();
      expect(checkbox.checked).toBeTrue();

      const vatRateBox = fixture.nativeElement.querySelector('#field-fe-vat-rate');
      expect(vatRateBox).toBeTruthy();
      const vatRateInput = vatRateBox.querySelector('input') as HTMLInputElement;
      expect(vatRateInput).toBeTruthy();
      expect(vatRateInput.value).toBe('15');

      const vatIncPill = vatIncBox.querySelector('.confidence-pill');
      expect(vatIncPill?.classList.contains('low-conf')).toBeTrue();
      expect(vatIncPill?.textContent?.trim()).toContain('80%');

      const vatRatePill = vatRateBox.querySelector('.confidence-pill');
      expect(vatRatePill?.classList.contains('low-conf')).toBeTrue();
      expect(vatRatePill?.textContent?.trim()).toContain('80%');

      const vatIncConfirmBtn = vatIncBox.querySelector('.confirm-as-is-btn');
      expect(vatIncConfirmBtn).toBeTruthy();

      const vatRateConfirmBtn = vatRateBox.querySelector('.confirm-as-is-btn');
      expect(vatRateConfirmBtn).toBeTruthy();

      expect(component.flaggedFields().map(f => f.fieldName)).toContain('prices_include_vat');
      expect(component.flaggedFields().map(f => f.fieldName)).toContain('vat_rate');
    });

    it('(b) confirming/changing sends the expected correction/patch (prices_include_vat: false / vat_rate: "0.05")', () => {
      const vatIncExtraction: FieldExtraction = {
        id: 'fe-vat-inc',
        quotation_id: 'q-review-1',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'prices_include_vat',
        extracted_value: true,
        confidence: '0.8000',
        extraction_method: 'bedrock',
        model_version: 'v1',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      };
      const vatRateExtraction: FieldExtraction = {
        id: 'fe-vat-rate',
        quotation_id: 'q-review-1',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'vat_rate',
        extracted_value: '0.15',
        confidence: '0.8000',
        extraction_method: 'bedrock',
        model_version: 'v1',
        corrected_value: null,
        corrected_by: null,
        corrected_at: null,
      };
      component.quotation.set({
        ...mockQuotationDetail,
        prices_include_vat: true,
        vat_rate: '0.1500',
        field_extractions: [vatIncExtraction, vatRateExtraction],
      });
      component.selectedSupplierId.set('sup-1');
      fixture.detectChanges();

      component.pricesIncludeVatToggled(false);
      component.vatRateInputChanged('5');

      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.saveCorrections();

      expect(apiService.patchQuotation).toHaveBeenCalledWith(
        'q-review-1',
        jasmine.objectContaining({
          prices_include_vat: false,
          vat_rate: '0.05',
          corrections: jasmine.arrayContaining([
            { field_extraction_id: 'fe-vat-inc', corrected_value: false },
            { field_extraction_id: 'fe-vat-rate', corrected_value: '0.05' },
          ]),
        }),
      );
    });

    it('(c) a quote without the extracted rows shows the field unflagged and unchecked, and toggling it sends prices_include_vat: true in the patch', () => {
      component.quotation.set({
        ...mockQuotationDetail,
        prices_include_vat: false,
        vat_rate: null,
        field_extractions: [],
      });
      component.selectedSupplierId.set('sup-1');
      fixture.detectChanges();

      const vatIncBox = fixture.nativeElement.querySelector('#field-prices_include_vat');
      expect(vatIncBox).toBeTruthy();
      const checkbox = vatIncBox.querySelector('mat-checkbox input[type="checkbox"]') as HTMLInputElement;
      expect(checkbox.checked).toBeFalse();
      expect(vatIncBox.querySelector('.confidence-pill')).toBeFalsy();
      expect(vatIncBox.querySelector('.confirm-as-is-btn')).toBeFalsy();
      expect(component.flaggedFields().map(f => f.fieldName)).not.toContain('prices_include_vat');

      component.pricesIncludeVatToggled(true);

      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.saveCorrections();

      expect(apiService.patchQuotation).toHaveBeenCalledWith(
        'q-review-1',
        jasmine.objectContaining({
          prices_include_vat: true,
        }),
      );
    });
  });

  describe('Error state and route param changes (PPS-156 / B7 & B8)', () => {
    it('(a) getQuotation errors with HttpErrorResponse 404 -> shows not-found error state, back link and retry control, and hides review form', () => {
      apiService.getQuotation.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 404, statusText: 'Not Found' })),
      );
      paramMapSubject.next(convertToParamMap({ id: 'missing-quote-id' }));
      fixture.detectChanges();

      const errorEl = fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]');
      expect(errorEl).toBeTruthy();
      expect(errorEl.textContent).toContain('Quotation not found');

      const backLink = errorEl.querySelector('a.back-link') ?? errorEl.querySelector('a');
      expect(backLink).toBeTruthy();
      expect(backLink?.getAttribute('routerLink') ?? backLink?.getAttribute('href')).toBe('/quotations');

      const buttons = Array.from(errorEl.querySelectorAll('button')) as HTMLButtonElement[];
      const retryBtn = buttons.find((b) => b.textContent?.includes('Retry'));
      expect(retryBtn).toBeTruthy();

      expect(fixture.nativeElement.querySelector('.page-header')).toBeFalsy();
      expect(fixture.nativeElement.querySelector('app-quotation-review-banners')).toBeFalsy();
    });

    it('(b) clicking Retry calls getQuotation again and on success renders the quotation', () => {
      apiService.getQuotation.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 500, error: { message: 'Server error' } })),
      );
      paramMapSubject.next(convertToParamMap({ id: 'retry-quote-id' }));
      fixture.detectChanges();

      const errorEl = fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]');
      expect(errorEl).toBeTruthy();

      const buttons = Array.from(errorEl.querySelectorAll('button')) as HTMLButtonElement[];
      const retryBtn = buttons.find((b) => b.textContent?.includes('Retry'));
      expect(retryBtn).toBeTruthy();

      apiService.getQuotation.and.returnValue(of(mockQuotationDetail));
      retryBtn?.click();
      fixture.detectChanges();

      expect(apiService.getQuotation).toHaveBeenCalledWith('retry-quote-id');
      expect(fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]')).toBeFalsy();
      expect(fixture.nativeElement.querySelector('.page-header')).toBeTruthy();
      expect(component.quotation()?.id).toBe('q-review-1');
    });

    it('(c) a non-404 failure (500 with an ApiError body incl. trace_id) shows the message and the trace id', () => {
      const apiError: ApiError = {
        code: 'internal_error',
        message: 'Database connection failed',
        details: {},
        trace_id: 'trace-test-12345',
      };
      apiService.getQuotation.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 500, statusText: 'Internal Server Error', error: apiError })),
      );
      paramMapSubject.next(convertToParamMap({ id: 'error-quote-id' }));
      fixture.detectChanges();

      const errorEl = fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]');
      expect(errorEl).toBeTruthy();
      expect(errorEl.textContent).toContain('Database connection failed');
      expect(errorEl.textContent).toContain('trace-test-12345');
    });

    it('(d) a failed silent reload keeps the quotation visible (no load-error state)', () => {
      expect(component.quotation()).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]')).toBeFalsy();

      apiService.getQuotation.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 500, error: { message: 'Background failure' } })),
      );
      component.loadQuotation('q-review-1', { silent: true });
      fixture.detectChanges();

      expect(component.quotation()).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[data-testid="quotation-load-error"]')).toBeFalsy();
      expect(fixture.nativeElement.querySelector('.page-header')).toBeTruthy();
    });

    it('(e) paramMap emitting a second id calls getQuotation with the new id, replaces the displayed quotation, and clears pending corrections and pending new lines left from the first', () => {
      component.pendingCorrections.set(new Map([['fe-line1-price', { amount: '30.00', currency: 'GBP' }]]));
      component.pendingNewLines.set([
        {
          original_text: 'Extra delivery charge',
          quantity: '1',
          unit_price_amount: '15.00',
          unit_price_currency: 'GBP',
        },
      ]);
      component.pendingRemoveLineIds.set(new Set(['line-1']));
      component.reviewerNotes.set('Notes for first quote');
      fixture.detectChanges();

      expect(component.pendingCorrections().size).toBe(1);
      expect(component.pendingNewLines().length).toBe(1);
      expect(component.pendingRemoveLineIds().size).toBe(1);

      const secondQuotation: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'q-review-2',
        reviewer_notes: 'Initial notes for second quote',
      };
      apiService.getQuotation.and.returnValue(of(secondQuotation));

      paramMapSubject.next(convertToParamMap({ id: 'q-review-2' }));
      fixture.detectChanges();

      expect(apiService.getQuotation).toHaveBeenCalledWith('q-review-2');
      expect(component.quotation()?.id).toBe('q-review-2');
      expect(component.pendingCorrections().size).toBe(0);
      expect(component.pendingNewLines().length).toBe(0);
      expect(component.pendingRemoveLineIds().size).toBe(0);
      expect(component.reviewerNotes()).toBe('Initial notes for second quote');
    });

    it('(f) paramMap emits id A, getQuotation(A) pending; paramMap emits id B and getQuotation(B) responds; then A response arrives -> quotation().id is still B', () => {
      const quoteASubject = new Subject<QuotationDetail>();
      const quoteBSubject = new Subject<QuotationDetail>();
      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return quoteASubject.asObservable();
        if (id === 'quote-B') return quoteBSubject.asObservable();
        return of(mockQuotationDetail);
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();

      const quoteB: QuotationDetail = { ...mockQuotationDetail, id: 'quote-B' };
      quoteBSubject.next(quoteB);
      fixture.detectChanges();

      expect(component.quotation()?.id).toBe('quote-B');

      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A' };
      quoteASubject.next(quoteA);
      fixture.detectChanges();

      expect(component.quotation()?.id).toBe('quote-B');
    });

    it('(g) A audit reply arriving after switching to B must not populate auditTrail', () => {
      const auditASubject = new Subject<{ items: AuditTrailEntry[] }>();
      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A' };
      const quoteB: QuotationDetail = { ...mockQuotationDetail, id: 'quote-B' };

      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return of(quoteA);
        if (id === 'quote-B') return of(quoteB);
        return of(mockQuotationDetail);
      });
      apiService.getAuditTrail.and.callFake((id: string) => {
        if (id === 'quote-A') return auditASubject.asObservable();
        return of({ items: [] });
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();

      const auditA: AuditTrailEntry = {
        id: 1,
        action: 'quotation.reviewed',
        actor_email: 'user@example.com',
        outcome: 'success',
        target: null,
        trace_id: null,
        occurred_at: '2026-10-30T10:00:00Z',
      };
      auditASubject.next({ items: [auditA] });
      fixture.detectChanges();

      expect(component.auditTrail()).toEqual([]);
    });

    it('(h) A document download URL arriving after switching to B must not populate documentPreviewUrl', () => {
      const docASubject = new Subject<{ download_url: string }>();
      const quoteA: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-A',
        document: { ...mockQuotationDetail.document, id: 'doc-A' },
      };
      const quoteB: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-B',
        document: { ...mockQuotationDetail.document, id: 'doc-B' },
      };

      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return of(quoteA);
        if (id === 'quote-B') return of(quoteB);
        return of(mockQuotationDetail);
      });
      apiService.getDocumentDownloadUrl.and.callFake((id: string) => {
        if (id === 'doc-A') return docASubject.asObservable();
        return of({ download_url: 'https://storage.example.com/doc-B.pdf' });
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();

      docASubject.next({ download_url: 'https://storage.example.com/doc-A-stale.pdf' });
      fixture.detectChanges();

      expect(component.documentPreviewUrl()).not.toBe('https://storage.example.com/doc-A-stale.pdf');
    });

    it('(i) a first-load HttpErrorResponse with status 0 and no ApiError body shows the translated generic message, not err.message', () => {
      const translate = TestBed.inject(TranslateService);
      const genericError = translate.instant('quotations.review.actions.genericError');

      const rawHttpError = new HttpErrorResponse({
        status: 0,
        statusText: 'Unknown Error',
        url: 'http://localhost/api/v1/quotations/quote-err-0',
      });
      apiService.getQuotation.and.returnValue(throwError(() => rawHttpError));

      paramMapSubject.next(convertToParamMap({ id: 'quote-err-0' }));
      fixture.detectChanges();

      expect(component.loadFailed()).toBeTrue();
      expect(component.errorMessage()).toBe(genericError);
      expect(component.errorMessage()).not.toBe(rawHttpError.message);
    });

    it('(j) saveCorrections for A pending, paramMap switches to B, B loads, then A PATCH response arrives -> quotation().id is still B, pendingCorrections for B untouched, getQuotation was not called again for A', () => {
      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A' };
      const quoteB: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-B',
        field_extractions: [
          {
            ...mockQuotationDetail.field_extractions[0],
            id: 'fe-quote-B-1',
            quotation_id: 'quote-B',
          },
        ],
      };
      const patchASubject = new Subject<QuotationDetail>();

      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return of(quoteA);
        if (id === 'quote-B') return of(quoteB);
        return of(mockQuotationDetail);
      });
      apiService.patchQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return patchASubject.asObservable();
        return of(quoteB);
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-A');

      component.pendingCorrections.set(new Map([['fe-quote-A-1', 'corrected-A']]));
      component.saveCorrections();
      expect(component.isSaving()).toBeTrue();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.isSaving()).toBeFalse();

      component.pendingCorrections.set(new Map([['fe-quote-B-1', 'corrected-B']]));
      apiService.getQuotation.calls.reset();

      patchASubject.next({ ...quoteA, reviewer_notes: 'Updated note A' });
      fixture.detectChanges();

      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.pendingCorrections().get('fe-quote-B-1')).toBe('corrected-B');
      expect(apiService.getQuotation).not.toHaveBeenCalledWith('quote-A');
    });

    it('(k) refuse for A pending then switch -> late response does not call loadQuotation/navigate/snackbar for A', () => {
      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A' };
      const quoteB: QuotationDetail = { ...mockQuotationDetail, id: 'quote-B' };
      const refuseASubject = new Subject<Quotation>();

      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return of(quoteA);
        if (id === 'quote-B') return of(quoteB);
        return of(mockQuotationDetail);
      });
      apiService.refuseQuotation.and.returnValue(refuseASubject.asObservable());

      const router = TestBed.inject(Router);
      spyOn(router, 'navigate');
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-A');

      component.refuseQuotation();
      expect(component.isRefusing()).toBeTrue();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.isRefusing()).toBeFalse();

      apiService.getQuotation.calls.reset();

      refuseASubject.next({ ...quoteA, status: 'refused' });
      fixture.detectChanges();

      expect(apiService.getQuotation).not.toHaveBeenCalledWith('quote-A');
      expect(router.navigate).not.toHaveBeenCalled();
      expect(snackBar.open).not.toHaveBeenCalled();
      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.isRefusing()).toBeFalse();
    });

    it('(l) retryExtraction for A pending then switch -> late response does not reload A', () => {
      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A', status: 'in_review' };
      const quoteB: QuotationDetail = { ...mockQuotationDetail, id: 'quote-B' };
      const retryASubject = new Subject<Quotation>();

      apiService.getQuotation.and.callFake((id: string) => {
        if (id === 'quote-A') return of(quoteA);
        if (id === 'quote-B') return of(quoteB);
        return of(mockQuotationDetail);
      });
      apiService.retryExtraction.and.returnValue(retryASubject.asObservable());
      spyOn(window, 'confirm').and.returnValue(true);

      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-A');

      component.retryExtraction();
      expect(component.isRetryingExtraction()).toBeTrue();

      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();
      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.isRetryingExtraction()).toBeFalse();

      apiService.getQuotation.calls.reset();

      retryASubject.next({ ...quoteA, status: 'extracted' });
      fixture.detectChanges();

      expect(apiService.getQuotation).not.toHaveBeenCalledWith('quote-A');
      expect(component.quotation()?.id).toBe('quote-B');
      expect(component.isRetryingExtraction()).toBeFalse();
    });
  });

  describe('Money parsing and totals (PPS-157 / P-125)', () => {
    it('(a) with lines totalling 1234.56 and a pending stated-total correction {amount: "1234.56"} the arithmetic banner is reconciled and arithmeticDifference() is "0.00"', () => {
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        currency: 'GBP',
        prices_include_vat: true,
        vat_rate: null,
        stated_total: { amount: '999.00', currency: 'GBP' },
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            quantity: '1',
            unit_price: { amount: '1234.56', currency: 'GBP' },
            vat_rate: null,
            delivery_fee: null,
            discount: null,
          },
        ],
        field_extractions: [
          {
            ...mockQuotationDetail.field_extractions[0],
            id: 'fe-stated-total',
            entity_type: 'quotation',
            entity_id: 'q-review-1',
            field_name: 'stated_total',
            extracted_value: { amount: '999.00', currency: 'GBP' },
            confidence: '0.9000',
            corrected_value: null,
          },
        ],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      expect(component.hasArithmeticMismatch()).toBeTrue();
      expect(component.isArithmeticReconciled()).toBeFalse();

      component.updateCorrection('fe-stated-total', { amount: '1234.56', currency: 'GBP' });
      fixture.detectChanges();

      expect(component.hasArithmeticMismatch()).toBeFalse();
      expect(component.isArithmeticReconciled()).toBeTrue();
      expect(component.arithmeticDifference()).toBe('0.00');

      component.revertToAiValue('fe-stated-total');
      fixture.detectChanges();

      expect(component.hasArithmeticMismatch()).toBeTrue();
      expect(component.isArithmeticReconciled()).toBeFalse();
    });

    it('(b) typing "٣٠٠" into the stated-total handler writes amount "300", typing "abc" writes nothing', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '250.00', currency: 'GBP' },
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      component.onStatedTotalInput(q, '٣٠٠');
      expect(component.pendingCorrections().get('fe-stated-total')).toEqual({
        amount: '300',
        currency: 'GBP',
      });

      // Clear pending corrections and verify 'abc' writes nothing
      component.pendingCorrections.set(new Map());
      component.onStatedTotalInput(q, 'abc');
      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
    });

    it('(c) typing "1.234,56" writes "1234.56"', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '250.00', currency: 'GBP' },
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      component.onStatedTotalInput(q, '1.234,56');
      expect(component.pendingCorrections().get('fe-stated-total')).toEqual({
        amount: '1234.56',
        currency: 'GBP',
      });
    });

    it('(d) a line with quantity 2, unit price 10, delivery 5, discount 3, VAT 0.15 on a VAT-exclusive quote shows a line total equal to the parent computeLineTotal (25.30) and on prices_include_vat quote 22.00', () => {
      const line = {
        ...mockQuotationDetail.lines[0],
        id: 'line-test-1',
        quantity: '2',
        unit_price: { amount: '10.00', currency: 'GBP' },
        delivery_fee: { amount: '5.00', currency: 'GBP' },
        discount: { amount: '3.00', currency: 'GBP' },
        vat_rate: '0.15',
      };
      const exclusiveQuote: QuotationDetail = {
        ...mockQuotationDetail,
        prices_include_vat: false,
        lines: [line],
      };
      component.quotation.set(exclusiveQuote);
      fixture.detectChanges();

      const exclusiveLineTotal = component.computeLineTotal(line);
      expect(exclusiveLineTotal).toBe('25.30');
      expect(component.lineTotals()['line-test-1']).toBe('25.30');

      const inclusiveQuote: QuotationDetail = {
        ...mockQuotationDetail,
        prices_include_vat: true,
        lines: [line],
      };
      component.quotation.set(inclusiveQuote);
      fixture.detectChanges();

      const inclusiveLineTotal = component.computeLineTotal(line);
      expect(inclusiveLineTotal).toBe('22.00');
      expect(component.lineTotals()['line-test-1']).toBe('22.00');
    });

    it('(e) addNewLine with quantity "٢" and price "١٢٫٥" calls the API with "2" and "12.5"', () => {
      component.quotation.set(mockQuotationDetail);
      fixture.detectChanges();

      component.newLineText.set('Arabic Digit Item');
      component.newLineQuantity.set('٢');
      component.newLinePriceAmount.set('١٢٫٥');
      component.addNewLine();

      expect(component.pendingNewLines()).toEqual([
        jasmine.objectContaining({
          original_text: 'Arabic Digit Item',
          quantity: '2',
          unit_price_amount: '12.5',
          unit_price_currency: 'GBP',
        }),
      ]);

      apiService.patchQuotation.and.returnValue(of(mockQuotationDetail));
      component.saveCorrections();

      expect(apiService.patchQuotation).toHaveBeenCalledWith(
        'q-review-1',
        jasmine.objectContaining({
          add_lines: [
            jasmine.objectContaining({
              quantity: '2',
              unit_price_amount: '12.5',
            }),
          ],
        }),
      );
    });

    it('(f) after pendingQuotationCurrency (or the currency correction) changes to "EGP" a stated-total edit carries currency "EGP"', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '250.00', currency: 'GBP' },
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      component.currencySelectionChanged('EGP');
      component.onStatedTotalInput(q, '500');

      const corr = component.pendingCorrections().get('fe-stated-total') as Money;
      expect(corr.currency).toBe('EGP');
      expect(corr.amount).toBe('500');
    });

    it('(g) focus/blur on a high-confidence stated total with displayed text "1,234.57" without input event does not stage a correction', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '1234.5678', currency: 'GBP' },
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '1234.5678', currency: 'GBP' },
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
      expect(input).toBeTruthy();
      expect(input.value).toContain('1,234.57');

      input.dispatchEvent(new Event('focus'));
      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
      expect(component.pendingCorrections().size).toBe(0);
      expect(component.hasPendingReviewChanges()).toBeFalse();

      component.onStatedTotalInput(q, '1,234.57', true);
      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
      expect(component.pendingCorrections().size).toBe(0);
    });

    it('(h) an input event with "1500" then blur creates a pending correction with amount "1500"', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '1234.5678', currency: 'GBP' },
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '1234.5678', currency: 'GBP' },
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
      input.value = '1500';
      input.dispatchEvent(new Event('input'));
      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections().get('fe-stated-total')).toEqual({
        amount: '1500',
        currency: 'GBP',
      });
      expect(component.hasPendingReviewChanges()).toBeTrue();

      component.pendingCorrections.set(new Map());
      component.onStatedTotalInput(q, '1500', false);
      component.onStatedTotalInput(q, '1500', true);
      expect(component.pendingCorrections().get('fe-stated-total')).toEqual({
        amount: '1500',
        currency: 'GBP',
      });
    });

    it('(i) blur with unparseable text stages nothing', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '1234.5678', currency: 'GBP' },
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '1234.5678', currency: 'GBP' },
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
      input.value = 'abc';
      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
      expect(component.pendingCorrections().size).toBe(0);

      component.onStatedTotalInput(q, 'not-a-number', true);
      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
      expect(component.pendingCorrections().size).toBe(0);
    });

    it('(j) low-confidence stated total blur keeps its existing reviewFieldValue behaviour', () => {
      const lowConfidenceTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total-low',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '1234.5678', currency: 'GBP' },
        confidence: '0.5400',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '1234.5678', currency: 'GBP' },
        field_extractions: [lowConfidenceTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-stated-total-low input') as HTMLInputElement;
      expect(input).toBeTruthy();

      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections().get('fe-stated-total-low')).toEqual({
        amount: '1234.57',
        currency: 'GBP',
      });
      expect(component.hasPendingReviewChanges()).toBeTrue();

      component.pendingCorrections.set(new Map());
      component.onStatedTotalInput(q, '1,234.57', true);
      expect(component.pendingCorrections().get('fe-stated-total-low')).toEqual({
        amount: '1234.57',
        currency: 'GBP',
      });
      expect(component.hasPendingReviewChanges()).toBeTrue();
    });

    it('(k) typing "1,234.50" into unit price stages canonical "1234.50", saveCorrections sends canonical, and banner total agrees', () => {
      const priceFe: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-line1-price-canon',
        entity_type: 'quotation_line',
        entity_id: 'line-1',
        field_name: 'unit_price',
        extracted_value: { amount: '10.00', currency: 'GBP' },
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            quantity: '1',
            unit_price: { amount: '10.00', currency: 'GBP' },
            vat_rate: '0',
          },
        ],
        field_extractions: [priceFe],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-line1-price-canon input') as HTMLInputElement;
      expect(input).toBeTruthy();

      input.value = '1,234.50';
      input.dispatchEvent(new Event('input'));
      input.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      const staged = component.pendingCorrections().get('fe-line1-price-canon');
      expect(staged).toEqual({
        amount: '1234.50',
        currency: 'GBP',
      });
      expect(component.computedLinesTotal()?.amount).toBe('1234.50');

      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.saveCorrections();
      expect(apiService.patchQuotation).toHaveBeenCalled();
      const patchPayload = apiService.patchQuotation.calls.mostRecent().args[1];
      const priceCorr = patchPayload.corrections?.find(
        (c) => c.field_extraction_id === 'fe-line1-price-canon',
      );
      expect(priceCorr?.corrected_value).toEqual({
        amount: '1234.50',
        currency: 'GBP',
      });
    });

    it('(l) typing "١٢٫٥" into quantity stages canonical "12.5", and "abc" stages nothing', () => {
      const qtyFe: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-line1-qty-canon',
        entity_type: 'quotation_line',
        entity_id: 'line-1',
        field_name: 'quantity',
        extracted_value: '1',
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            quantity: '1',
            unit_price: { amount: '10.00', currency: 'GBP' },
            vat_rate: '0',
          },
        ],
        field_extractions: [qtyFe],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-line1-qty-canon input') as HTMLInputElement;
      expect(input).toBeTruthy();

      input.value = 'abc';
      input.dispatchEvent(new Event('input'));
      input.dispatchEvent(new Event('change'));
      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      expect(component.pendingCorrections().has('fe-line1-qty-canon')).toBeFalse();

      input.value = '١٢٫٥';
      input.dispatchEvent(new Event('input'));
      input.dispatchEvent(new Event('change'));
      fixture.detectChanges();

      expect(component.pendingCorrections().get('fe-line1-qty-canon')).toBe('12.5');
      expect(component.computedLinesTotal()?.amount).toBe('125.00');
    });

    it('(m) stated total 30, one complete line worth 10 and a null-quantity line priced 20 -> computed total 10 (not 30) and the banner shows a mismatch', () => {
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '30.00', currency: 'GBP' },
        prices_include_vat: false,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            id: 'line-complete',
            quantity: '1',
            unit_price: { amount: '10.00', currency: 'GBP' },
            vat_rate: '0',
            delivery_fee: null,
            discount: null,
          },
          {
            ...mockQuotationDetail.lines[0],
            id: 'line-null-qty',
            quantity: null,
            unit_price: { amount: '20.00', currency: 'GBP' },
            vat_rate: '0',
            delivery_fee: null,
            discount: null,
          },
        ],
        field_extractions: [],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      expect(component.computeLineTotal(q.lines[0])).toBe('10.00');
      expect(component.computeLineTotal(q.lines[1])).toBeNull();
      expect(component.computedLinesTotal()?.amount).toBe('10.00');
      expect(component.hasArithmeticMismatch()).toBeTrue();
    });

    it('(n) typing "1" then clearing stated total leaves no stale correction, effectiveStatedTotal falls back, and saveCorrections sends no stated_total', () => {
      const feStatedTotal: FieldExtraction = {
        ...mockQuotationDetail.field_extractions[0],
        id: 'fe-stated-total',
        entity_type: 'quotation',
        entity_id: 'q-review-1',
        field_name: 'stated_total',
        extracted_value: { amount: '250.00', currency: 'GBP' },
        confidence: '0.9500',
        corrected_value: null,
        corrected_by: null,
      };
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '250.00', currency: 'GBP' },
        field_extractions: [feStatedTotal],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      const input = fixture.nativeElement.querySelector('#field-fe-stated-total input') as HTMLInputElement;
      expect(input).toBeTruthy();

      input.value = '1';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();

      expect(component.pendingCorrections().get('fe-stated-total')).toEqual({
        amount: '1',
        currency: 'GBP',
      });
      expect(component.effectiveStatedTotal()?.amount).toBe('1');

      input.value = '';
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();

      expect(component.pendingCorrections().has('fe-stated-total')).toBeFalse();
      expect(component.effectiveStatedTotal()?.amount).toBe('250.00');

      apiService.patchQuotation.and.returnValue(of(component.quotation()!));
      component.saveCorrections();
      expect(apiService.patchQuotation).toHaveBeenCalled();
      const patchPayload = apiService.patchQuotation.calls.mostRecent().args[1];
      const statedCorr = patchPayload.corrections?.find(
        (c) => c.field_extraction_id === 'fe-stated-total',
      );
      expect(statedCorr).toBeUndefined();
    });

    it('(o) stated total 250, every line missing quantity -> computedLinesTotal null, no mismatch shown', () => {
      const q: QuotationDetail = {
        ...mockQuotationDetail,
        stated_total: { amount: '250.00', currency: 'GBP' },
        prices_include_vat: false,
        lines: [
          {
            ...mockQuotationDetail.lines[0],
            id: 'line-no-qty-1',
            quantity: null,
            unit_price: { amount: '50.00', currency: 'GBP' },
            vat_rate: '0',
            delivery_fee: null,
            discount: null,
          },
          {
            ...mockQuotationDetail.lines[0],
            id: 'line-no-qty-2',
            quantity: null,
            unit_price: { amount: '100.00', currency: 'GBP' },
            vat_rate: '0',
            delivery_fee: null,
            discount: null,
          },
        ],
        field_extractions: [],
      };
      component.quotation.set(q);
      fixture.detectChanges();

      expect(component.computedLinesTotal()).toBeNull();
      expect(component.hasArithmeticMismatch()).toBeFalse();
      expect(fixture.nativeElement.querySelector('.arithmetic-mismatch-banner')).toBeNull();
    });
  });

  describe('Re-quote linking, reviewed button, and prior quotations selector (PPS-160 / P-128)', () => {
    const validUuid = 'c49d6c29-373f-4e02-9844-33d3d7890abc';

    it('(1) presets isRequote and selectedPreviousQuotationId from valid UUID requote_from param on quotation load', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      paramMapSubject.next(convertToParamMap({ id: 'q-review-1' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeTrue();
      expect(component.selectedPreviousQuotationId()).toBe(validUuid);
    });

    it('(2) does not preset isRequote when requote_from equals current quotation id', () => {
      const sameQuoteId = validUuid;
      apiService.getQuotation.and.returnValue(
        of({
          ...mockQuotationDetail,
          id: sameQuoteId,
        }),
      );
      queryParamMapSubject.next(convertToParamMap({ requote_from: sameQuoteId }));
      paramMapSubject.next(convertToParamMap({ id: sameQuoteId }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeFalse();
      expect(component.selectedPreviousQuotationId()).toBeNull();
    });

    it('(3) does not preset isRequote when requote_from is not a UUID', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: 'not-a-valid-uuid' }));
      paramMapSubject.next(convertToParamMap({ id: 'q-review-1' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeFalse();
      expect(component.selectedPreviousQuotationId()).toBeNull();
    });

    it('(4) does not preset isRequote when quotation is already reviewed', () => {
      const reviewedQuote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'q-reviewed-1',
        status: 'reviewed',
      };
      apiService.getQuotation.and.returnValue(of(reviewedQuote));

      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      paramMapSubject.next(convertToParamMap({ id: 'q-reviewed-1' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeFalse();
      expect(component.selectedPreviousQuotationId()).toBeNull();
    });

    it('(5) does not overwrite previous_quotation_id when quotation already has its own previous quotation linked', () => {
      const alreadyLinkedQuote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'q-linked-1',
        previous_quotation_id: 'q-existing-prior',
      };
      apiService.getQuotation.and.returnValue(of(alreadyLinkedQuote));

      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      paramMapSubject.next(convertToParamMap({ id: 'q-linked-1' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeTrue();
      expect(component.selectedPreviousQuotationId()).toBe('q-existing-prior');
    });

    it('(6) a second quotation without the param does not inherit it', () => {
      const quoteA: QuotationDetail = { ...mockQuotationDetail, id: 'quote-A' };
      const quoteB: QuotationDetail = { ...mockQuotationDetail, id: 'quote-B' };
      apiService.getQuotation.and.callFake((id: string) => of(id === 'quote-A' ? quoteA : quoteB));

      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      paramMapSubject.next(convertToParamMap({ id: 'quote-A' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeTrue();
      expect(component.selectedPreviousQuotationId()).toBe(validUuid);

      queryParamMapSubject.next(convertToParamMap({}));
      paramMapSubject.next(convertToParamMap({ id: 'quote-B' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeFalse();
      expect(component.selectedPreviousQuotationId()).toBeNull();
    });

    it('(7) offers Create re-quote button on reviewed quotations and clicking it navigates with queryParams', () => {
      const reviewedQuote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'q-reviewed-77',
        status: 'reviewed',
      };
      apiService.getQuotation.and.returnValue(of(reviewedQuote));
      paramMapSubject.next(convertToParamMap({ id: 'q-reviewed-77' }));
      fixture.detectChanges();

      const buttons = Array.from(fixture.nativeElement.querySelectorAll('header.page-header button')) as HTMLButtonElement[];
      const requoteBtn = buttons.find(
        (b) =>
          b.textContent?.includes('Create re-quote') ||
          b.textContent?.includes('إنشاء طلب إعادة عرض') ||
          b.querySelector('mat-icon')?.textContent?.trim() === 'content_copy',
      );
      expect(requoteBtn).toBeTruthy();

      const router = TestBed.inject(Router);
      spyOn(router, 'navigate');

      requoteBtn?.click();
      expect(router.navigate).toHaveBeenCalledWith(['/quotations/upload'], {
        queryParams: { requote_from: 'q-reviewed-77' },
      });
    });

    it('(8) makes selector request with supplier name search and filters out other suppliers and current quotation, newest first', () => {
      const quoteWithSupplier: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'current-quote-id',
        supplier_id: 'sup-1',
      };
      apiService.getQuotation.and.returnValue(of(quoteWithSupplier));
      component.suppliers.set([
        { id: 'sup-1', name: 'Dairy Direct Ltd', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);
      apiService.getReviewTasks.and.returnValue(
        of({
          items: [
            {
              id: 'task-1',
              quotation_id: 'current-quote-id',
              supplier_name: 'Dairy Direct Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-10T00:00:00Z',
            },
            {
              id: 'task-2',
              quotation_id: 'quote-other-supplier',
              supplier_name: 'Other Supplier Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-15T00:00:00Z',
            },
            {
              id: 'task-3',
              quotation_id: 'quote-prior-older',
              supplier_name: 'Dairy Direct Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-05T00:00:00Z',
            },
            {
              id: 'task-4',
              quotation_id: 'quote-prior-newer',
              supplier_name: 'Dairy Direct Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-20T00:00:00Z',
            },
            {
              id: 'task-5',
              quotation_id: 'quote-prior-newer',
              supplier_name: 'Dairy Direct Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-20T00:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      );

      paramMapSubject.next(convertToParamMap({ id: 'current-quote-id' }));
      fixture.detectChanges();
      component.loadPriorQuotations();

      expect(apiService.getReviewTasks).toHaveBeenCalledWith({
        status: 'all',
        limit: 100,
        search: 'Dairy Direct Ltd',
      });
      expect(component.priorQuotations()).toEqual([
        { id: 'quote-prior-newer', created_at: '2026-08-20T00:00:00Z', supplier_name: 'Dairy Direct Ltd' },
        { id: 'quote-prior-older', created_at: '2026-08-05T00:00:00Z', supplier_name: 'Dairy Direct Ltd' },
      ]);
    });

    it('(9) lists none and keeps empty state when current quotation has no supplier', () => {
      const quoteWithoutSupplier: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-no-sup',
        supplier_id: null,
      };
      apiService.getQuotation.and.returnValue(of(quoteWithoutSupplier));
      apiService.getReviewTasks.calls.reset();

      paramMapSubject.next(convertToParamMap({ id: 'quote-no-sup' }));
      fixture.detectChanges();
      component.loadPriorQuotations();

      expect(apiService.getReviewTasks).not.toHaveBeenCalled();
      expect(component.priorQuotations()).toEqual([]);
    });

    it('(10) cancels pending prior quotations request when switching quotations so late reply does not fill selector', () => {
      const quoteX: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-X',
        supplier_id: 'sup-x',
      };
      const quoteY: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-Y',
        supplier_id: 'sup-y',
      };
      component.suppliers.set([
        { id: 'sup-x', name: 'Supplier X', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-y', name: 'Supplier Y', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);

      const tasksXSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
      const tasksYSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();

      apiService.getQuotation.and.callFake((id: string) => of(id === 'quote-X' ? quoteX : quoteY));
      apiService.getReviewTasks.and.callFake((params: { search?: string }) => {
        if (params.search === 'Supplier X') {
          return tasksXSubject.asObservable();
        }
        return tasksYSubject.asObservable();
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-X' }));
      fixture.detectChanges();

      paramMapSubject.next(convertToParamMap({ id: 'quote-Y' }));
      fixture.detectChanges();

      // Late reply for supplier X arrives after switching to quotation of supplier Y
      tasksXSubject.next({
        items: [
          {
            id: 'task-x1',
            quotation_id: 'quote-x-prior',
            supplier_name: 'Supplier X',
            status: 'open',
            priority: 'normal',
            reason: 'review_required',
            created_at: '2026-08-10T00:00:00Z',
          },
        ],
        next_cursor: null,
      });

      expect(component.priorQuotations()).toEqual([]);
    });

    it('(11) drops stale prior quotations reply if supplier changes on the same quotation', () => {
      const quote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-same',
        supplier_id: 'sup-x',
      };
      apiService.getQuotation.and.returnValue(of(quote));
      component.suppliers.set([
        { id: 'sup-x', name: 'Supplier X', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-y', name: 'Supplier Y', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);

      const tasksXSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
      apiService.getReviewTasks.and.returnValue(tasksXSubject.asObservable());

      paramMapSubject.next(convertToParamMap({ id: 'quote-same' }));
      fixture.detectChanges();

      expect(apiService.getReviewTasks).toHaveBeenCalledWith({
        status: 'all',
        limit: 100,
        search: 'Supplier X',
      });

      // Supplier changes on the same quotation before response arrives
      component.selectedSupplierId.set('sup-y');

      // Stale reply for Supplier X arrives
      tasksXSubject.next({
        items: [
          {
            id: 'task-x1',
            quotation_id: 'quote-x-prior',
            supplier_name: 'Supplier X',
            status: 'open',
            priority: 'normal',
            reason: 'review_required',
            created_at: '2026-08-10T00:00:00Z',
          },
        ],
        next_cursor: null,
      });

      // Dropped because current supplier name is Supplier Y, not Supplier X
      expect(component.priorQuotations()).toEqual([]);
    });

    it('keeps supplier Y prior quotations when supplier changes X -> Y quickly with X reply arriving last (success variant)', () => {
      const quote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-interleave-1',
        supplier_id: 'sup-x',
      };
      apiService.getQuotation.and.returnValue(of(quote));
      component.suppliers.set([
        { id: 'sup-x', name: 'Supplier X', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-y', name: 'Supplier Y', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);

      const tasksXSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
      const tasksYSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();

      apiService.getReviewTasks.and.callFake((params?: { search?: string }) => {
        if (params?.search === 'Supplier X') {
          return tasksXSubject.asObservable();
        }
        if (params?.search === 'Supplier Y') {
          return tasksYSubject.asObservable();
        }
        return of({ items: [], next_cursor: null });
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-interleave-1' }));
      fixture.detectChanges();

      expect(apiService.getReviewTasks).toHaveBeenCalledWith({
        status: 'all',
        limit: 100,
        search: 'Supplier X',
      });

      // Quick change to Supplier Y:
      component.selectedSupplierId.set('sup-y');
      component.loadPriorQuotations();

      expect(apiService.getReviewTasks).toHaveBeenCalledWith({
        status: 'all',
        limit: 100,
        search: 'Supplier Y',
      });

      // Supplier Y reply arrives first:
      tasksYSubject.next({
        items: [
          {
            id: 'task-y1',
            quotation_id: 'quote-y-prior',
            supplier_name: 'Supplier Y',
            status: 'open',
            priority: 'normal',
            reason: 'review_required',
            created_at: '2026-08-15T00:00:00Z',
          },
        ],
        next_cursor: null,
      });

      expect(component.priorQuotations()).toEqual([
        { id: 'quote-y-prior', created_at: '2026-08-15T00:00:00Z', supplier_name: 'Supplier Y' },
      ]);

      // Superseded Supplier X reply arrives last (success):
      tasksXSubject.next({
        items: [
          {
            id: 'task-x1',
            quotation_id: 'quote-x-prior',
            supplier_name: 'Supplier X',
            status: 'open',
            priority: 'normal',
            reason: 'review_required',
            created_at: '2026-08-10T00:00:00Z',
          },
        ],
        next_cursor: null,
      });

      // List stays Y's:
      expect(component.priorQuotations()).toEqual([
        { id: 'quote-y-prior', created_at: '2026-08-15T00:00:00Z', supplier_name: 'Supplier Y' },
      ]);
    });

    it('keeps supplier Y prior quotations when supplier changes X -> Y quickly with X reply arriving last (error variant)', () => {
      const quote: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-interleave-2',
        supplier_id: 'sup-x',
      };
      apiService.getQuotation.and.returnValue(of(quote));
      component.suppliers.set([
        { id: 'sup-x', name: 'Supplier X', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-y', name: 'Supplier Y', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);

      const tasksXSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
      const tasksYSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();

      apiService.getReviewTasks.and.callFake((params?: { search?: string }) => {
        if (params?.search === 'Supplier X') {
          return tasksXSubject.asObservable();
        }
        if (params?.search === 'Supplier Y') {
          return tasksYSubject.asObservable();
        }
        return of({ items: [], next_cursor: null });
      });

      paramMapSubject.next(convertToParamMap({ id: 'quote-interleave-2' }));
      fixture.detectChanges();

      // Quick change to Supplier Y:
      component.selectedSupplierId.set('sup-y');
      component.loadPriorQuotations();

      // Supplier Y reply arrives first:
      tasksYSubject.next({
        items: [
          {
            id: 'task-y1',
            quotation_id: 'quote-y-prior',
            supplier_name: 'Supplier Y',
            status: 'open',
            priority: 'normal',
            reason: 'review_required',
            created_at: '2026-08-15T00:00:00Z',
          },
        ],
        next_cursor: null,
      });

      expect(component.priorQuotations()).toEqual([
        { id: 'quote-y-prior', created_at: '2026-08-15T00:00:00Z', supplier_name: 'Supplier Y' },
      ]);

      // Superseded Supplier X reply arrives last (error):
      tasksXSubject.error(new Error('Stale network failure'));

      // List stays Y's (not cleared by error callback):
      expect(component.priorQuotations()).toEqual([
        { id: 'quote-y-prior', created_at: '2026-08-15T00:00:00Z', supplier_name: 'Supplier Y' },
      ]);
    });

    it('(12) calls getReviewTasks with supplier name and populates prior quotations when accepting supplier suggestion on quote opened with requote_from and no supplier_id', () => {
      const quoteNoSupplier: QuotationDetail = {
        ...mockQuotationDetail,
        id: 'quote-no-supplier',
        supplier_id: null,
        suggested_supplier_id: 'sup-sugg',
        suggested_supplier_name: 'Acme Suggested Ltd',
        supplier_match_confidence: '0.95',
      };
      apiService.getQuotation.and.returnValue(of(quoteNoSupplier));
      component.suppliers.set([
        { id: 'sup-sugg', name: 'Acme Suggested Ltd', status: 'active', created_at: '2026-08-01T00:00:00Z' },
      ]);
      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({
          items: [
            {
              id: 'task-sugg-1',
              quotation_id: 'quote-prior-acme',
              supplier_name: 'Acme Suggested Ltd',
              status: 'open',
              priority: 'normal',
              reason: 'review_required',
              created_at: '2026-08-15T00:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      );

      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      paramMapSubject.next(convertToParamMap({ id: 'quote-no-supplier' }));
      fixture.detectChanges();

      expect(component.isRequote()).toBeTrue();
      expect(component.selectedPreviousQuotationId()).toBe(validUuid);
      expect(apiService.getReviewTasks).not.toHaveBeenCalled();
      expect(component.priorQuotations()).toEqual([]);

      component.acceptSupplierSuggestion();
      fixture.detectChanges();

      expect(component.selectedSupplierId()).toBe('sup-sugg');
      expect(apiService.getReviewTasks).toHaveBeenCalledWith({
        status: 'all',
        limit: 100,
        search: 'Acme Suggested Ltd',
      });
      expect(component.priorQuotations()).toEqual([
        { id: 'quote-prior-acme', created_at: '2026-08-15T00:00:00Z', supplier_name: 'Acme Suggested Ltd' },
      ]);
    });
  });

  describe('PPS-159 Detail-page findings', () => {
    describe('Finding 1: Extraction polling', () => {
      it('polls quotation after retryExtraction until extraction leaves in-progress state', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        const finishedQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracted',
        };
        apiService.retryExtraction.and.returnValue(of(inProgressQuote));
        spyOn(window, 'confirm').and.returnValue(true);
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        component.retryExtraction();
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeTrue();
        expect(fixture.nativeElement.querySelector('[data-testid="extraction-processing-banner"]')).toBeTruthy();

        // Advance polling interval
        apiService.getQuotation.and.returnValue(of(finishedQuote));
        tick(2000);
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        expect(component.quotation()?.status).toBe('extracted');
        expect(fixture.nativeElement.querySelector('[data-testid="extraction-processing-banner"]')).toBeFalsy();
      }));

      it('polls quotation after replaceDocument until extraction leaves in-progress state', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        const finishedQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracted',
        };
        apiService.uploadFileToStorage.and.returnValue(of(undefined));
        apiService.replaceDocument.and.returnValue(of(inProgressQuote));
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        const dummyFile = new File(['dummy'], 'new-quote.pdf', { type: 'application/pdf' });
        const dummyEvent = {
          target: { files: [dummyFile], value: 'fake' },
        } as unknown as Event;

        component.onReplaceDocumentSelected(dummyEvent);
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeTrue();

        apiService.getQuotation.and.returnValue(of(finishedQuote));
        tick(2000);
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        expect(component.quotation()?.status).toBe('extracted');
      }));

      it('stops polling when route parameter changes or destroyed', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        apiService.retryExtraction.and.returnValue(of(inProgressQuote));
        spyOn(window, 'confirm').and.returnValue(true);
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        component.retryExtraction();
        fixture.detectChanges();
        expect(component.isPollingExtraction()).toBeTrue();

        // Route changes to a different quotation
        const otherQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-other',
          status: 'extracted',
        };
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(otherQuote));
        paramMapSubject.next(convertToParamMap({ id: 'q-other' }));
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        tick(2500);
        expect(apiService.getQuotation).not.toHaveBeenCalledWith('q-review-1');
      }));

      it('stops polling and shows timeout banner after maximum poll attempts without infinite spinner', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        apiService.retryExtraction.and.returnValue(of(inProgressQuote));
        spyOn(window, 'confirm').and.returnValue(true);
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        component.retryExtraction();
        fixture.detectChanges();
        expect(component.isPollingExtraction()).toBeTrue();

        // Advance through 31 intervals
        for (let i = 0; i < 31; i++) {
          tick(2000);
        }
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        expect(component.extractionPollTimedOut()).toBeTrue();
        expect(fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]')).toBeTruthy();
      }));

      it('survives transient errors during polling and continues polling', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        const finishedQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracted',
        };
        apiService.retryExtraction.and.returnValue(of(inProgressQuote));
        spyOn(window, 'confirm').and.returnValue(true);
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        component.retryExtraction();
        fixture.detectChanges();
        expect(component.isPollingExtraction()).toBeTrue();

        // Transient failure
        apiService.getQuotation.and.returnValue(throwError(() => new HttpErrorResponse({ status: 503 })));
        tick(2000);
        fixture.detectChanges();

        // Polling is still active despite single error
        expect(component.isPollingExtraction()).toBeTrue();

        // Now returns succeeded
        apiService.getQuotation.and.returnValue(of(finishedQuote));
        tick(2000);
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        expect(component.quotation()?.status).toBe('extracted');
      }));

      it('preserves user edits (notes, supplier, currency) when clicking retry after polling times out', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
          reviewer_notes: null,
          supplier_id: null,
          currency: 'GBP',
        };
        apiService.retryExtraction.and.returnValue(of(inProgressQuote));
        spyOn(window, 'confirm').and.returnValue(true);
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(inProgressQuote));

        // Start extraction polling via retryExtraction
        component.retryExtraction();
        fixture.detectChanges();
        expect(component.isPollingExtraction()).toBeTrue();

        // User edits reviewer notes, supplier, and currency while extraction is in progress
        component.reviewerNotes.set('Special urgent instructions');
        component.selectedSupplierId.set('sup-user-edit-uuid');
        component.pendingQuotationCurrency.set('EUR');
        fixture.detectChanges();

        // Let polling time out
        for (let i = 0; i < 31; i++) {
          tick(2000);
        }
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeFalse();
        expect(component.extractionPollTimedOut()).toBeTrue();

        const banner = fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]');
        expect(banner).toBeTruthy();

        // Server returns in-progress quote with server values on retry
        const serverPendingQuote: QuotationDetail = {
          ...inProgressQuote,
          reviewer_notes: 'server notes',
          supplier_id: 'sup-server-uuid',
          currency: 'GBP',
        };
        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.returnValue(of(serverPendingQuote));

        // Click retry button in timeout banner
        const retryBtn = banner.querySelector('button') as HTMLButtonElement;
        expect(retryBtn).toBeTruthy();
        retryBtn.click();
        fixture.detectChanges();
        tick();

        // Verify user edits survived and polling resumed
        expect(component.reviewerNotes()).toBe('Special urgent instructions');
        expect(component.selectedSupplierId()).toBe('sup-user-edit-uuid');
        expect(component.pendingQuotationCurrency()).toBe('EUR');
        expect(component.extractionPollTimedOut()).toBeFalse();
        expect(component.isPollingExtraction()).toBeTrue();
      }));

      it('completes and observes responses with 2.5s latency with exactly one request in flight at a time', fakeAsync(() => {
        const inProgressQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracting',
        };
        const finishedQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-review-1',
          status: 'extracted',
        };

        let inFlight = 0;
        let maxInFlight = 0;
        let responsesReceived = 0;
        let callCount = 0;

        apiService.getQuotation.calls.reset();
        apiService.getQuotation.and.callFake(() => {
          callCount++;
          inFlight++;
          if (inFlight > maxInFlight) {
            maxInFlight = inFlight;
          }
          const quoteToReturn = callCount === 1 ? inProgressQuote : finishedQuote;
          return timer(2500).pipe(
            map(() => {
              responsesReceived++;
              return quoteToReturn;
            }),
            finalize(() => {
              inFlight--;
            }),
          );
        });

        component.startExtractionPolling('q-review-1');
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeTrue();
        expect(maxInFlight).toBe(1);
        expect(inFlight).toBe(1);

        // Advance 2000ms: request 1 is still in flight (latency is 2.5s)
        // With switchMap, this would abort request 1 and schedule another one.
        // With sequential polling, request 1 continues and no new request is launched.
        tick(2000);
        fixture.detectChanges();

        expect(component.isPollingExtraction()).toBeTrue();
        expect(maxInFlight).toBe(1);
        expect(inFlight).toBe(1);
        expect(responsesReceived).toBe(0);

        // Advance remaining 500ms to complete request 1
        tick(500);
        fixture.detectChanges();

        expect(responsesReceived).toBe(1);
        expect(maxInFlight).toBe(1);
        expect(inFlight).toBe(0);
        expect(component.isPollingExtraction()).toBeTrue();

        // 2000ms interval between requests: no request is in flight
        tick(1000);
        fixture.detectChanges();
        expect(inFlight).toBe(0);

        tick(1000); // 2000ms elapsed since request 1 finished; request 2 starts
        fixture.detectChanges();
        expect(inFlight).toBe(1);
        expect(maxInFlight).toBe(1);

        // Advance 2500ms to complete request 2 (returns extracted)
        tick(2500);
        fixture.detectChanges();

        expect(responsesReceived).toBe(2);
        expect(maxInFlight).toBe(1);
        expect(component.isPollingExtraction()).toBeFalse();

        // Advance 2500ms for final silent loadQuotation
        tick(2500);
        fixture.detectChanges();

        expect(inFlight).toBe(0);
        expect(maxInFlight).toBe(1);
        expect(component.quotation()?.status).toBe('extracted');
      }));
    });

    describe('Finding 2: Refuse confirmation dialog', () => {
      it('opens confirmation dialog on refuse click and does nothing when cancelled', () => {
        dialogSpy.open.calls.reset();
        apiService.refuseQuotation.calls.reset();
        dialogSpy.open.and.returnValue({
          afterClosed: () => of(false),
        } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

        component.refuseQuotation();

        expect(dialogSpy.open).toHaveBeenCalledWith(
          CatalogueConfirmDialogComponent,
          jasmine.objectContaining({
            width: '440px',
            data: jasmine.objectContaining({
              titleKey: 'quotations.review.refuseConfirm.title',
              messageKey: 'quotations.review.refuseConfirm.message',
              confirmKey: 'quotations.review.refuseConfirm.confirm',
              cancelKey: 'quotations.review.refuseConfirm.cancel',
              isDestructive: true,
            }),
          }),
        );
        expect(apiService.refuseQuotation).not.toHaveBeenCalled();
        expect(component.isRefusing()).toBeFalse();
      });

      it('calls apiService.refuseQuotation when confirm dialog is confirmed', () => {
        dialogSpy.open.calls.reset();
        apiService.refuseQuotation.calls.reset();
        dialogSpy.open.and.returnValue({
          afterClosed: () => of(true),
        } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
        apiService.refuseQuotation.and.returnValue(of(mockQuotationDetail));

        component.refuseQuotation();

        expect(dialogSpy.open).toHaveBeenCalled();
        expect(apiService.refuseQuotation).toHaveBeenCalledWith('q-review-1');
      });
    });

    describe('Finding 3: Refused quotation controls', () => {
      it('hides or disables editing controls, lines editing, Save and Confirm on refused quotation', () => {
        const refusedQuote: QuotationDetail = {
          ...mockQuotationDetail,
          id: 'q-refused-1',
          status: 'refused',
        };
        component.quotation.set(refusedQuote);
        fixture.detectChanges();

        // Save & Confirm buttons must be hidden
        expect(fixture.nativeElement.querySelector('.save-btn')).toBeFalsy();
        expect(fixture.nativeElement.querySelector('.confirm-btn')).toBeFalsy();
        expect(fixture.nativeElement.querySelector('.refuse-btn')).toBeFalsy();

        // Supplier select must be disabled
        const supplierSelect = fixture.debugElement.query(By.css('#supplier-select'));
        expect(supplierSelect.attributes['aria-disabled']).toBe('true');

        // Add line button must be hidden
        expect(fixture.nativeElement.querySelector('.add-line-btn')).toBeFalsy();

        // Remove line button must be hidden
        expect(fixture.nativeElement.querySelector('[data-testid="remove-line-btn"]') || fixture.nativeElement.querySelector('button[mattooltip="quotations.review.lines.removeLine"]')).toBeFalsy();

        // Audit trail is still present
        expect(fixture.nativeElement.querySelector('app-quotation-audit-trail')).toBeTruthy();
      });
    });

    describe('Header field boxes are groups, not buttons (PPS-162 / P-130)', () => {
      it('wraps each header control in a named group instead of a role=button that nests inputs', () => {
        component.quotation.set({ ...mockQuotationDetail, id: 'q-a11y-1' });
        fixture.detectChanges();

        const boxes = Array.from(
          (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('.field-box'),
        );
        expect(boxes.length).toBeGreaterThan(0);
        for (const box of boxes) {
          expect(box.getAttribute('role')).not.toBe('button');
          expect(box.getAttribute('tabindex')).toBeNull();
          expect(box.getAttribute('role')).toBe('group');
          const labelledBy = box.getAttribute('aria-labelledby');
          const name = labelledBy
            ? (fixture.nativeElement as HTMLElement).querySelector('#' + labelledBy)?.textContent?.trim()
            : box.getAttribute('aria-label')?.trim();
          expect(name).withContext(box.id).toBeTruthy();
        }
      });

      it('focusing a control inside a field box selects that field (keyboard and mouse)', () => {
        component.quotation.set({ ...mockQuotationDetail, id: 'q-a11y-2' });
        fixture.detectChanges();
        const spy = spyOn(component, 'selectField').and.callThrough();

        const box = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('.field-box');
        expect(box).not.toBeNull();
        box!.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));

        expect(spy).toHaveBeenCalledTimes(1);
      });
    });

    describe('Finding 4: Unsaved-changes guard & beforeunload', () => {
      it('allows leaving without prompt when nothing is pending', () => {
        dialogSpy.open.calls.reset();
        const canLeave = component.canDeactivate();
        expect(canLeave).toBeTrue();
        expect(dialogSpy.open).not.toHaveBeenCalled();
      });

      it('allows leaving without prompt when quotation is already reviewed or refused', () => {
        component.quotation.set({ ...mockQuotationDetail, status: 'reviewed' });
        component.reviewerNotes.set('Unsaved draft notes');
        fixture.detectChanges();

        dialogSpy.open.calls.reset();
        expect(component.canDeactivate()).toBeTrue();
        expect(dialogSpy.open).not.toHaveBeenCalled();

        component.quotation.set({ ...mockQuotationDetail, status: 'refused' });
        fixture.detectChanges();
        expect(component.canDeactivate()).toBeTrue();
        expect(dialogSpy.open).not.toHaveBeenCalled();
      });

      it('prompts via confirm dialog when corrections, supplier, or notes are pending and allows leaving on confirm', (done) => {
        component.quotation.set(mockQuotationDetail);
        component.reviewerNotes.set('New unsaved notes');
        fixture.detectChanges();

        dialogSpy.open.calls.reset();
        dialogSpy.open.and.returnValue({
          afterClosed: () => of(true),
        } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

        const result = component.canDeactivate();
        expect(dialogSpy.open).toHaveBeenCalledWith(
          CatalogueConfirmDialogComponent,
          jasmine.objectContaining({
            width: '440px',
            data: jasmine.objectContaining({
              titleKey: 'quotations.review.unsavedChanges.title',
              messageKey: 'quotations.review.unsavedChanges.message',
              confirmKey: 'quotations.review.unsavedChanges.confirm',
              cancelKey: 'quotations.review.unsavedChanges.cancel',
              isDestructive: true,
            }),
          }),
        );

        if (typeof result === 'boolean') {
          fail('expected observable');
          done();
        } else {
          result.subscribe((allowed: boolean) => {
            expect(allowed).toBeTrue();
            done();
          });
        }
      });

      it('cancels navigation when confirm dialog is cancelled', (done) => {
        component.quotation.set(mockQuotationDetail);
        component.selectedSupplierId.set('sup-changed');
        fixture.detectChanges();

        dialogSpy.open.calls.reset();
        dialogSpy.open.and.returnValue({
          afterClosed: () => of(false),
        } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

        const result = component.canDeactivate();
        expect(dialogSpy.open).toHaveBeenCalled();

        if (typeof result === 'boolean') {
          fail('expected observable');
          done();
        } else {
          result.subscribe((allowed: boolean) => {
            expect(allowed).toBeFalse();
            done();
          });
        }
      });

      it('prevents beforeunload when changes are pending', () => {
        component.quotation.set(mockQuotationDetail);
        component.reviewerNotes.set('Unsaved notes');
        fixture.detectChanges();

        const event = {
          preventDefault: jasmine.createSpy('preventDefault'),
          returnValue: undefined as unknown as string,
        } as unknown as BeforeUnloadEvent;

        component.onBeforeUnload(event);

        expect(event.preventDefault).toHaveBeenCalled();
        expect(event.returnValue).toBe('');
      });

      it('does not prevent beforeunload when pristine', () => {
        component.quotation.set(mockQuotationDetail);
        fixture.detectChanges();

        const event = {
          preventDefault: jasmine.createSpy('preventDefault'),
          returnValue: undefined as unknown as string,
        } as unknown as BeforeUnloadEvent;

        component.onBeforeUnload(event);

        expect(event.preventDefault).not.toHaveBeenCalled();
        expect(event.returnValue).toBeUndefined();
      });
    });

    describe('P2 Review Fixes (F1 - F4)', () => {
      describe('F1: Polling-timeout banner clearing', () => {
        it('clears extraction timeout banner on route change / resetPerQuotationState', fakeAsync(() => {
          component.extractionPollTimedOut.set(true);
          fixture.detectChanges();
          expect(fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]')).toBeTruthy();

          const otherQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-other-extracted',
            status: 'extracted',
          };
          apiService.getQuotation.calls.reset();
          apiService.getQuotation.and.returnValue(of(otherQuote));

          paramMapSubject.next(convertToParamMap({ id: 'q-other-extracted' }));
          fixture.detectChanges();
          tick();

          expect(component.extractionPollTimedOut()).toBeFalse();
          expect(fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]')).toBeFalsy();
        }));

        it('clears extraction timeout banner when loadQuotation returns extracted status', fakeAsync(() => {
          component.extractionPollTimedOut.set(true);
          fixture.detectChanges();
          expect(fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]')).toBeTruthy();

          const extractedQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-review-1',
            status: 'extracted',
          };
          apiService.getQuotation.calls.reset();
          apiService.getQuotation.and.returnValue(of(extractedQuote));

          component.loadQuotation('q-review-1');
          fixture.detectChanges();
          tick();

          expect(component.extractionPollTimedOut()).toBeFalse();
          expect(fixture.nativeElement.querySelector('[data-testid="extraction-timeout-banner"]')).toBeFalsy();
        }));
      });

      describe('F2: Archive confirmation with unsaved edits', () => {
        it('prompts to discard unsaved changes before archiving and aborts if keep editing is chosen', () => {
          component.quotation.set(mockQuotationDetail);
          component.reviewerNotes.set('Edited notes draft');
          fixture.detectChanges();
          expect(component.hasPendingReviewChanges()).toBeTrue();

          dialogSpy.open.calls.reset();
          dialogSpy.open.and.returnValue({
            afterClosed: () => of(false),
          } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
          const confirmSpy = spyOn(window, 'confirm');
          apiService.archiveQuotation.calls.reset();

          component.archiveQuotation();

          expect(dialogSpy.open).toHaveBeenCalledWith(
            CatalogueConfirmDialogComponent,
            jasmine.objectContaining({
              data: jasmine.objectContaining({
                titleKey: 'quotations.review.unsavedChanges.title',
                messageKey: 'quotations.review.unsavedChanges.message',
                confirmKey: 'quotations.review.unsavedChanges.confirm',
                cancelKey: 'quotations.review.unsavedChanges.cancel',
              }),
            }),
          );
          expect(confirmSpy).not.toHaveBeenCalled();
          expect(apiService.archiveQuotation).not.toHaveBeenCalled();
          expect(component.isArchiving()).toBeFalse();
        });

        it('confirms discard first, then archives and navigates without prompting again in canDeactivate', fakeAsync(() => {
          component.quotation.set(mockQuotationDetail);
          component.reviewerNotes.set('Edited notes draft');
          fixture.detectChanges();
          expect(component.hasPendingReviewChanges()).toBeTrue();

          dialogSpy.open.calls.reset();
          dialogSpy.open.and.returnValue({
            afterClosed: () => of(true),
          } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
          spyOn(window, 'confirm').and.returnValue(true);
          apiService.archiveQuotation.and.returnValue(of(mockQuotationDetail));
          const router = TestBed.inject(Router);
          spyOn(router, 'navigate');

          component.archiveQuotation();
          tick();

          expect(apiService.archiveQuotation).toHaveBeenCalledWith(mockQuotationDetail.id);
          expect(router.navigate).toHaveBeenCalledWith(['/quotations']);

          dialogSpy.open.calls.reset();
          const canLeave = component.canDeactivate();
          expect(canLeave).toBeTrue();
          expect(dialogSpy.open).not.toHaveBeenCalled();
        }));
      });

      describe('F3: In-flight save/confirm mutations treated as dirty', () => {
        it('prompts via confirm dialog when isSaving is in flight', (done) => {
          component.quotation.set(mockQuotationDetail);
          component.isSaving.set(true);
          fixture.detectChanges();

          dialogSpy.open.calls.reset();
          dialogSpy.open.and.returnValue({
            afterClosed: () => of(false),
          } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

          const result = component.canDeactivate();
          expect(dialogSpy.open).toHaveBeenCalled();
          if (typeof result === 'boolean') {
            fail('expected observable dialog result');
            done();
          } else {
            result.subscribe((allowed) => {
              expect(allowed).toBeFalse();
              done();
            });
          }
        });

        it('prompts via confirm dialog when isConfirming is in flight', (done) => {
          component.quotation.set(mockQuotationDetail);
          component.isConfirming.set(true);
          fixture.detectChanges();

          dialogSpy.open.calls.reset();
          dialogSpy.open.and.returnValue({
            afterClosed: () => of(false),
          } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

          const result = component.canDeactivate();
          expect(dialogSpy.open).toHaveBeenCalled();
          if (typeof result === 'boolean') {
            fail('expected observable dialog result');
            done();
          } else {
            result.subscribe((allowed) => {
              expect(allowed).toBeFalse();
              done();
            });
          }
        });

        it('prevents beforeunload when isSaving or isConfirming is in flight', () => {
          component.quotation.set(mockQuotationDetail);
          component.isSaving.set(true);
          fixture.detectChanges();

          const event = {
            preventDefault: jasmine.createSpy('preventDefault'),
            returnValue: undefined as unknown as string,
          } as unknown as BeforeUnloadEvent;

          component.onBeforeUnload(event);

          expect(event.preventDefault).toHaveBeenCalled();
          expect(event.returnValue).toBe('');
        });
      });

      describe('F4: Silent reload after extraction preserves user edits', () => {
        it('preserves user-edited notes and supplier during silent reload after extraction completes', fakeAsync(() => {
          const extractingQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-review-1',
            status: 'extracting',
            reviewer_notes: 'Initial notes',
            supplier_id: 'sup-1',
          };
          component.quotation.set(extractingQuote);
          component.reviewerNotes.set('User updated notes while extracting');
          component.selectedSupplierId.set('sup-2');
          fixture.detectChanges();

          const finishedQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-review-1',
            status: 'extracted',
            reviewer_notes: 'Initial notes',
            supplier_id: 'sup-1',
          };
          apiService.getQuotation.calls.reset();
          apiService.getQuotation.and.returnValue(of(finishedQuote));

          component.loadQuotation('q-review-1', { silent: true });
          fixture.detectChanges();
          tick();

          expect(component.reviewerNotes()).toBe('User updated notes while extracting');
          expect(component.selectedSupplierId()).toBe('sup-2');
          expect(component.quotation()?.status).toBe('extracted');
        }));

        it('updates notes and supplier on silent reload if user did not edit them', fakeAsync(() => {
          const extractingQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-review-1',
            status: 'extracting',
            reviewer_notes: '',
            supplier_id: null,
          };
          component.quotation.set(extractingQuote);
          component.reviewerNotes.set('');
          component.selectedSupplierId.set(null);
          fixture.detectChanges();

          const finishedQuote: QuotationDetail = {
            ...mockQuotationDetail,
            id: 'q-review-1',
            status: 'extracted',
            reviewer_notes: '',
            supplier_id: 'sup-extracted',
          };
          apiService.getQuotation.calls.reset();
          apiService.getQuotation.and.returnValue(of(finishedQuote));

          component.loadQuotation('q-review-1', { silent: true });
          fixture.detectChanges();
          tick();

          expect(component.selectedSupplierId()).toBe('sup-extracted');
        }));
      });
    });
  });

  describe('PPS-158 / P-126 Supplier corrections and picker', () => {
    it('(1) supplier-only change enables Save button and persists supplier_id in review patch', () => {
      component.quotation.set({
        ...mockQuotationDetail,
        supplier_id: 'sup-1',
      });
      component.selectedSupplierId.set('sup-1');
      fixture.detectChanges();

      // Initially, quotation has supplier_id 'sup-1', matches selectedSupplierId
      expect(component.quotation()?.supplier_id).toBe('sup-1');
      expect(component.selectedSupplierId()).toBe('sup-1');
      expect(component.hasPendingReviewChanges()).toBeFalse();

      const saveBtn = fixture.nativeElement.querySelector('.save-btn') as HTMLButtonElement;
      expect(saveBtn.disabled).toBeTrue();

      // Change only the supplier to 'sup-2'
      component.selectedSupplierId.set('sup-2');
      fixture.detectChanges();

      expect(component.hasPendingReviewChanges()).toBeTrue();
      expect(saveBtn.disabled).toBeFalse();

      // Calling saveCorrections sends review patch containing supplier_id 'sup-2'
      apiService.patchQuotation.and.returnValue(
        of({
          ...mockQuotationDetail,
          supplier_id: 'sup-2',
        }),
      );

      component.saveCorrections();
      expect(apiService.patchQuotation).toHaveBeenCalledWith(
        'q-review-1',
        jasmine.objectContaining({
          supplier_id: 'sup-2',
        }),
      );

      fixture.detectChanges();
      // After save succeeds, hasPendingReviewChanges is reset to false
      expect(component.hasPendingReviewChanges()).toBeFalse();
      expect(saveBtn.disabled).toBeTrue();
    });

    it('(2) supplier picker follows next cursors until all pages are loaded', () => {
      const page1 = [
        { id: 'sup-1', name: 'Alpha Ltd', status: 'active' as const, created_at: '2026-08-01T00:00:00Z' },
      ];
      const page2 = [
        { id: 'sup-2', name: 'Beta Ltd', status: 'active' as const, created_at: '2026-08-02T00:00:00Z' },
      ];

      apiService.suppliers.and.callFake((params?: { cursor?: string; limit?: number }) => {
        if (!params?.cursor) {
          return of({ items: page1, next_cursor: 'cursor-page-2' });
        }
        if (params.cursor === 'cursor-page-2') {
          return of({ items: page2, next_cursor: null });
        }
        return of({ items: [], next_cursor: null });
      });

      component.loadSuppliers();

      expect(apiService.suppliers).toHaveBeenCalledWith(jasmine.objectContaining({ limit: 100 }));
      expect(apiService.suppliers).toHaveBeenCalledWith(jasmine.objectContaining({ cursor: 'cursor-page-2' }));
      expect(component.suppliers().length).toBe(2);
      expect(component.suppliers().map((s) => s.id)).toEqual(['sup-1', 'sup-2']);
    });

    it('(3) supplier picker shows distinct error state with retry on failure, not empty-list message', () => {
      apiService.suppliers.and.returnValue(throwError(() => new Error('API failure')));

      component.loadSuppliers();
      fixture.detectChanges();

      const errorState = fixture.nativeElement.querySelector('.supplier-error-state');
      const emptyState = fixture.nativeElement.querySelector('.supplier-empty-state');

      expect(errorState).toBeTruthy();
      expect(emptyState).toBeFalsy();

      // Retry button calls loadSuppliers again
      apiService.suppliers.and.returnValue(
        of({
          items: [{ id: 'sup-1', name: 'Dairy Direct', status: 'active' as const, created_at: '2026-08-01T00:00:00Z' }],
          next_cursor: null,
        }),
      );

      const retryBtn = errorState.querySelector('button') as HTMLButtonElement;
      retryBtn.click();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.supplier-error-state')).toBeFalsy();
      expect(component.suppliers().length).toBe(1);
    });

    it('(4) supplier picker is searchable and filters client-side', () => {
      component.suppliers.set([
        { id: 'sup-1', name: 'Dairy Direct Ltd', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-2', name: 'Bakery Best', status: 'active', created_at: '2026-08-02T00:00:00Z' },
      ]);
      fixture.detectChanges();

      const comp = component as unknown as {
        filteredSuppliers?: () => Supplier[];
        setSupplierSearch?: (q: string) => void;
      };
      expect(comp.filteredSuppliers?.().length).toBe(2);

      comp.setSupplierSearch?.('bakery');
      fixture.detectChanges();

      expect(comp.filteredSuppliers?.().length).toBe(1);
      expect(comp.filteredSuppliers?.()[0].name).toBe('Bakery Best');
    });

    it('(5) typing, space and arrows inside search input stop propagation and do not close or change select', () => {
      component.quotation.set({
        ...mockQuotationDetail,
        supplier_id: null,
      });
      component.suppliers.set([
        { id: 'sup-1', name: 'Dairy Direct Ltd', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        { id: 'sup-2', name: 'Bakery Best', status: 'active', created_at: '2026-08-02T00:00:00Z' },
      ]);
      fixture.detectChanges();

      const selectDebug = fixture.debugElement.query(By.css('#supplier-select'));
      expect(selectDebug).toBeTruthy();
      const matSelect = selectDebug.componentInstance;
      matSelect.open();
      fixture.detectChanges();

      expect(matSelect.panelOpen).toBeTrue();

      const searchInput = (document.querySelector('[data-testid="supplier-search-input"]') ||
        fixture.nativeElement.querySelector('[data-testid="supplier-search-input"]')) as HTMLInputElement;
      expect(searchInput).toBeTruthy();

      // Space, arrows, and normal characters must stop propagation and leave panel open & select unchanged
      const testKeys = [' ', 'ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'a'];
      for (const key of testKeys) {
        const keyEvent = new KeyboardEvent('keydown', {
          key,
          bubbles: true,
          cancelable: true,
        });
        spyOn(keyEvent, 'stopPropagation').and.callThrough();
        searchInput.dispatchEvent(keyEvent);

        expect(keyEvent.stopPropagation).toHaveBeenCalled();
        expect(matSelect.panelOpen).toBeTrue();
        expect(component.selectedSupplierId()).toBeNull();
      }

      // Typing in input updates filter query without selecting or closing
      searchInput.value = 'Bakery';
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      fixture.detectChanges();

      expect(component.supplierSearchQuery()).toBe('Bakery');
      expect(matSelect.panelOpen).toBeTrue();
      expect(component.selectedSupplierId()).toBeNull();

      matSelect.close();
      fixture.detectChanges();
    });
  });
});
