import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { OrdersApiService, PurchaseOrderCreate } from './orders-api';

describe('OrdersApiService', () => {
  let service: OrdersApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        OrdersApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(OrdersApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('createOrder POSTs body and sets Idempotency-Key header', () => {
    const payload: PurchaseOrderCreate = {
      order_number: 'PO-TEST',
      supplier_id: 's-1',
      order_date: '2026-09-30',
      expected_delivery_date: null,
      total: { amount: '100.0000', currency: 'USD' },
      tax: { amount: '0.0000', currency: 'USD' },
      source_kind: 'manual',
      source_reference: 'web',
      lines: []
    };

    const idempotencyKey = 'test-idempotency-key';

    service.createOrder(payload, idempotencyKey).subscribe();

    const req = http.expectOne('/api/v1/orders');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    expect(req.request.headers.get('Idempotency-Key')).toBe(idempotencyKey);
    req.flush({});
  });

  it('createOrder defaults Idempotency-Key when omitted', () => {
    const payload: PurchaseOrderCreate = {
      order_number: 'PO-TEST-2',
      supplier_id: 's-1',
      order_date: '2026-09-30',
      expected_delivery_date: null,
      total: { amount: '100.0000', currency: 'USD' },
      tax: { amount: '0.0000', currency: 'USD' },
      source_kind: 'manual',
      source_reference: 'web',
      lines: []
    };

    service.createOrder(payload).subscribe();

    const req = http.expectOne('/api/v1/orders');
    expect(req.request.headers.has('Idempotency-Key')).toBeTrue();
    expect(req.request.headers.get('Idempotency-Key')).toBeTruthy();
    req.flush({});
  });
});
