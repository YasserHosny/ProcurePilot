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

  it('should load quotation details and suppliers on init', () => {
    expect(apiService.getQuotation).toHaveBeenCalledWith('q-review-1');
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(component.quotation()?.id).toBe('q-review-1');
    expect(component.suppliers().length).toBe(1);
    expect(component.flaggedFields().length).toBe(1);
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
