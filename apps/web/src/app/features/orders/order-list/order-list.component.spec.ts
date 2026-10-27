import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import { OrderListComponent } from './order-list.component';
import { SessionService } from '../../../core/auth/session.service';
import { signal, WritableSignal, computed, Signal } from '@angular/core';
import { Role } from '../../../core/api/models';

describe('OrderListComponent', () => {
  let fixture: ComponentFixture<OrderListComponent>;
  let component: OrderListComponent;
  let http: HttpTestingController;
  let mockRole: WritableSignal<Role | null>;
  let mockSession: Partial<SessionService>;

  beforeEach(async () => {
    mockRole = signal<Role | null>('owner');
    mockSession = {
      role: mockRole as unknown as Signal<Role | null>,
      isAuthenticated: computed(() => true),
      activeLocale: computed(() => 'en'),
    };

    await TestBed.configureTestingModule({
      imports: [OrderListComponent],
      providers: [
        provideTranslateService(),
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSession }
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      orders: {
        title: 'Order Tracking', subtitle: 'Orders', refresh: 'Refresh', retry: 'Retry', loadMore: 'Load more',
        loadError: 'Load failed', open: 'Open', orderDate: 'Ordered {{date}}', lineCount: '{{count}} line(s)',
        createButton: 'Create Order', fromApprovedRequest: 'From approved request',
        fromApprovedRequestEmpty: 'No approved requests available.',
        status: { submitted: 'Submitted' }, empty: { title: 'Empty', description: 'No orders' },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OrderListComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads and renders purchase orders with status and total', () => {
    fixture.detectChanges();
    const request = http.expectOne('/api/v1/orders?limit=50');
    request.flush({
      next_cursor: null,
      items: [{
        id: 'order-1', tenant_id: 'tenant-1', order_number: 'PO-1001', supplier_id: 'supplier-1',
        status: 'submitted', order_date: '2026-09-20', expected_delivery_date: null,
        total: { amount: '120.00', currency: 'GBP' }, tax: { amount: '0.00', currency: 'GBP' },
        source_kind: 'manual', source_reference: 'PO-1001', source_hash: null, created_by: 'member-1',
        created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z', lines: [],
      }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="orders-list"]').textContent).toContain('PO-1001');
    expect(fixture.nativeElement.textContent).toContain('Submitted');
    expect(fixture.nativeElement.textContent).toContain('GBP 120');
  });

  it('shows create button for owner and hides for viewer', () => {
    mockRole.set('owner');
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null });
    let btn = fixture.nativeElement.querySelector('[data-testid="order-create-btn"]');
    expect(btn).toBeTruthy();

    mockRole.set('viewer');
    fixture.detectChanges();
    btn = fixture.nativeElement.querySelector('[data-testid="order-create-btn"]');
    expect(btn).toBeNull();
  });

  it('loads approved requests into the picker and navigates to /orders/new?source_request_id=<id>', () => {
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null });

    const fromApprovedBtn = fixture.nativeElement.querySelector(
      '[data-testid="order-from-approved-request-btn"]',
    ) as HTMLButtonElement;
    expect(fromApprovedBtn).toBeTruthy();
    expect(fromApprovedBtn.textContent).toContain('From approved request');

    fromApprovedBtn.click();
    fixture.detectChanges();

    const approvedReqCall = http.expectOne('/api/v1/requests?limit=100&eligible_for_order=true');
    approvedReqCall.flush({
      next_cursor: null,
      items: [
        {
          id: 'req-approved-1',
          branch_id: 'b1',
          requested_by_membership_id: 'm1',
          required_by_date: '2026-09-20',
          status: 'ordered',
          approval_step: { id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'approved', decided_by_membership_id: 'm1', decided_at: '2026-10-01T00:00:00Z' },
          lines: [],
          estimated_total: { amount: '56425.0000', currency: 'EGP' },
          has_incomplete_estimate: false,
          created_at: '2026-10-01T00:00:00Z',
        },
        {
          id: 'req-pending-1',
          branch_id: 'b1',
          requested_by_membership_id: 'm1',
          required_by_date: '2026-10-25',
          status: 'submitted',
          approval_step: { id: 'step2', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'pending', decided_by_membership_id: null, decided_at: null },
          lines: [],
          estimated_total: null,
          has_incomplete_estimate: false,
          created_at: '2026-10-02T00:00:00Z',
        },
      ],
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.approvedRequests().length).toBe(1);
    expect(document.querySelector('[data-testid="approved-request-option-req-pending-1"]')).toBeNull();
    const option = document.querySelector(
      '[data-testid="approved-request-option-req-approved-1"]',
    ) as HTMLButtonElement | null;
    expect(option).toBeTruthy();
    expect(option?.textContent).toContain('Sep 20, 2026');
    expect(option?.textContent).toContain('EGP 56,425');

    option?.click();
    expect(router.navigate).toHaveBeenCalledWith(['/orders/new'], {
      queryParams: { source_request_id: 'req-approved-1' },
    });
  });

  it('shows empty state in From approved request picker when no approved requests exist', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null });

    const fromApprovedBtn = fixture.nativeElement.querySelector(
      '[data-testid="order-from-approved-request-btn"]',
    ) as HTMLButtonElement;
    fromApprovedBtn.click();
    fixture.detectChanges();

    http.expectOne('/api/v1/requests?limit=100&eligible_for_order=true').flush({ items: [], next_cursor: null });
    fixture.detectChanges();

    const emptyEl = document.querySelector('[data-testid="approved-requests-empty"]');
    expect(emptyEl).toBeTruthy();
    expect(emptyEl?.textContent).toContain('No approved requests available.');
  });

  it('formats required-by dates in approved request picker in en and ar', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null });

    const fromApprovedBtn = fixture.nativeElement.querySelector(
      '[data-testid="order-from-approved-request-btn"]',
    ) as HTMLButtonElement;
    fromApprovedBtn.click();
    fixture.detectChanges();

    http.expectOne('/api/v1/requests?limit=100&eligible_for_order=true').flush({
      next_cursor: null,
      items: [
        {
          id: 'req-approved-1',
          branch_id: 'b1',
          requested_by_membership_id: 'm1',
          required_by_date: '2026-09-20',
          status: 'ordered',
          approval_step: { id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'approved', decided_by_membership_id: 'm1', decided_at: '2026-10-01T00:00:00Z' },
          lines: [],
          estimated_total: { amount: '56425.0000', currency: 'EGP' },
          has_incomplete_estimate: false,
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
    });
    fixture.detectChanges();

    const option = document.querySelector(
      '[data-testid="approved-request-option-req-approved-1"]',
    ) as HTMLButtonElement | null;
    expect(option?.textContent).toContain('Sep 20, 2026');
    expect(component.formatRequiredBy('2026-09-20')).toBe('Sep 20, 2026');

    TestBed.inject(TranslateService).use('ar');
    fixture.detectChanges();

    const updatedOption = document.querySelector(
      '[data-testid="approved-request-option-req-approved-1"]',
    ) as HTMLButtonElement | null;
    expect(updatedOption?.textContent).toContain('٢٠');
    expect(updatedOption?.textContent).toContain('٢٠٢٦');
    expect(component.formatRequiredBy('2026-09-20')).toContain('٢٠');
    expect(/[0-9]/.test(component.formatRequiredBy('2026-09-20'))).toBeFalse();
  });
});
