import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import type { IngestionEmailLog, IngestionEmailLogList } from '../ingestion-api';
import { EmailLogComponent } from './email-log.component';

describe('EmailLogComponent', () => {
  let component: EmailLogComponent;
  let fixture: ComponentFixture<EmailLogComponent>;
  let httpTestingController: HttpTestingController;

  const mockLogs: IngestionEmailLog[] = [
    {
      id: 'log-001',
      message_id: '<msg-001@acme.com>',
      from_address: 'orders@acme.com',
      from_domain: 'acme.com',
      subject: 'Quotation for Office Supplies',
      received_at: '2026-09-17T08:30:00Z',
      processed_at: '2026-09-17T08:30:15Z',
      status: 'completed',
      error_message: null,
      attachment_count: 2,
      quotation_id: 'quot-101',
      supplier_id: 'supp-201',
      match_method: 'domain',
      created_at: '2026-09-17T08:30:00Z',
    },
    {
      id: 'log-002',
      message_id: '<msg-002@unknown-vendor.net>',
      from_address: 'pricing@unknown-vendor.net',
      from_domain: 'unknown-vendor.net',
      subject: null,
      received_at: '2026-09-17T07:15:00Z',
      processed_at: '2026-09-17T07:15:05Z',
      status: 'failed',
      error_message: 'Corrupt PDF attachment could not be parsed',
      attachment_count: 1,
      quotation_id: null,
      supplier_id: null,
      match_method: null,
      created_at: '2026-09-17T07:15:00Z',
    },
    {
      id: 'log-003',
      message_id: '<msg-003@partner.org>',
      from_address: 'support@partner.org',
      from_domain: 'partner.org',
      subject: 'Inquiry response',
      received_at: '2026-09-17T06:00:00Z',
      processed_at: null,
      status: 'processing',
      error_message: null,
      attachment_count: 0,
      quotation_id: null,
      supplier_id: 'supp-303',
      match_method: 'address',
      created_at: '2026-09-17T06:00:00Z',
    },
    {
      id: 'log-004',
      message_id: '<msg-004@supplier.io>',
      from_address: 'sales@supplier.io',
      from_domain: 'supplier.io',
      subject: 'Duplicate quotation notice',
      received_at: '2026-09-16T14:00:00Z',
      processed_at: '2026-09-16T14:00:02Z',
      status: 'duplicate',
      error_message: null,
      attachment_count: 1,
      quotation_id: null,
      supplier_id: 'supp-404',
      match_method: 'thread',
      created_at: '2026-09-16T14:00:00Z',
    },
    {
      id: 'log-005',
      message_id: '<msg-005@spammer.org>',
      from_address: 'promo@spammer.org',
      from_domain: 'spammer.org',
      subject: 'Unsolicited advertising',
      received_at: '2026-09-16T12:00:00Z',
      processed_at: '2026-09-16T12:00:01Z',
      status: 'rejected',
      error_message: 'Sender domain not in allowlist',
      attachment_count: 0,
      quotation_id: null,
      supplier_id: null,
      match_method: null,
      created_at: '2026-09-16T12:00:00Z',
    },
    {
      id: 'log-006',
      message_id: '<msg-006@newlead.com>',
      from_address: 'info@newlead.com',
      from_domain: 'newlead.com',
      subject: 'New quotation ready',
      received_at: '2026-09-16T10:00:00Z',
      processed_at: null,
      status: 'received',
      error_message: null,
      attachment_count: 1,
      quotation_id: null,
      supplier_id: null,
      match_method: null,
      created_at: '2026-09-16T10:00:00Z',
    },
  ];

  const mockInitialResponse: IngestionEmailLogList = {
    items: mockLogs,
    next_cursor: 'cursor-page-2',
  };

  const mockSecondPage: IngestionEmailLogList = {
    items: [
      {
        id: 'log-007',
        message_id: '<msg-007@extra.com>',
        from_address: 'billing@extra.com',
        from_domain: 'extra.com',
        subject: 'Additional invoice',
        received_at: '2026-09-15T09:00:00Z',
        processed_at: '2026-09-15T09:00:10Z',
        status: 'completed',
        error_message: null,
        attachment_count: 1,
        quotation_id: 'quot-107',
        supplier_id: 'supp-201',
        match_method: 'manual',
        created_at: '2026-09-15T09:00:00Z',
      },
    ],
    next_cursor: null,
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EmailLogComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
      ],
    }).compileComponents();

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(EmailLogComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  describe('initial load', () => {
    it('should request email logs with limit=50 and render rows on success', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      expect(req.request.method).toBe('GET');
      req.flush(mockInitialResponse);

      expect(component.isLoading()).toBeFalse();
      expect(component.logs().length).toBe(6);
      expect(component.nextCursor()).toBe('cursor-page-2');

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const rows = compiled.querySelectorAll('tr.mat-mdc-row');
      expect(rows.length).toBe(6);
    });

    it('should show error banner when initial load fails', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush({ message: 'Internal server error' }, { status: 500, statusText: 'Server Error' });

      expect(component.isLoading()).toBeFalse();
      expect(component.errorMessage()).toBeTruthy();

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const errorBanner = compiled.querySelector('.error-banner');
      expect(errorBanner).toBeTruthy();
    });

    it('should retry loading when retry button is clicked', () => {
      fixture.detectChanges();

      const req1 = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req1.flush({}, { status: 500, statusText: 'Server Error' });

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const retryBtn = compiled.querySelector('.retry-btn') as HTMLButtonElement;
      expect(retryBtn).toBeTruthy();

      retryBtn.click();

      const req2 = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req2.flush(mockInitialResponse);

      expect(component.errorMessage()).toBeNull();
      expect(component.logs().length).toBe(6);
    });
  });

  describe('pagination (load more)', () => {
    it('should append new items to the existing list rather than replacing them', () => {
      fixture.detectChanges();

      const req1 = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req1.flush(mockInitialResponse);

      expect(component.logs().length).toBe(6);
      expect(component.nextCursor()).toBe('cursor-page-2');

      component.loadMore();
      expect(component.isLoadingMore()).toBeTrue();

      const req2 = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?cursor=cursor-page-2&limit=50'
      );
      expect(req2.request.method).toBe('GET');
      req2.flush(mockSecondPage);

      expect(component.isLoadingMore()).toBeFalse();
      expect(component.logs().length).toBe(7);
      expect(component.nextCursor()).toBeNull();
      expect(component.logs()[6].id).toBe('log-007');
    });

    it('should not call API if nextCursor is null', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush({ items: mockLogs, next_cursor: null });

      expect(component.nextCursor()).toBeNull();

      component.loadMore();
      httpTestingController.expectNone(
        (request) => request.url.includes('/api/v1/ingestion/emails') && request.params.has('cursor')
      );
      expect(component.logs().length).toBe(mockLogs.length);
    });

    it('should not call API if already loading more', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush(mockInitialResponse);

      component.loadMore();
      const moreReq = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?cursor=cursor-page-2&limit=50'
      );

      // Attempt second loadMore while first is still pending
      component.loadMore();
      httpTestingController.verify();

      moreReq.flush(mockSecondPage);
      expect(component.logs().length).toBe(7);
    });
  });

  describe('filtering', () => {
    beforeEach(() => {
      fixture.detectChanges();
      const initReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      initReq.flush(mockInitialResponse);
    });

    it('should filter by status independently', () => {
      component.statusFilter.set('completed');
      component.onFilterChange();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50&status=completed');
      expect(req.request.method).toBe('GET');
      req.flush({ items: [mockLogs[0]], next_cursor: null });

      expect(component.logs().length).toBe(1);
      expect(component.logs()[0].status).toBe('completed');
    });

    it('should filter by sender domain independently', () => {
      component.fromDomain.set('acme.com');
      component.onFilterChange();

      const req = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?limit=50&from_domain=acme.com'
      );
      expect(req.request.method).toBe('GET');
      req.flush({ items: [mockLogs[0]], next_cursor: null });

      expect(component.logs().length).toBe(1);
      expect(component.logs()[0].from_domain).toBe('acme.com');
    });

    it('should filter by date_from independently', () => {
      component.dateFrom.set('2026-09-17');
      component.onFilterChange();

      const req = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?limit=50&date_from=2026-09-17'
      );
      expect(req.request.method).toBe('GET');
      req.flush({ items: mockLogs.slice(0, 3), next_cursor: null });

      expect(component.logs().length).toBe(3);
    });

    it('should filter by date_to independently', () => {
      component.dateTo.set('2026-09-16');
      component.onFilterChange();

      const req = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?limit=50&date_to=2026-09-16'
      );
      expect(req.request.method).toBe('GET');
      req.flush({ items: mockLogs.slice(3), next_cursor: null });

      expect(component.logs().length).toBe(3);
    });

    it('should combine all filters into one request', () => {
      component.statusFilter.set('failed');
      component.fromDomain.set('unknown-vendor.net');
      component.dateFrom.set('2026-09-01');
      component.dateTo.set('2026-09-17');
      component.onFilterChange();

      const req = httpTestingController.expectOne(
        '/api/v1/ingestion/emails?limit=50&status=failed&from_domain=unknown-vendor.net&date_from=2026-09-01&date_to=2026-09-17'
      );
      expect(req.request.method).toBe('GET');
      req.flush({ items: [mockLogs[1]], next_cursor: null });

      expect(component.logs().length).toBe(1);
    });

    it('should reset all filters and reload logs', () => {
      component.statusFilter.set('failed');
      component.fromDomain.set('unknown-vendor.net');
      component.dateFrom.set('2026-09-01');
      component.dateTo.set('2026-09-17');

      expect(component.hasActiveFilters()).toBeTrue();

      component.resetFilters();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      expect(req.request.method).toBe('GET');
      req.flush(mockInitialResponse);

      expect(component.statusFilter()).toBe('all');
      expect(component.fromDomain()).toBe('');
      expect(component.dateFrom()).toBe('');
      expect(component.dateTo()).toBe('');
      expect(component.hasActiveFilters()).toBeFalse();
    });
  });

  describe('UI rendering', () => {
    it('should render distinct status badges for all six statuses', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush(mockInitialResponse);

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;

      const completedBadge = compiled.querySelector('.status-completed');
      expect(completedBadge).toBeTruthy();
      expect(completedBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('check_circle');

      const failedBadge = compiled.querySelector('.status-failed');
      expect(failedBadge).toBeTruthy();
      expect(failedBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('error');

      const processingBadge = compiled.querySelector('.status-processing');
      expect(processingBadge).toBeTruthy();
      expect(processingBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('hourglass_top');

      const duplicateBadge = compiled.querySelector('.status-duplicate');
      expect(duplicateBadge).toBeTruthy();
      expect(duplicateBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('content_copy');

      const rejectedBadge = compiled.querySelector('.status-rejected');
      expect(rejectedBadge).toBeTruthy();
      expect(rejectedBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('cancel');

      const receivedBadge = compiled.querySelector('.status-received');
      expect(receivedBadge).toBeTruthy();
      expect(receivedBadge?.querySelector('mat-icon')?.textContent?.trim()).toBe('inbox');
    });

    it('should render quotation link when quotation_id is present and fallback when absent', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush(mockInitialResponse);

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const rows = compiled.querySelectorAll('tr.mat-mdc-row');

      // First row has quotation_id: 'quot-101'
      const firstRowQuotation = rows[0].querySelector('.quotation-cell');
      const quoteLink = firstRowQuotation?.querySelector('a.quotation-link');
      expect(quoteLink).toBeTruthy();

      // Second row has quotation_id: null
      const secondRowQuotation = rows[1].querySelector('.quotation-cell');
      const noQuoteSpan = secondRowQuotation?.querySelector('.no-quotation');
      expect(noQuoteSpan).toBeTruthy();
      expect(secondRowQuotation?.querySelector('a.quotation-link')).toBeNull();
    });

    it('should render supplier info when supplier_id is present and unmatched when absent', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush(mockInitialResponse);

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const rows = compiled.querySelectorAll('tr.mat-mdc-row');

      // First row has supplier_id: 'supp-201' and match_method: 'domain'
      const firstRowSupplier = rows[0].querySelector('.supplier-cell');
      expect(firstRowSupplier?.querySelector('.supplier-id')).toBeTruthy();
      expect(firstRowSupplier?.querySelector('.match-method-chip')).toBeTruthy();

      // Second row has supplier_id: null
      const secondRowSupplier = rows[1].querySelector('.supplier-cell');
      expect(secondRowSupplier?.querySelector('.unmatched-supplier')).toBeTruthy();
      expect(secondRowSupplier?.querySelector('.match-method-chip')).toBeNull();
    });

    it('should render empty state when no email logs are returned', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=50');
      req.flush({ items: [], next_cursor: null });

      fixture.detectChanges();
      const compiled = fixture.nativeElement as HTMLElement;
      const emptyState = compiled.querySelector('.empty-state');
      expect(emptyState).toBeTruthy();
      expect(compiled.querySelector('.email-log-table')).toBeNull();
    });
  });
});
