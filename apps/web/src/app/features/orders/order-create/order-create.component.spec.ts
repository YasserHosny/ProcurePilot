import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { OrderEvidenceProjection } from '../orders-api';
import { OrdersApiService } from '../orders-api';
import { RequestsApiService } from '../../requests/requests-api';
import { OrderCreateComponent } from './order-create.component';

import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

describe('OrderCreateComponent', () => {
  let component: OrderCreateComponent;
  let fixture: ComponentFixture<OrderCreateComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let ordersApiService: jasmine.SpyObj<OrdersApiService>;
  let requestsApiService: jasmine.SpyObj<RequestsApiService>;
  let router: Router;
  let routeSnapshot: { paramMap: ReturnType<typeof convertToParamMap>; queryParamMap: ReturnType<typeof convertToParamMap> };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['suppliers', 'products']);
    ordersApiService = jasmine.createSpyObj('OrdersApiService', [
      'createOrder',
      'editDraftOrder',
      'getAllocations',
      'getOrder',
    ]);
    requestsApiService = jasmine.createSpyObj('RequestsApiService', ['getRequest']);
    routeSnapshot = {
      paramMap: convertToParamMap({}),
      queryParamMap: convertToParamMap({}),
    };

    const mockSupplier = { id: 's1', name: 'Supplier 1' } as import('../../../core/api/models').Supplier;
    const mockProduct = { id: 'p1', tenant_name: 'Product 1', base_unit: 'KG' } as import('../../../core/api/models').Product;
    apiService.suppliers.and.returnValue(of({ items: [mockSupplier], next_cursor: null }));
    apiService.products.and.returnValue(of({ items: [mockProduct], next_cursor: null }));
    ordersApiService.getAllocations.and.returnValue(of({ source_request_id: 'req-1', lines: [] }));

    await TestBed.configureTestingModule({
      imports: [OrderCreateComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: OrdersApiService, useValue: ordersApiService },
        { provide: RequestsApiService, useValue: requestsApiService },
        { provide: ActivatedRoute, useValue: { snapshot: routeSnapshot } },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load initial data', () => {
    expect(component).toBeTruthy();
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(apiService.products).toHaveBeenCalled();
    expect(component.suppliers().length).toBe(1);
    expect(component.products().length).toBe(1);
    expect(component.lines.length).toBe(1); // One empty line added by default
  });

  it('loads a source request when editing a request-derived draft and preserves links on submit', () => {
    routeSnapshot.paramMap = convertToParamMap({ id: 'order-1' });
    const order = {
      id: 'order-1',
      tenant_id: 'tenant-1',
      order_number: 'PO-EDIT-1',
      supplier_id: 's1',
      status: 'draft',
      order_date: '2026-09-29',
      expected_delivery_date: null,
      total: { amount: '20.0000', currency: 'USD' },
      tax: { amount: '0.0000', currency: 'USD' },
      source_kind: 'manual',
      source_reference: 'PO-EDIT-1',
      source_hash: null,
      source_request_id: 'req-1',
      created_by: 'm1',
      created_at: '2026-09-29T00:00:00Z',
      updated_at: '2026-09-29T00:00:00Z',
      lines: [
        {
          id: 'ol-1',
          line_number: 1,
          workspace_product_id: 'p1',
          description: 'Product 1',
          ordered_quantity: '2.000000',
          base_unit: 'KG',
          unit_price: { amount: '10.0000', currency: 'USD' },
          tax: { amount: '0.0000', currency: 'USD' },
          line_total: { amount: '20.0000', currency: 'USD' },
          source_request_line_id: 'rl-1',
        },
      ],
    } as import('../orders-api').PurchaseOrder;
    ordersApiService.getOrder.and.returnValue(of({
      order,
      confirmation: null,
      receipts: [],
      lifecycle: {},
    } as unknown as OrderEvidenceProjection));
    requestsApiService.getRequest.and.returnValue(of({
      id: 'req-1',
      branch_id: 'b1',
      requested_by_membership_id: 'm1',
      required_by_date: '2026-10-01',
      status: 'ordered',
      lines: [
        {
          id: 'rl-1',
          workspace_product_id: 'p1',
          quantity: '5.000000',
          estimated_unit_price: { amount: '9.0000', currency: 'USD' },
        },
      ],
      has_incomplete_estimate: false,
      created_at: '2026-09-29T00:00:00Z',
    } as unknown as import('../../../core/api/models').PurchaseRequest));
    ordersApiService.getAllocations.and.returnValue(of({
      source_request_id: 'req-1',
      lines: [
        {
          source_request_line_id: 'rl-1',
          requested_quantity: '5.000000',
          allocated_quantity: '2.000000',
          remaining_quantity: '3.000000',
        },
      ],
    }));
    ordersApiService.editDraftOrder.and.returnValue(of(order));

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(requestsApiService.getRequest).toHaveBeenCalledWith('req-1');
    expect(ordersApiService.getAllocations).toHaveBeenCalledWith('req-1');
    expect(component.sourceRequest()?.id).toBe('req-1');

    component.submit();

    expect(ordersApiService.editDraftOrder).toHaveBeenCalled();
    const payload = ordersApiService.editDraftOrder.calls.mostRecent().args[1];
    expect(payload.source_request_id).toBe('req-1');
    expect(payload.lines[0].source_request_line_id).toBe('rl-1');
  });

  it('should auto-fill product details when selected', () => {
    component.onProductSelected(0, 'p1');
    const lineGroup = component.lines.at(0);
    expect(lineGroup.value.description).toBe('Product 1');
    expect(lineGroup.value.base_unit).toBe('KG');
  });

  it('should calculate totals, submit successfully, and navigate', () => {
    component.form.patchValue({
      order_number: 'PO-TEST-1',
      supplier_id: 's1',
      order_date: new Date('2026-09-29T12:00:00Z'),
      currency: 'USD',
      order_tax: 5,
    });

    const lineGroup = component.lines.at(0);
    lineGroup.patchValue({
      description: 'Test Item',
      quantity: 2,
      base_unit: 'EA',
      unit_price: 10,
      line_tax: 2,
    });

    const mockOrder = { id: 'order-123' } as import('../orders-api').PurchaseOrder;
    ordersApiService.createOrder.and.returnValue(of(mockOrder));

    component.submit();

    expect(ordersApiService.createOrder).toHaveBeenCalled();
    const payload = ordersApiService.createOrder.calls.mostRecent().args[0];
    
    expect(payload.order_number).toBe('PO-TEST-1');
    expect(payload.supplier_id).toBe('s1');
    expect(payload.lines.length).toBe(1);
    expect(payload.lines[0].description).toBe('Test Item');
    
    expect(payload.total.amount).toBe('22.0000');
    expect(payload.tax.amount).toBe('5.0000');
    expect(payload.lines[0].line_total.amount).toBe('22.0000');

    expect(router.navigate).toHaveBeenCalledWith(['/orders', 'order-123']);
  });

  it('does not submit if form is invalid or no lines exist', () => {
    component.lines.clear();
    component.submit();
    expect(ordersApiService.createOrder).not.toHaveBeenCalled();

    component.addLine();
    // It's still invalid because required fields are empty
    component.submit();
    expect(ordersApiService.createOrder).not.toHaveBeenCalled();
  });
});
