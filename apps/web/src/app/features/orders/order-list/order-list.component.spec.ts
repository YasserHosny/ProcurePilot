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
        loadError: 'Load failed', open: 'Open', orderDate: 'Ordered {{date}}', createdDate: 'Created {{date}}', lineCount: '{{count}} line(s)',
        createButton: 'Create Order', fromApprovedRequest: 'From approved request', resultCount: '{{count}} orders', expectedDate: 'Expected {{date}}',
        fromApprovedRequestEmpty: 'No approved requests available.',
        status: { submitted: 'Submitted', draft: 'Draft' }, empty: { title: 'Empty', description: 'No orders' },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OrderListComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // The supplier filter loads its options on start; tests that do not care just let it empty.
    http.match((r) => r.url.includes('/suppliers')).forEach((r) => r.flush({ items: [], next_cursor: null }));
    http.verify();
  });

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

  it('renders supplier name and displays Created date for draft and Ordered date for submitted', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({
      next_cursor: null,
      items: [
        {
          id: 'order-draft',
          tenant_id: 'tenant-1',
          order_number: 'PO-DRAFT',
          supplier_id: 'supplier-1',
          supplier_name: 'الوفرة للمواد الغذائية',
          status: 'draft',
          order_date: '2026-10-28',
          expected_delivery_date: null,
          total: { amount: '120.00', currency: 'SAR' },
          tax: { amount: '0.00', currency: 'SAR' },
          source_kind: 'manual',
          source_reference: 'PO-DRAFT',
          source_hash: null,
          created_by: 'member-1',
          created_at: '2026-10-28T09:00:00Z',
          updated_at: '2026-10-28T09:00:00Z',
          lines: [],
        },
        {
          id: 'order-sub',
          tenant_id: 'tenant-1',
          order_number: 'PO-SUBMITTED',
          supplier_id: 'supplier-1',
          supplier_name: 'شركة الأغذية',
          status: 'submitted',
          order_date: '2026-10-25',
          expected_delivery_date: null,
          total: { amount: '200.00', currency: 'SAR' },
          tax: { amount: '0.00', currency: 'SAR' },
          source_kind: 'manual',
          source_reference: 'PO-SUBMITTED',
          source_hash: null,
          created_by: 'member-1',
          created_at: '2026-10-24T09:00:00Z',
          updated_at: '2026-10-25T09:00:00Z',
          lines: [],
        },
      ],
    });
    fixture.detectChanges();

    const suppliers = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="order-card-supplier"]',
    );
    expect(suppliers.length).toBe(2);
    expect(suppliers[0]?.textContent?.trim()).toBe('الوفرة للمواد الغذائية');
    expect(suppliers[0]?.getAttribute('dir')).toBe('auto');
    expect(suppliers[1]?.textContent?.trim()).toBe('شركة الأغذية');

    const cards = (fixture.nativeElement as HTMLElement).querySelectorAll('.order-row');
    expect(cards[0]?.querySelector('.order-date')?.textContent).toContain('Created');
    expect(cards[0]?.querySelector('.order-date')?.textContent).not.toContain('Ordered');
    expect(cards[1]?.querySelector('.order-date')?.textContent).toContain('Ordered');
  });
  const orderRow = (id: string, number: string) => ({
    id, tenant_id: 'tenant-1', order_number: number, supplier_id: 'supplier-1', supplier_name: 'Acme',
    status: 'submitted', order_date: '2026-09-20', expected_delivery_date: null,
    total: { amount: '120.00', currency: 'GBP' }, tax: { amount: '0.00', currency: 'GBP' },
    source_kind: 'manual', source_reference: number, source_hash: null, created_by: 'member-1',
    created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z', lines: [],
  });
  const el = (): HTMLElement => fixture.nativeElement as HTMLElement;

  // P-182: search, status, sort and a result count; the server does the work.
  it('searches, filters and sorts through the API and shows the result count', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: null, total_count: 14 });
    fixture.detectChanges();
    expect(el().querySelector('[data-testid="orders-result-count"]')?.textContent).toContain('14');

    const search = el().querySelector('[data-testid="orders-search"]') as HTMLInputElement;
    search.value = 'alpha';
    search.dispatchEvent(new Event('input'));
    (el().querySelector('[data-testid="orders-search-form"]') as HTMLFormElement)
      .dispatchEvent(new Event('submit'));
    http.expectOne('/api/v1/orders?limit=50&q=alpha').flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();

    const status = el().querySelector('[data-testid="orders-status-filter"]') as HTMLSelectElement;
    status.value = 'submitted';
    status.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&q=alpha&status=submitted')
      .flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();

    const sort = el().querySelector('[data-testid="orders-sort"]') as HTMLSelectElement;
    sort.value = 'total:asc';
    sort.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&q=alpha&status=submitted&sort=total&dir=asc')
      .flush({ items: [], next_cursor: null, total_count: 0 });
  });

  it('says when filters match nothing instead of showing the empty-workspace message', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: null, total_count: 1 });
    fixture.detectChanges();
    const status = el().querySelector('[data-testid="orders-status-filter"]') as HTMLSelectElement;
    status.value = 'cancelled';
    status.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&status=cancelled').flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();
    expect(el().querySelector('[data-testid="orders-no-match"]')).toBeTruthy();
  });

  // P-182: a failed «Load more» used to replace the rows already loaded with an error card.
  it('keeps the loaded orders and offers a retry when Load more fails', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: '50', total_count: 80 });
    fixture.detectChanges();

    component.loadMore();
    http.expectOne('/api/v1/orders?limit=50&cursor=50').flush({}, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();

    expect(el().querySelector('[data-testid="orders-list"]')?.textContent).toContain('PO-1');
    expect(el().querySelector('[data-testid="load-more-error"]')).toBeTruthy();
  });

  // P-182: an order created between two page loads shifts the offset and repeats a row.
  it('does not list an order twice when the next page repeats it', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1'), orderRow('o2', 'PO-2')], next_cursor: '2', total_count: 3 });
    component.loadMore();
    http.expectOne('/api/v1/orders?limit=50&cursor=2').flush({ items: [orderRow('o2', 'PO-2'), orderRow('o3', 'PO-3')], next_cursor: null, total_count: 3 });
    fixture.detectChanges();
    expect(component.orders().map((o) => o.id)).toEqual(['o1', 'o2', 'o3']);
  });

  // P-182: the approved-request menu named requests only by date and total.
  it('names the supplier and line count of each approved request in the picker', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null, total_count: 0 });
    (el().querySelector('[data-testid="order-from-approved-request-btn"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    http.expectOne('/api/v1/requests?limit=100&eligible_for_order=true').flush({
      next_cursor: null,
      items: [{
        id: 'req-1', branch_id: 'b1', requested_by_membership_id: 'm1', required_by_date: '2026-11-05',
        status: 'ordered', source: { supplier_name: 'Al Dhahabi' },
        approval_step: { id: 's', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'approved', decided_by_membership_id: 'm1', decided_at: '2026-10-01T00:00:00Z' },
        lines: [{ id: 'l1' }, { id: 'l2' }], estimated_total: { amount: '200', currency: 'SAR' },
        has_incomplete_estimate: false, created_at: '2026-10-01T00:00:00Z',
      }],
    });
    fixture.detectChanges();
    const option = document.querySelector('[data-testid="approved-request-option-req-1"]');
    expect(option?.textContent).toContain('Al Dhahabi');
    expect(option?.textContent).toContain('2');
  });
  // P-182 review: a late «Load more» answer must not land in a newer filter's result set.
  it('ignores a Load more response that arrives after the filter changed', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: '50', total_count: 80 });
    component.loadMore();
    const late = http.expectOne('/api/v1/orders?limit=50&cursor=50');

    const status = el().querySelector('[data-testid="orders-status-filter"]') as HTMLSelectElement;
    status.value = 'draft';
    status.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&status=draft').flush({ items: [orderRow('d1', 'PO-D1')], next_cursor: null, total_count: 1 });
    late.flush({ items: [orderRow('o2', 'PO-2')], next_cursor: '100', total_count: 80 });

    expect(component.orders().map((o) => o.id)).toEqual(['d1']);
    expect(component.nextCursor()).toBeNull();
    expect(component.totalCount()).toBe(1);
  });
  // Review (Codex, #419): Load more used the text typed after the page was loaded.
  it('pages with the search that was applied, not with text typed but not submitted', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: '50', total_count: 80 });
    fixture.detectChanges();

    const search = el().querySelector('[data-testid="orders-search"]') as HTMLInputElement;
    search.value = 'ALPHA';
    search.dispatchEvent(new Event('input')); // typed, never submitted
    component.loadMore();

    http.expectOne('/api/v1/orders?limit=50&cursor=50').flush({ items: [orderRow('o2', 'PO-2')], next_cursor: null, total_count: 80 });
    expect(component.orders().map((o) => o.id)).toEqual(['o1', 'o2']);
    expect(component.totalCount()).toBe(80);
  });
  // P-188: the list showed neither the expected delivery date nor which orders are late.
  it('shows the expected delivery date and flags only late open orders', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({
      next_cursor: null, total_count: 3,
      items: [
        { ...orderRow('late', 'PO-LATE'), expected_delivery_date: '2020-01-01' },
        { ...orderRow('done', 'PO-DONE'), expected_delivery_date: '2020-01-01', status: 'received' },
        { ...orderRow('soon', 'PO-SOON'), expected_delivery_date: '2999-01-01' },
      ],
    });
    fixture.detectChanges();

    const rows = Array.from(el().querySelectorAll('.order-row')) as HTMLElement[];
    const by = (n: string) => rows.find((r) => r.textContent?.includes(n))!;
    expect(by('PO-LATE').querySelector('[data-testid="order-overdue"]')).toBeTruthy();
    expect(by('PO-DONE').querySelector('[data-testid="order-overdue"]')).toBeNull();
    expect(by('PO-SOON').querySelector('[data-testid="order-overdue"]')).toBeNull();
    expect(by('PO-SOON').querySelector('[data-testid="order-expected"]')?.textContent).toContain('2999');
  });
  // PPS-206: the API filters by supplier and order date; the page now offers both.
  it('filters by supplier and by order date range through the API', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [orderRow('o1', 'PO-1')], next_cursor: null, total_count: 1 });
    http.expectOne((r) => r.url.includes('/suppliers')).flush({
      items: [{ id: 'sup-1', name: 'Al Dhahabi', status: 'active', created_at: '' }, { id: 'sup-2', name: 'Al Wafra', status: 'active', created_at: '' }],
      next_cursor: null,
    });
    fixture.detectChanges();

    const supplier = el().querySelector('[data-testid="orders-supplier-filter"]') as HTMLSelectElement;
    expect(Array.from(supplier.options).map((o) => o.textContent?.trim())).toContain('Al Wafra');
    supplier.value = 'sup-2';
    supplier.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&supplier_id=sup-2').flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();

    const from = el().querySelector('[data-testid="orders-date-from"]') as HTMLInputElement;
    from.value = '2026-10-01';
    from.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&supplier_id=sup-2&date_from=2026-10-01').flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();

    const to = el().querySelector('[data-testid="orders-date-to"]') as HTMLInputElement;
    to.value = '2026-10-31';
    to.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/orders?limit=50&supplier_id=sup-2&date_from=2026-10-01&date_to=2026-10-31')
      .flush({ items: [], next_cursor: null, total_count: 0 });
    fixture.detectChanges();
    expect(el().querySelector('[data-testid="orders-no-match"]')).toBeTruthy(); // a filter is active
  });
  // Review (Codex, #460): suppliers beyond the first page could never be chosen in the filter.
  it('follows the supplier cursors so every supplier can be filtered on', () => {
    fixture.detectChanges();
    http.expectOne('/api/v1/orders?limit=50').flush({ items: [], next_cursor: null, total_count: 0 });
    http.expectOne((r) => r.url.includes('/suppliers') && !r.url.includes('cursor')).flush({
      items: [{ id: 'sup-1', name: 'Al Dhahabi', status: 'active', created_at: '' }],
      next_cursor: 'page-2',
    });
    http.expectOne((r) => r.url.includes('/suppliers') && r.url.includes('cursor=page-2')).flush({
      items: [{ id: 'sup-2', name: 'Al Wafra', status: 'active', created_at: '' }],
      next_cursor: null,
    });

    expect(component.suppliers().map((s) => s.id)).toEqual(['sup-1', 'sup-2']);
  });
});
