import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { type WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { SyncedBill, SyncedBillList } from '../accounting-api';
import { BillsComponent } from './bills.component';

describe('BillsComponent (T026)', () => {
  let component: BillsComponent;
  let fixture: ComponentFixture<BillsComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: WritableSignal<Role | null>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockBills: SyncedBill[] = [
    {
      id: 'bill-001',
      vendor_name: 'Acme Paper Co',
      matched_supplier_id: 'supp-001',
      amount: '1500.50',
      currency: 'USD',
      bill_date: '2026-09-10',
      provider_status: 'paid',
      matched: true,
      purchase_record_id: 'pr-12345',
    },
    {
      id: 'bill-002',
      vendor_name: 'Beta Hardware',
      matched_supplier_id: null,
      amount: '320.00',
      currency: 'USD',
      bill_date: '2026-09-12',
      provider_status: 'open',
      matched: false,
      purchase_record_id: null,
    },
    {
      id: 'bill-003',
      vendor_name: 'Gamma Services',
      matched_supplier_id: null,
      amount: '75.25',
      currency: 'EUR',
      bill_date: '2026-09-14',
      provider_status: 'void',
      matched: false,
      purchase_record_id: null,
    },
  ];

  const mockInitialResponse: SyncedBillList = {
    items: mockBills,
    next_cursor: 'cursor-page-2',
  };

  const mockSecondPageResponse: SyncedBillList = {
    items: [
      {
        id: 'bill-004',
        vendor_name: 'Delta Logistics',
        matched_supplier_id: 'supp-004',
        amount: '890.00',
        currency: 'USD',
        bill_date: '2026-09-15',
        provider_status: 'open',
        matched: true,
        purchase_record_id: 'pr-67890',
      },
    ],
    next_cursor: null,
  };

  beforeEach(async () => {
    mockRoleSignal = signal<Role | null>('owner');
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    const mockSessionService = {
      role: mockRoleSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = mockRoleSignal();
        return current !== null && roles.includes(current);
      },
      isAuthenticated: signal(true),
      activeLocale: signal('en'),
      currentMember: signal(null),
      tenant: signal(null),
    };

    await TestBed.configureTestingModule({
      imports: [BillsComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
      ],
    })
      .overrideComponent(BillsComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      common: { loading: 'Loading...' },
      accounting: {
        bills: {
          title: 'Synced Bills & Invoices',
          subtitle: 'View supplier bills imported from your accounting software and their purchase record matches.',
          backToConnection: 'Connection Settings',
          syncNow: 'Sync now',
          syncing: 'Syncing...',
          refresh: 'Refresh',
          filters: {
            matchStatus: 'Filter by Match Status',
            all: 'All',
            matched: 'Matched',
            unmatched: 'Unmatched',
          },
          table: {
            vendor: 'Supplier / Vendor',
            amount: 'Amount',
            date: 'Bill Date',
            providerStatus: 'Status',
            matchedStatus: 'Reconciliation',
          },
          providerStatus: {
            open: 'Open',
            paid: 'Paid',
            void: 'Void',
          },
          matched: 'Matched',
          unmatched: 'Unmatched',
          purchaseRecordId: 'Purchase Record: {{id}}',
          empty: {
            title: 'No synced bills found',
            description: 'No bills match the current filter.',
          },
          error: {
            title: 'Failed to load bills',
            retry: 'Retry',
          },
          loadError: 'Failed to load synced bills. Please try again.',
          syncSuccess: 'Sync enqueued. Bills will update shortly.',
          syncAlreadyRunning: 'A sync is already running. Please wait for it to complete.',
          syncNoConnection: 'Connect an accounting system first before syncing bills.',
          syncFailed: 'Failed to trigger sync. Please try again.',
          pagination: {
            loadMore: 'Load more',
            loadingMore: 'Loading more...',
            noMore: 'All bills loaded',
          },
        },
      },
    });
    translate.use('en');

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(BillsComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  describe('Initial load and render', () => {
    it('should call listBills() with limit=50 on init and render table with bills', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      expect(req.request.method).toBe('GET');
      req.flush(mockInitialResponse);

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.bills().length).toBe(3);
      expect(component.nextCursor()).toBe('cursor-page-2');

      const rows = fixture.debugElement.queryAll(By.css('[data-testid="bill-row"]'));
      expect(rows.length).toBe(3);

      // First bill: Acme Paper Co, $1500.50, matched with pr-12345
      const firstRow = rows[0];
      const vendorEl = firstRow.query(By.css('[data-testid="bill-vendor"]'));
      expect(vendorEl.nativeElement.textContent).toContain('Acme Paper Co');

      const amountEl = firstRow.query(By.css('[data-testid="bill-amount"]'));
      expect(amountEl.nativeElement.textContent).toContain('1,500.50');
      expect(amountEl.nativeElement.textContent).toContain('$');

      const dateEl = firstRow.query(By.css('[data-testid="bill-date"]'));
      expect(dateEl.nativeElement.textContent).toContain('2026');

      const statusEl = firstRow.query(By.css('[data-testid="bill-provider-status"]'));
      expect(statusEl.nativeElement.textContent).toContain('Paid');

      const matchedBadge = firstRow.query(By.css('[data-testid="match-badge-matched"]'));
      expect(matchedBadge).not.toBeNull();
      expect(matchedBadge.nativeElement.textContent).toContain('Matched');

      const purchaseRecordEl = firstRow.query(By.css('[data-testid="purchase-record-id"]'));
      expect(purchaseRecordEl).not.toBeNull();
      expect(purchaseRecordEl.nativeElement.textContent).toContain('pr-12345');

      // Second bill: Beta Hardware, unmatched
      const secondRow = rows[1];
      const unmatchedBadge = secondRow.query(By.css('[data-testid="match-badge-unmatched"]'));
      expect(unmatchedBadge).not.toBeNull();
      expect(unmatchedBadge.nativeElement.textContent).toContain('Unmatched');
    });

    it('should display empty state when no bills are returned', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      req.flush({ items: [], next_cursor: null });

      fixture.detectChanges();

      expect(component.bills().length).toBe(0);
      const emptyEl = fixture.debugElement.query(By.css('[data-testid="empty-state"]'));
      expect(emptyEl).not.toBeNull();
      expect(emptyEl.nativeElement.textContent).toContain('No synced bills found');
    });

    it('should show error banner when initial load fails and allow retry', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      req.flush({ message: 'Internal Server Error' }, { status: 500, statusText: 'Server Error' });

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.errorMessage()).not.toBeNull();

      const errorBanner = fixture.debugElement.query(By.css('[data-testid="error-banner"]'));
      expect(errorBanner).not.toBeNull();
      expect(snackBarSpy.open).toHaveBeenCalled();

      // Click retry
      const retryBtn = fixture.debugElement.query(By.css('[data-testid="retry-btn"]'));
      retryBtn.nativeElement.click();

      const retryReq = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      retryReq.flush(mockInitialResponse);

      fixture.detectChanges();
      expect(component.bills().length).toBe(3);
      expect(component.errorMessage()).toBeNull();
    });
  });

  describe('Filter changes', () => {
    beforeEach(() => {
      fixture.detectChanges();
      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      req.flush(mockInitialResponse);
      fixture.detectChanges();
    });

    it('should filter by matched when filter changes to "matched"', () => {
      component.onFilterChange('matched');

      const req = httpTestingController.expectOne(
        '/api/v1/accounting/bills?limit=50&match_status=matched',
      );
      expect(req.request.method).toBe('GET');
      req.flush({
        items: [mockBills[0]],
        next_cursor: null,
      });

      fixture.detectChanges();
      expect(component.matchStatusFilter()).toBe('matched');
      expect(component.bills().length).toBe(1);
      expect(component.bills()[0].matched).toBeTrue();
    });

    it('should filter by unmatched when filter changes to "unmatched"', () => {
      component.onFilterChange('unmatched');

      const req = httpTestingController.expectOne(
        '/api/v1/accounting/bills?limit=50&match_status=unmatched',
      );
      expect(req.request.method).toBe('GET');
      req.flush({
        items: [mockBills[1], mockBills[2]],
        next_cursor: null,
      });

      fixture.detectChanges();
      expect(component.matchStatusFilter()).toBe('unmatched');
      expect(component.bills().length).toBe(2);
      expect(component.bills().every((b) => !b.matched)).toBeTrue();
    });

    it('should request all bills without match_status when filter resets to "all"', () => {
      component.onFilterChange('matched');
      const req1 = httpTestingController.expectOne(
        '/api/v1/accounting/bills?limit=50&match_status=matched',
      );
      req1.flush({ items: [], next_cursor: null });

      component.onFilterChange('all');
      const req2 = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      expect(req2.request.urlWithParams).not.toContain('match_status');
      req2.flush(mockInitialResponse);

      expect(component.bills().length).toBe(3);
    });
  });

  describe('Load more pagination', () => {
    beforeEach(() => {
      fixture.detectChanges();
      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      req.flush(mockInitialResponse);
      fixture.detectChanges();
    });

    it('should show "Load more" button when next_cursor is present and append items on click', () => {
      const loadMoreBtn = fixture.debugElement.query(By.css('[data-testid="load-more-btn"]'));
      expect(loadMoreBtn).not.toBeNull();

      loadMoreBtn.nativeElement.click();

      const req = httpTestingController.expectOne(
        '/api/v1/accounting/bills?cursor=cursor-page-2&limit=50',
      );
      expect(req.request.method).toBe('GET');
      req.flush(mockSecondPageResponse);

      fixture.detectChanges();

      expect(component.bills().length).toBe(4);
      expect(component.nextCursor()).toBeNull();

      // "All bills loaded" text replaces load more button
      const loadMoreBtnAfter = fixture.debugElement.query(By.css('[data-testid="load-more-btn"]'));
      expect(loadMoreBtnAfter).toBeNull();
      const noMoreEl = fixture.debugElement.query(By.css('[data-testid="no-more-bills"]'));
      expect(noMoreEl).not.toBeNull();
      expect(noMoreEl.nativeElement.textContent).toContain('All bills loaded');
    });

    it('should preserve active match_status filter when loading more', () => {
      component.matchStatusFilter.set('matched');
      component.nextCursor.set('cur-matched-2');

      component.loadMore();

      const req = httpTestingController.expectOne(
        '/api/v1/accounting/bills?cursor=cur-matched-2&limit=50&match_status=matched',
      );
      expect(req.request.method).toBe('GET');
      req.flush(mockSecondPageResponse);
    });
  });

  describe('Sync now button', () => {
    beforeEach(() => {
      fixture.detectChanges();
      const req = httpTestingController.expectOne('/api/v1/accounting/bills?limit=50');
      req.flush(mockInitialResponse);
      fixture.detectChanges();
    });

    it('should trigger sync on click and show success snackbar', () => {
      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      expect(syncBtn).not.toBeNull();

      syncBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/accounting/sync');
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush({ status: 'enqueued' }, { status: 202, statusText: 'Accepted' });

      expect(component.isSyncing()).toBeFalse();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'Sync enqueued. Bills will update shortly.',
        undefined,
        { duration: 4000 },
      );
    });

    it('should show "a sync is already running" message on 409 conflict', () => {
      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      syncBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/accounting/sync');
      req.flush(
        { code: 'CONFLICT', message: 'Sync in progress', trace_id: 'tr-1' },
        { status: 409, statusText: 'Conflict' },
      );

      expect(component.isSyncing()).toBeFalse();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'A sync is already running. Please wait for it to complete.',
        undefined,
        { duration: 4000 },
      );
    });

    it('should show "connect an accounting system first" message on 404 not found', () => {
      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      syncBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/accounting/sync');
      req.flush(
        { code: 'NOT_FOUND', message: 'No connection', trace_id: 'tr-2' },
        { status: 404, statusText: 'Not Found' },
      );

      expect(component.isSyncing()).toBeFalse();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'Connect an accounting system first before syncing bills.',
        undefined,
        { duration: 4000 },
      );
    });

    it('should show generic error message on other errors (500)', () => {
      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      syncBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/accounting/sync');
      req.flush(
        { code: 'INTERNAL_ERROR', message: 'Server down', trace_id: 'tr-3' },
        { status: 500, statusText: 'Internal Server Error' },
      );

      expect(component.isSyncing()).toBeFalse();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'Failed to trigger sync. Please try again.',
        undefined,
        { duration: 4000 },
      );
    });

    it('should hide sync button for unauthorized roles (e.g. viewer)', () => {
      mockRoleSignal.set('viewer');
      fixture.detectChanges();

      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      expect(syncBtn).toBeNull();
    });

    it('should show sync button for buyer role', () => {
      mockRoleSignal.set('buyer');
      fixture.detectChanges();

      const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-now-btn"]'));
      expect(syncBtn).not.toBeNull();
    });
  });
});
