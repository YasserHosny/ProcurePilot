import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { OrderListComponent } from './order-list.component';

describe('OrderListComponent', () => {
  let fixture: ComponentFixture<OrderListComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OrderListComponent, TranslateModule.forRoot()],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations(), provideRouter([])],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      orders: {
        title: 'Order Tracking', subtitle: 'Orders', refresh: 'Refresh', retry: 'Retry', loadMore: 'Load more',
        loadError: 'Load failed', open: 'Open', orderDate: 'Ordered {{date}}', lineCount: '{{count}} line(s)',
        status: { submitted: 'Submitted' }, empty: { title: 'Empty', description: 'No orders' },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OrderListComponent);
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
    expect(fixture.nativeElement.textContent).toContain('120.00');
  });
});
