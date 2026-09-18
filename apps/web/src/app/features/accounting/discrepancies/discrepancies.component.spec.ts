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
import type {
  ReconciliationDiscrepancy,
  ReconciliationDiscrepancyList,
} from '../accounting-api';
import { DiscrepanciesComponent } from './discrepancies.component';

describe('DiscrepanciesComponent (T031)', () => {
  let component: DiscrepanciesComponent;
  let fixture: ComponentFixture<DiscrepanciesComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: WritableSignal<Role | null>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockOpenDiscrepancies: ReconciliationDiscrepancy[] = [
    {
      id: 'disc-001',
      discrepancy_type: 'amount_mismatch',
      synced_bill_id: 'bill-001',
      purchase_record_id: 'pr-001',
      status: 'open',
      detected_at: '2026-09-18T10:00:00Z',
      resolved_by: null,
      resolved_at: null,
      resolution_note: null,
      synced_bill_detail: {
        vendor_name: 'Acme Supplies',
        amount: '1250.00',
        currency: 'USD',
        bill_date: '2026-09-10',
      },
      purchase_record_detail: {
        supplier_name: 'Acme Supplies Inc',
        amount: '1200.00',
        currency: 'EUR',
        date: '2026-09-11',
      },
    },
    {
      id: 'disc-002',
      discrepancy_type: 'unmatched_bill',
      synced_bill_id: 'bill-002',
      purchase_record_id: null,
      status: 'open',
      detected_at: '2026-09-18T10:30:00Z',
      resolved_by: null,
      resolved_at: null,
      resolution_note: null,
      synced_bill_detail: {
        vendor_name: 'Beta Cloud Services',
        amount: '450.00',
        currency: 'USD',
        bill_date: '2026-09-12',
      },
      purchase_record_detail: null,
    },
    {
      id: 'disc-003',
      discrepancy_type: 'unmatched_purchase',
      synced_bill_id: null,
      purchase_record_id: 'pr-003',
      status: 'open',
      detected_at: '2026-09-18T11:00:00Z',
      resolved_by: null,
      resolved_at: null,
      resolution_note: null,
      synced_bill_detail: null,
      purchase_record_detail: {
        supplier_name: 'Gamma Hardware',
        amount: '980.00',
        currency: 'USD',
        date: '2026-08-15',
      },
    },
  ];

  const mockResolvedDiscrepancies: ReconciliationDiscrepancy[] = [
    {
      id: 'disc-004',
      discrepancy_type: 'amount_mismatch',
      synced_bill_id: 'bill-004',
      purchase_record_id: 'pr-004',
      status: 'resolved',
      detected_at: '2026-09-17T09:00:00Z',
      resolved_by: 'User Alpha',
      resolved_at: '2026-09-17T15:00:00Z',
      resolution_note: 'Difference accepted due to shipping fees',
      synced_bill_detail: {
        vendor_name: 'Delta Shipping',
        amount: '310.00',
        currency: 'USD',
        bill_date: '2026-09-14',
      },
      purchase_record_detail: {
        supplier_name: 'Delta Shipping',
        amount: '300.00',
        currency: 'USD',
        date: '2026-09-14',
      },
    },
    {
      id: 'disc-005',
      discrepancy_type: 'unmatched_bill',
      synced_bill_id: 'bill-005',
      purchase_record_id: null,
      status: 'resolved',
      detected_at: '2026-09-16T08:00:00Z',
      resolved_by: null, // System-resolved
      resolved_at: '2026-09-17T08:00:00Z',
      resolution_note: null,
      synced_bill_detail: {
        vendor_name: 'Epsilon Tech',
        amount: '75.00',
        currency: 'USD',
        bill_date: '2026-09-13',
      },
      purchase_record_detail: null,
    },
  ];

  const mockInitialOpenResponse: ReconciliationDiscrepancyList = {
    items: mockOpenDiscrepancies,
    next_cursor: 'cur-page-2',
  };

  const mockMoreOpenResponse: ReconciliationDiscrepancyList = {
    items: [
      {
        id: 'disc-006',
        discrepancy_type: 'unmatched_purchase',
        synced_bill_id: null,
        purchase_record_id: 'pr-006',
        status: 'open',
        detected_at: '2026-09-18T12:00:00Z',
        resolved_by: null,
        resolved_at: null,
        resolution_note: null,
        synced_bill_detail: null,
        purchase_record_detail: {
          supplier_name: 'Zeta Office Supplies',
          amount: '120.00',
          currency: 'USD',
          date: '2026-08-10',
        },
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
      imports: [DiscrepanciesComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
      ],
    })
      .overrideComponent(DiscrepanciesComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      common: { loading: 'Loading...' },
      accounting: {
        discrepancies: {
          title: 'Reconciliation Discrepancies',
          subtitle: 'Review and resolve reconciliation discrepancies between synced bills and purchase records.',
          backToConnection: 'Connection Settings',
          refresh: 'Refresh',
          filters: {
            status: 'Filter by Status',
            open: 'Open',
            resolved: 'Resolved',
          },
          types: {
            amount_mismatch: 'Amount Mismatch',
            unmatched_bill: 'Unmatched Bill',
            unmatched_purchase: 'Unmatched Purchase Record',
          },
          table: {
            type: 'Type',
            details: 'Details',
            detectedAt: 'Detected',
            status: 'Status',
            actions: 'Actions',
          },
          details: {
            syncedBill: 'Synced Bill',
            purchaseRecord: 'Purchase Record',
            vendor: 'Vendor',
            supplier: 'Supplier',
            amount: 'Amount',
            date: 'Date',
          },
          status: {
            open: 'Open',
            resolved: 'Resolved',
          },
          resolution: {
            title: 'Resolution Info',
            resolvedBy: 'Resolved by: {{name}}',
            automaticallyResolved: 'Automatically resolved',
            resolvedAt: 'Resolved on {{date}}',
            note: 'Note: {{note}}',
          },
          resolveDialog: {
            title: 'Resolve Discrepancy',
            noteLabel: 'Resolution Note (Optional)',
            notePlaceholder: 'Reason for resolving this discrepancy...',
            cancel: 'Cancel',
            confirm: 'Resolve',
          },
          resolveAction: 'Resolve',
          empty: {
            title: 'No discrepancies found',
            description: 'No reconciliation discrepancies match the current filter.',
          },
          error: {
            title: 'Failed to load discrepancies',
            retry: 'Retry',
          },
          loadError: 'Failed to load discrepancies. Please try again.',
          resolveSuccess: 'Discrepancy resolved successfully.',
          resolveAlreadyResolved: 'This discrepancy was already resolved by someone else. Please refresh.',
          resolveFailed: 'Failed to resolve discrepancy. Please try again.',
          pagination: {
            loadMore: 'Load more',
            loadingMore: 'Loading more...',
            noMore: 'All discrepancies loaded',
          },
        },
      },
    });
    translate.use('en');

    fixture = TestBed.createComponent(DiscrepanciesComponent);
    component = fixture.componentInstance;
    httpTestingController = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should load open discrepancies on initial load by default', () => {
    fixture.detectChanges();

    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    expect(component.discrepancies().length).toBe(3);
    expect(component.statusFilter()).toBe('open');

    const rows = fixture.debugElement.queryAll(By.css('[data-testid="discrepancy-row"]'));
    expect(rows.length).toBe(3);
  });

  it('should switch status filter and load resolved discrepancies', () => {
    fixture.detectChanges();
    const req1 = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req1.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    component.onStatusFilterChange('resolved');
    fixture.detectChanges();

    const req2 = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=resolved',
    );
    expect(req2.request.method).toBe('GET');
    req2.flush({
      items: mockResolvedDiscrepancies,
      next_cursor: null,
    });
    fixture.detectChanges();

    expect(component.discrepancies().length).toBe(2);
    expect(component.statusFilter()).toBe('resolved');
  });

  it('should render amount_mismatch detail with side-by-side comparison and explicit currencies', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    const mismatchDetail = fixture.debugElement.query(
      By.css('[data-testid="amount-mismatch-detail"]'),
    );
    expect(mismatchDetail).toBeTruthy();

    const billVendor = mismatchDetail.query(By.css('[data-testid="bill-vendor"]'));
    const billAmount = mismatchDetail.query(By.css('[data-testid="bill-amount"]'));
    const purchaseSupplier = mismatchDetail.query(By.css('[data-testid="purchase-supplier"]'));
    const purchaseAmount = mismatchDetail.query(By.css('[data-testid="purchase-amount"]'));

    expect(billVendor.nativeElement.textContent).toContain('Acme Supplies');
    expect(billAmount.nativeElement.textContent).toContain('1,250.00');
    expect(purchaseSupplier.nativeElement.textContent).toContain('Acme Supplies Inc');
    expect(purchaseAmount.nativeElement.textContent).toContain('1,200.00');
  });

  it('should render unmatched_bill detail with vendor, amount, and date', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    const unmatchedBill = fixture.debugElement.query(
      By.css('[data-testid="unmatched-bill-detail"]'),
    );
    expect(unmatchedBill).toBeTruthy();

    const vendor = unmatchedBill.query(By.css('[data-testid="unmatched-bill-vendor"]'));
    const amount = unmatchedBill.query(By.css('[data-testid="unmatched-bill-amount"]'));
    const date = unmatchedBill.query(By.css('[data-testid="unmatched-bill-date"]'));

    expect(vendor.nativeElement.textContent).toContain('Beta Cloud Services');
    expect(amount.nativeElement.textContent).toContain('450.00');
    expect(date).toBeTruthy();
  });

  it('should render unmatched_purchase detail with supplier, amount, and date', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    const unmatchedPurchase = fixture.debugElement.query(
      By.css('[data-testid="unmatched-purchase-detail"]'),
    );
    expect(unmatchedPurchase).toBeTruthy();

    const supplier = unmatchedPurchase.query(By.css('[data-testid="unmatched-purchase-supplier"]'));
    const amount = unmatchedPurchase.query(By.css('[data-testid="unmatched-purchase-amount"]'));
    const date = unmatchedPurchase.query(By.css('[data-testid="unmatched-purchase-date"]'));

    expect(supplier.nativeElement.textContent).toContain('Gamma Hardware');
    expect(amount.nativeElement.textContent).toContain('980.00');
    expect(date).toBeTruthy();
  });

  it('should remove row and show success snackbar on successful resolve', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    const resolveBtn = fixture.debugElement.query(By.css('[data-testid="resolve-btn"]'));
    resolveBtn.nativeElement.click();
    fixture.detectChanges();

    const form = fixture.debugElement.query(By.css('[data-testid="inline-resolve-form"]'));
    expect(form).toBeTruthy();

    component.resolutionNote.set('Approved exception');
    fixture.detectChanges();

    const confirmBtn = fixture.debugElement.query(By.css('[data-testid="confirm-resolve-btn"]'));
    confirmBtn.nativeElement.click();
    fixture.detectChanges();

    const resolveReq = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies/disc-001/resolve',
    );
    expect(resolveReq.request.method).toBe('POST');
    expect(resolveReq.request.body).toEqual({ note: 'Approved exception' });
    resolveReq.flush({
      ...mockOpenDiscrepancies[0],
      status: 'resolved',
      resolved_by: 'User Owner',
      resolved_at: '2026-09-18T12:30:00Z',
      resolution_note: 'Approved exception',
    });
    fixture.detectChanges();

    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Discrepancy resolved successfully.',
      undefined,
      { duration: 4000 },
    );
    expect(component.discrepancies().length).toBe(2);
    expect(component.discrepancies().find((d) => d.id === 'disc-001')).toBeUndefined();
  });

  it('should show already resolved message on 409 error during resolve', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    component.startResolve(mockOpenDiscrepancies[0]);
    component.confirmResolve(mockOpenDiscrepancies[0]);
    fixture.detectChanges();

    const resolveReq = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies/disc-001/resolve',
    );
    resolveReq.flush(
      { code: 'ALREADY_RESOLVED', message: 'Already resolved', trace_id: 't-1' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'This discrepancy was already resolved by someone else. Please refresh.',
      undefined,
      { duration: 4000 },
    );
  });

  it('should show generic error message on unexpected error during resolve', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    component.startResolve(mockOpenDiscrepancies[0]);
    component.confirmResolve(mockOpenDiscrepancies[0]);
    fixture.detectChanges();

    const resolveReq = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies/disc-001/resolve',
    );
    resolveReq.flush(
      { code: 'INTERNAL_ERROR', message: 'Server error', trace_id: 't-2' },
      { status: 500, statusText: 'Internal Server Error' },
    );
    fixture.detectChanges();

    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Failed to resolve discrepancy. Please try again.',
      undefined,
      { duration: 4000 },
    );
  });

  it('should append items when clicking load more button', () => {
    fixture.detectChanges();
    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=open',
    );
    req.flush(mockInitialOpenResponse);
    fixture.detectChanges();

    expect(component.discrepancies().length).toBe(3);
    const loadMoreBtn = fixture.debugElement.query(By.css('[data-testid="load-more-btn"]'));
    expect(loadMoreBtn).toBeTruthy();

    loadMoreBtn.nativeElement.click();
    fixture.detectChanges();

    const moreReq = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?cursor=cur-page-2&limit=50&status=open',
    );
    moreReq.flush(mockMoreOpenResponse);
    fixture.detectChanges();

    expect(component.discrepancies().length).toBe(4);
    expect(component.nextCursor()).toBeNull();
  });

  it('should render system-resolved indicator instead of a blank when resolved_by is null', () => {
    component.statusFilter.set('resolved');
    fixture.detectChanges();

    const req = httpTestingController.expectOne(
      '/api/v1/accounting/discrepancies?limit=50&status=resolved',
    );
    req.flush({
      items: [mockResolvedDiscrepancies[1]], // resolved_by: null
      next_cursor: null,
    });
    fixture.detectChanges();

    const systemIndicator = fixture.debugElement.query(
      By.css('[data-testid="system-resolved-indicator"]'),
    );
    expect(systemIndicator).toBeTruthy();
    expect(systemIndicator.nativeElement.textContent).toContain('Automatically resolved');
  });
});
