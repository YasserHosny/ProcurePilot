import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { of, throwError } from 'rxjs';
import { signal } from '@angular/core';

import { ApiService } from '../../../core/api/api.service';
import type { PurchaseRequest } from '../../../core/api/models';
import type { OrderEvidenceProjection } from '../orders-api';
import { OrdersApiService } from '../orders-api';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { SessionService } from '../../../core/auth/session.service';
import { OrderCreateComponent } from './order-create.component';

import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

describe('OrderCreateComponent', () => {
  let component: OrderCreateComponent;
  let fixture: ComponentFixture<OrderCreateComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let ordersApiService: jasmine.SpyObj<OrdersApiService>;
  let requestsApiService: jasmine.SpyObj<RequestsApiService>;
  let organisationApiService: jasmine.SpyObj<OrganisationApiService>;
  let router: Router;
  let routeSnapshot: { paramMap: ReturnType<typeof convertToParamMap>; queryParamMap: ReturnType<typeof convertToParamMap> };
  let homeCurrency: ReturnType<typeof signal<string | undefined>>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['suppliers', 'products']);
    ordersApiService = jasmine.createSpyObj('OrdersApiService', [
      'createOrder',
      'editDraftOrder',
      'getAllocations',
      'getOrder',
      'getNextOrderNumber',
      'getRequestPrefill',
    ]);
    requestsApiService = jasmine.createSpyObj('RequestsApiService', ['getRequest']);
    organisationApiService = jasmine.createSpyObj('OrganisationApiService', ['listBranches']);
    routeSnapshot = {
      paramMap: convertToParamMap({}),
      queryParamMap: convertToParamMap({}),
    };
    homeCurrency = signal<string | undefined>(undefined);

    const mockSupplier = { id: 's1', name: 'Supplier 1' } as import('../../../core/api/models').Supplier;
    const mockProduct = { id: 'p1', tenant_name: 'Product 1', base_unit: 'KG' } as import('../../../core/api/models').Product;
    apiService.suppliers.and.returnValue(of({ items: [mockSupplier], next_cursor: null }));
    apiService.products.and.returnValue(of({ items: [mockProduct], next_cursor: null }));
    ordersApiService.getAllocations.and.returnValue(of({ source_request_id: 'req-1', lines: [] }));
    ordersApiService.getNextOrderNumber.and.returnValue(of({ order_number: 'PO-000101' }));
    ordersApiService.getRequestPrefill.and.returnValue(of({ source_request_id: 'req-1', supplier: null }));
    organisationApiService.listBranches.and.returnValue(
      of({
        items: [
          { id: 'b1', name: 'فرع العليا', is_active: true, created_at: '2026-01-01T00:00:00Z' },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [OrderCreateComponent],
      providers: [
        provideTranslateService(),
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: OrdersApiService, useValue: ordersApiService },
        { provide: RequestsApiService, useValue: requestsApiService },
        { provide: OrganisationApiService, useValue: organisationApiService },
        { provide: SessionService, useValue: { homeCurrency } },
        { provide: ActivatedRoute, useValue: { snapshot: routeSnapshot } },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load initial data with suggested order number', () => {
    expect(component).toBeTruthy();
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(apiService.products).toHaveBeenCalled();
    expect(ordersApiService.getNextOrderNumber).toHaveBeenCalled();
    expect(component.form.controls.order_number.value).toBe('PO-000101');
    expect(component.suppliers().length).toBe(1);
    expect(component.products().length).toBe(1);
    expect(component.lines.length).toBe(1); // One empty line added by default
  });

  it('pre-fills supplier (id + name) and next order number when source_request_id is present', () => {
    fixture.destroy();
    routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-42' });
    requestsApiService.getRequest.and.returnValue(of({
      id: 'req-42',
      branch_id: 'b1',
      requested_by_membership_id: 'm1',
      required_by_date: '2026-10-01',
      status: 'approved',
      lines: [
        {
          id: 'rl-1',
          workspace_product_id: 'p1',
          quantity: '3.000000',
          estimated_unit_price: { amount: '12.0000', currency: 'USD' },
        },
      ],
      has_incomplete_estimate: false,
      created_at: '2026-09-29T00:00:00Z',
    } as unknown as import('../../../core/api/models').PurchaseRequest));
    ordersApiService.getAllocations.and.returnValue(of({
      source_request_id: 'req-42',
      lines: [
        {
          source_request_line_id: 'rl-1',
          requested_quantity: '3.000000',
          allocated_quantity: '0.000000',
          remaining_quantity: '3.000000',
        },
      ],
    }));
    ordersApiService.getNextOrderNumber.and.returnValue(of({ order_number: 'PO-000777' }));
    ordersApiService.getRequestPrefill.and.returnValue(of({
      source_request_id: 'req-42',
      supplier: { id: 's-cairo', name: 'Cairo Foods' },
    }));

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(ordersApiService.getRequestPrefill).toHaveBeenCalledWith('req-42');
    expect(ordersApiService.getNextOrderNumber).toHaveBeenCalled();
    expect(component.form.controls.order_number.value).toBe('PO-000777');
    expect(component.form.controls.supplier_id.value).toBe('s-cairo');
    expect(component.suppliers().some(s => s.id === 's-cairo' && s.name === 'Cairo Foods')).toBeTrue();
  });

  it('displays approved request banner with supplier and branch, changes subtitle, pre-fills expected delivery, makes currency readonly, and uses "Still to order"', () => {
    fixture.destroy();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-42' });
    requestsApiService.getRequest.and.returnValue(
      of({
        id: 'req-42',
        branch_id: 'b1',
        requested_by_membership_id: 'm1',
        required_by_date: '2026-10-01',
        status: 'approved',
        source: {
          rfq_id: 'rfq-1',
          rfq_response_id: 'resp-1',
          quotation_id: 'q-1',
          supplier_id: 's-cairo',
          supplier_name: 'الوفرة للمواد الغذائية',
        },
        lines: [
          {
            id: 'rl-1',
            workspace_product_id: 'p1',
            quantity: '3.000000',
            estimated_unit_price: { amount: '12.0000', currency: 'SAR' },
          },
        ],
        has_incomplete_estimate: false,
        created_at: '2026-09-29T00:00:00Z',
      } as unknown as import('../../../core/api/models').PurchaseRequest),
    );
    ordersApiService.getAllocations.and.returnValue(
      of({
        source_request_id: 'req-42',
        lines: [
          {
            source_request_line_id: 'rl-1',
            requested_quantity: '3.000000',
            allocated_quantity: '0.000000',
            remaining_quantity: '3.000000',
          },
        ],
      }),
    );
    ordersApiService.getNextOrderNumber.and.returnValue(of({ order_number: 'PO-000777' }));
    ordersApiService.getRequestPrefill.and.returnValue(
      of({
        source_request_id: 'req-42',
        supplier: { id: 's-cairo', name: 'الوفرة للمواد الغذائية' },
      }),
    );

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    // 1. Banner shows supplier and branch, linked to the request
    const bannerLink = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="source-request-link"]',
    );
    expect(bannerLink).toBeTruthy();
    expect(bannerLink?.getAttribute('href')).toBe('/requests/req-42');
    expect(bannerLink?.textContent).toContain('الوفرة للمواد الغذائية');
    expect(bannerLink?.textContent).toContain('فرع العليا');

    // 2. Subtitle changes to "Check the order, then create it."
    const subtitle = (fixture.nativeElement as HTMLElement).querySelector('.page-header p');
    expect(subtitle?.textContent?.trim()).toBe('Check the order, then create it.');

    // 3. Expected delivery date pre-filled from required_by_date
    expect(component.form.controls.expected_delivery_date.value).toEqual(new Date(2026, 9, 1));

    // 4. Currency is readonly
    const currencyInput = (fixture.nativeElement as HTMLElement).querySelector(
      'input[formControlName="currency"]',
    );
    expect(currencyInput?.hasAttribute('readonly')).toBeTrue();

    // 5. Line remaining badge says "Still to order"
    const remainingBadge = (fixture.nativeElement as HTMLElement).querySelector('.remaining-badge');
    expect(remainingBadge?.textContent).toContain('Still to order: 3');
  });

  it('handles prefill and next-number failures gracefully by leaving fields blank', () => {
    fixture.destroy();
    routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-99' });
    requestsApiService.getRequest.and.returnValue(throwError(() => new Error('Failed')));
    ordersApiService.getAllocations.and.returnValue(throwError(() => new Error('Failed')));
    ordersApiService.getRequestPrefill.and.returnValue(throwError(() => new Error('Prefill error')));
    ordersApiService.getNextOrderNumber.and.returnValue(throwError(() => new Error('Next number error')));

    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component.form.controls.order_number.value).toBe('');
    expect(component.form.controls.supplier_id.value).toBe('');
  });

  it('shows specific i18n error messages on 409 for order_number_exists and idempotency_key_exists', () => {
    component.form.patchValue({
      order_number: 'PO-DUP-1',
      supplier_id: 's1',
      order_date: new Date('2026-09-29T12:00:00Z'),
      currency: 'USD',
    });
    component.lines.at(0).patchValue({
      description: 'Test Item',
      quantity: 1,
      base_unit: 'EA',
      unit_price: 10,
      line_tax: 0,
    });

    ordersApiService.createOrder.and.returnValue(
      throwError(() => new HttpErrorResponse({
        status: 409,
        error: {
          code: 'CONFLICT',
          message: 'Order number already exists',
          details: { reason: 'order_number_exists' },
        },
      })),
    );

    component.submit();
    expect(component.errorMessage()).toBe('orders.create.errors.orderNumberExists');

    ordersApiService.createOrder.and.returnValue(
      throwError(() => new HttpErrorResponse({
        status: 409,
        error: {
          code: 'CONFLICT',
          message: 'Idempotency key already used',
          details: { reason: 'idempotency_key_exists' },
        },
      })),
    );

    component.submit();
    expect(component.errorMessage()).toBe('orders.create.errors.idempotencyKeyExists');
  });

  it('defaults the currency to the home currency and submits the selected currency', () => {
    fixture.destroy();
    homeCurrency.set('EGP');
    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    expect(component.form.controls.currency.value).toBe('EGP');

    component.form.patchValue({
      order_number: 'PO-EGP-1', supplier_id: 's1',
      order_date: new Date('2026-09-29T12:00:00Z'), currency: 'USD',
    });
    component.lines.at(0).patchValue({ description: 'Test Item', quantity: 1, base_unit: 'EA', unit_price: 10, line_tax: 0 });
    ordersApiService.createOrder.and.returnValue(of({ id: 'order-egp' } as import('../orders-api').PurchaseOrder));

    component.submit();

    expect(ordersApiService.createOrder.calls.mostRecent().args[0].total.currency).toBe('USD');
  });

  it('defaults to USD when no home currency is configured', () => {
    expect(component.form.controls.currency.value).toBe('USD');
  });

  it('prefills the PO unit price only from the supplier quoted price, never the landed estimate', () => {
    const loadRequest = (quoted: { amount: string; currency: string } | null) => {
      fixture.destroy();
      routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-1' });
      requestsApiService.getRequest.and.returnValue(of({
        id: 'req-1', branch_id: 'b1', requested_by_membership_id: 'm1',
        required_by_date: '2026-10-01', status: 'approved',
        source_rfq_response_id: 'rfq-response-1',
        lines: [{
          id: 'rl-1', workspace_product_id: 'p1', quantity: '5.000000',
          // landed estimate (incl. VAT/delivery) differs from the supplier's quoted price
          estimated_unit_price: { amount: '9.5000', currency: 'USD' },
          quoted_unit_price: quoted,
        }],
        has_incomplete_estimate: false, created_at: '2026-09-29T00:00:00Z',
      } as unknown as import('../../../core/api/models').PurchaseRequest));
      ordersApiService.getAllocations.and.returnValue(of({ source_request_id: 'req-1', lines: [{ source_request_line_id: 'rl-1', requested_quantity: '5.000000', allocated_quantity: '0', remaining_quantity: '5.000000' }] }));
      fixture = TestBed.createComponent(OrderCreateComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    };

    loadRequest({ amount: '9.0000', currency: 'USD' });
    expect(component.lines.at(0).controls.unit_price.value).toBe(9);
    expect(component.lines.at(0).controls.estimated_price.value).toBe(9.5);
    fixture.destroy();
    loadRequest(null);
    expect(component.lines.at(0).controls.unit_price.value).toBeNull();
    expect(component.lines.at(0).controls.estimated_price.value).toBe(9.5);
  });

  describe('quoted currency', () => {
    type Quote = { amount: string; currency: string } | null;
    const loadLines = (quotes: Quote[], remaining: string[] = quotes.map(() => '5.000000')) => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog);
      translate.use('en');
      fixture.destroy();
      routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-1' });
      requestsApiService.getRequest.and.returnValue(of({
        id: 'req-1', branch_id: 'b1', requested_by_membership_id: 'm1',
        required_by_date: '2026-10-01', status: 'approved',
        source_rfq_response_id: 'rfq-response-1',
        lines: quotes.map((quoted, i) => ({
          id: `rl-${i}`, workspace_product_id: 'p1', quantity: '5.000000', quoted_unit_price: quoted,
        })),
        has_incomplete_estimate: false, created_at: '2026-09-29T00:00:00Z',
      } as unknown as import('../../../core/api/models').PurchaseRequest));
      ordersApiService.getAllocations.and.returnValue(of({
        source_request_id: 'req-1',
        lines: quotes.map((_, i) => ({ source_request_line_id: `rl-${i}`, requested_quantity: '5.000000', allocated_quantity: '0', remaining_quantity: remaining[i] })),
      }));
      fixture = TestBed.createComponent(OrderCreateComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    };

    it('takes the order currency from the supplier quote and blocks a different one on submit', () => {
      loadLines([{ amount: '9.0000', currency: 'EUR' }]);
      expect(component.form.controls.currency.value).toBe('EUR');
      expect(component.lines.at(0).controls.unit_price.value).toBe(9);

      component.form.patchValue({ order_number: 'PO-1', supplier_id: 's1', currency: 'EGP' });
      ordersApiService.createOrder.calls.reset();
      component.submit();
      expect(ordersApiService.createOrder).not.toHaveBeenCalled();
      expect(component.errorMessage()).toContain('EUR');
    });

    it('ignores fully allocated lines when deciding whether quote currencies are mixed', () => {
      loadLines([{ amount: '9.0000', currency: 'EUR' }, { amount: '10.0000', currency: 'USD' }], ['0', '5.000000']);
      expect(component.lines.length).toBe(1);
      expect(component.form.controls.currency.value).toBe('USD');
      expect(component.lines.at(0).controls.unit_price.value).toBe(10);
      expect(component.errorMessage()).toBeNull();
    });

    it('stops enforcing the quote currency once every pre-filled price has been replaced', () => {
      loadLines([{ amount: '9.0000', currency: 'EUR' }]);
      component.lines.at(0).controls.unit_price.setValue(1200);
      component.form.patchValue({ order_number: 'PO-1', supplier_id: 's1', currency: 'EGP' });
      ordersApiService.createOrder.calls.reset();
      ordersApiService.createOrder.and.returnValue(of({ id: 'o1' }) as never);
      component.submit();
      expect(ordersApiService.createOrder).toHaveBeenCalledTimes(1);
      expect(component.errorMessage()).toBeNull();
    });

    it('does not pre-fill prices when the quote lines mix currencies', () => {
      loadLines([{ amount: '9.0000', currency: 'EUR' }, { amount: '10.0000', currency: 'USD' }]);
      expect(component.lines.at(0).controls.unit_price.value).toBeNull();
      expect(component.lines.at(1).controls.unit_price.value).toBeNull();
      expect(component.errorMessage()).toBe(enCatalog.orders.create.quotedMixedCurrencies);
    });
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

  it('keeps pack wording out of the stored description and exposes a separate localized pack hint', () => {
    const product = {
      id: 'p2', tenant_name: 'Rice', canonical_name: 'Rice', base_unit: 'kilogram',
      pack: { pack_count: 1, unit_size: '25', base_quantity: '25' }, status: 'active', created_at: '',
    } as import('../../../core/api/models').Product;
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
    component.products.set([product]);
    component.lines.at(0).controls.workspace_product_id.setValue('p2');
    component.onProductSelected(0, 'p2');
    expect(component.lines.at(0).controls.description.value).toBe('Rice');
    expect(component.packHint(component.lines.at(0))).toBe('pack of 25 kg');
    translate.use('ar');
    expect(component.packHint(component.lines.at(0))).toBe('عبوة ٢٥ كجم');
  });

  it('uses the request pack snapshot in the prefill hint despite a different live pack', () => {
    fixture.destroy();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
    routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-1' });
    apiService.products.and.returnValue(of({ items: [{
      id: 'p1', tenant_name: 'Milk', base_unit: 'litre',
      pack: { pack_count: 1, unit_size: '18', base_quantity: '18' },
      status: 'active', created_at: '',
    } as import('../../../core/api/models').Product], next_cursor: null }));
    const request = {
      id: 'req-1', branch_id: 'b1', requested_by_membership_id: 'm1',
      required_by_date: '2026-10-01', status: 'approved',
      lines: [{ id: 'rl-1', workspace_product_id: 'p1', quantity: '2.000000',
        product_name: 'Milk', base_unit: 'litre', pack_base_quantity: '6.000000' }],
      has_incomplete_estimate: false, created_at: '2026-09-29T00:00:00Z',
    } as import('../../../core/api/models').PurchaseRequest;
    requestsApiService.getRequest.and.returnValue(of(request));
    ordersApiService.getAllocations.and.returnValue(of({ source_request_id: 'req-1', lines: [{
      source_request_line_id: 'rl-1', requested_quantity: '2.000000',
      allocated_quantity: '0', remaining_quantity: '2.000000',
    }] }));
    fixture = TestBed.createComponent(OrderCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component.lines.at(0).controls.quantity.value).toBe(2);
    expect(component.packHint(component.lines.at(0))).toBe('pack of 6 L');
    translate.use('ar');
    expect(component.packHint(component.lines.at(0))).toBe('عبوة ٦ لتر');
    translate.use('en');
    component.sourceRequest.set({ ...request, lines: [{ ...request.lines[0], pack_base_quantity: null }] });
    expect(component.packHint(component.lines.at(0))).toBe('pack of 18 L');
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

  describe('PPS-118: one purchase order per click and chunk load handling', () => {
    beforeEach(() => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
    });

    it('(a) create success: the button is disabled while navigate is still pending, and calling submit() again does not call createOrder a second time; navigate was called with [/orders, id]', fakeAsync(() => {
      let resolveNavigate!: (val: boolean) => void;
      const navigatePromise = new Promise<boolean>((resolve) => {
        resolveNavigate = resolve;
      });
      (router.navigate as jasmine.Spy).and.returnValue(navigatePromise);

      component.form.patchValue({
        order_number: 'PO-TEST-1',
        supplier_id: 's1',
        order_date: new Date('2026-09-29T12:00:00Z'),
        currency: 'USD',
      });
      component.lines.at(0).patchValue({
        description: 'Test Item',
        quantity: 2,
        base_unit: 'EA',
        unit_price: 10,
        line_tax: 0,
      });

      const mockOrder = { id: 'order-123', order_number: 'PO-TEST-1' } as import('../orders-api').PurchaseOrder;
      ordersApiService.createOrder.and.returnValue(of(mockOrder));

      const submitButton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;

      component.submit();
      fixture.detectChanges();

      expect(ordersApiService.createOrder).toHaveBeenCalledTimes(1);
      expect(component.isSubmitting()).toBeTrue();
      expect(submitButton.disabled).toBeTrue();

      // Calling submit again and clicking button again
      component.submit();
      submitButton.click();
      expect(ordersApiService.createOrder).toHaveBeenCalledTimes(1);
      expect(router.navigate).toHaveBeenCalledWith(['/orders', 'order-123']);

      resolveNavigate(true);
      tick();
      fixture.detectChanges();
      expect(submitButton.disabled).toBeTrue();
    }));

    it('(b) navigate resolves false: the notice with the PO number and an Open order link shows, and the button stays disabled', fakeAsync(() => {
      (router.navigate as jasmine.Spy).and.returnValue(Promise.resolve(false));

      component.form.patchValue({
        order_number: 'PO-000006',
        supplier_id: 's1',
        order_date: new Date('2026-09-29T12:00:00Z'),
        currency: 'USD',
      });
      component.lines.at(0).patchValue({
        description: 'Test Item',
        quantity: 1,
        base_unit: 'EA',
        unit_price: 10,
        line_tax: 0,
      });

      const mockOrder = { id: 'po-6-id', order_number: 'PO-000006' } as import('../orders-api').PurchaseOrder;
      ordersApiService.createOrder.and.returnValue(of(mockOrder));

      component.submit();
      tick();
      fixture.detectChanges();

      const notice = fixture.nativeElement.querySelector('[role="status"]');
      expect(notice).toBeTruthy();
      expect(notice?.textContent).toContain('PO-000006');

      const openLink = fixture.nativeElement.querySelector('a[href="/orders/po-6-id"]') ||
        Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('a')).find((el) =>
          el.getAttribute('ng-reflect-router-link')?.includes('po-6-id') || el.textContent?.includes('Open order'),
        );
      expect(openLink).toBeTruthy();

      const submitButton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
      expect(submitButton.disabled).toBeTrue();
      expect(component.isSubmitting()).toBeTrue();
    }));

    it('(c) edit-draft path: editDraftOrder is called once; same disabled behaviour', fakeAsync(() => {
      component.editOrderId.set('edit-po-1');
      (router.navigate as jasmine.Spy).and.returnValue(Promise.resolve(true));

      component.form.patchValue({
        order_number: 'PO-EDIT-1',
        supplier_id: 's1',
        order_date: new Date('2026-09-29T12:00:00Z'),
        currency: 'USD',
      });
      component.lines.at(0).patchValue({
        description: 'Test Item',
        quantity: 1,
        base_unit: 'EA',
        unit_price: 10,
        line_tax: 0,
      });

      const mockOrder = { id: 'edit-po-1', order_number: 'PO-EDIT-1' } as import('../orders-api').PurchaseOrder;
      ordersApiService.editDraftOrder.and.returnValue(of(mockOrder));

      const submitButton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;

      component.submit();
      fixture.detectChanges();

      expect(ordersApiService.editDraftOrder).toHaveBeenCalledTimes(1);
      expect(component.isSubmitting()).toBeTrue();
      expect(submitButton.disabled).toBeTrue();

      component.submit();
      expect(ordersApiService.editDraftOrder).toHaveBeenCalledTimes(1);

      tick();
      fixture.detectChanges();
      expect(submitButton.disabled).toBeTrue();
    }));

    it('(d) 409 quantity_exceeds_allocation shows the translated message and re-enables the button', () => {
      component.form.patchValue({
        order_number: 'PO-1',
        supplier_id: 's1',
        order_date: new Date('2026-09-29T12:00:00Z'),
        currency: 'USD',
      });
      component.lines.at(0).patchValue({
        description: 'Test Item',
        quantity: 1,
        base_unit: 'EA',
        unit_price: 10,
        line_tax: 0,
      });

      ordersApiService.createOrder.and.returnValue(
        throwError(() => new HttpErrorResponse({
          status: 409,
          error: {
            code: 'CONFLICT',
            message: 'Over allocated',
            details: { reason: 'quantity_exceeds_allocation' },
          },
        })),
      );

      component.submit();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Part of this request was ordered after you opened this form. Reload the page to see what is still to order.');
      expect(component.isSubmitting()).toBeFalse();
      const submitButton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
      expect(submitButton.disabled).toBeFalse();
    });

    it('(e) a request with nothing left: no lines, notice plus link PO-000005, Create disabled', () => {
      const mockReq = {
        id: 'req-fully-ordered',
        lines: [
          {
            id: 'rl-1',
            product_name: 'Item 1',
            quantity: '5.000000',
            base_unit: 'EA',
            estimated_unit_price: null,
            quoted_unit_price: null,
          },
        ],
      } as unknown as PurchaseRequest;

      const mockAllocations = {
        source_request_id: 'req-fully-ordered',
        lines: [
          {
            source_request_line_id: 'rl-1',
            requested_quantity: '5.000000',
            allocated_quantity: '5.000000',
            remaining_quantity: '0',
          },
        ],
        orders: [
          {
            id: 'po-5',
            order_number: 'PO-000005',
            status: 'draft' as const,
          },
        ],
      };

      requestsApiService.getRequest.and.returnValue(of(mockReq));
      ordersApiService.getAllocations.and.returnValue(of(mockAllocations));

      routeSnapshot.queryParamMap = convertToParamMap({ source_request_id: 'req-fully-ordered' });

      const newFixture = TestBed.createComponent(OrderCreateComponent);
      newFixture.detectChanges();
      const comp = newFixture.componentInstance;

      expect(comp.lines.length).toBe(0);

      const notice = newFixture.nativeElement.querySelector('[role="status"]');
      expect(notice).toBeTruthy();
      expect(notice?.textContent).toContain('Everything on this request has already been ordered.');

      const link = Array.from((newFixture.nativeElement as HTMLElement).querySelectorAll('a')).find((a) =>
        a.textContent?.includes('PO-000005'),
      );
      expect(link).toBeTruthy();

      const submitButton = newFixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
      expect(submitButton.disabled).toBeTrue();
    });

    it('edit-draft of a PO whose request has all lines at remaining 0 → no fully-ordered-notice, lines present, Save enabled', () => {
      routeSnapshot.paramMap = convertToParamMap({ id: 'po-draft-1' });
      const order = {
        id: 'po-draft-1',
        order_number: 'PO-DRAFT-1',
        supplier_id: 's1',
        order_date: '2026-09-29T12:00:00Z',
        expected_delivery_date: null,
        total: { amount: '50.0000', currency: 'USD' },
        tax: { amount: '0.0000', currency: 'USD' },
        source_kind: 'manual',
        source_reference: 'PO-DRAFT-1',
        source_request_id: 'req-1',
        lines: [
          {
            id: 'ol-1',
            line_number: 1,
            workspace_product_id: 'p1',
            description: 'Product 1',
            ordered_quantity: '5.000000',
            base_unit: 'KG',
            unit_price: { amount: '10.0000', currency: 'USD' },
            tax: { amount: '0.0000', currency: 'USD' },
            line_total: { amount: '50.0000', currency: 'USD' },
            source_request_line_id: 'rl-1',
          },
        ],
      } as import('../orders-api').PurchaseOrder;

      ordersApiService.getOrder.and.returnValue(
        of({
          order,
          confirmation: null,
          receipts: [],
          lifecycle: {
            purchase_order_id: 'po-draft-1',
            status: 'draft',
            confirmation: 'unavailable',
            receipt: 'unavailable',
            lines: [],
          },
        } as unknown as OrderEvidenceProjection),
      );
      requestsApiService.getRequest.and.returnValue(
        of({
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
              estimated_unit_price: { amount: '10.0000', currency: 'USD' },
            },
          ],
          has_incomplete_estimate: false,
          created_at: '2026-09-29T00:00:00Z',
        } as unknown as import('../../../core/api/models').PurchaseRequest),
      );
      ordersApiService.getAllocations.and.returnValue(
        of({
          source_request_id: 'req-1',
          lines: [
            {
              source_request_line_id: 'rl-1',
              requested_quantity: '5.000000',
              allocated_quantity: '5.000000',
              remaining_quantity: '0',
            },
          ],
          orders: [
            {
              id: 'po-draft-1',
              order_number: 'PO-DRAFT-1',
              status: 'draft' as const,
            },
          ],
        }),
      );

      const editFixture = TestBed.createComponent(OrderCreateComponent);
      editFixture.detectChanges();
      const comp = editFixture.componentInstance;

      expect(editFixture.nativeElement.querySelector('[data-testid="fully-ordered-notice"]')).toBeNull();
      expect(comp.lines.length).toBe(1);
      const submitButton = editFixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
      expect(submitButton.disabled).toBeFalse();
    });
  });
});
