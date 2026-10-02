import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { OrdersApiService } from '../orders-api';
import { OrderCreateComponent } from './order-create.component';

import { Router } from '@angular/router';

describe('OrderCreateComponent', () => {
  let component: OrderCreateComponent;
  let fixture: ComponentFixture<OrderCreateComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let ordersApiService: jasmine.SpyObj<OrdersApiService>;
  let router: Router;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['suppliers', 'products']);
    ordersApiService = jasmine.createSpyObj('OrdersApiService', ['createOrder']);

    const mockSupplier = { id: 's1', name: 'Supplier 1' } as import('../../../core/api/models').Supplier;
    const mockProduct = { id: 'p1', tenant_name: 'Product 1', base_unit: 'KG' } as import('../../../core/api/models').Product;
    apiService.suppliers.and.returnValue(of({ items: [mockSupplier], next_cursor: null }));
    apiService.products.and.returnValue(of({ items: [mockProduct], next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [OrderCreateComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: OrdersApiService, useValue: ordersApiService },
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
