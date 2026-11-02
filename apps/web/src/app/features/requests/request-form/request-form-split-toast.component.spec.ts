import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { PurchaseRequest } from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import { OrdersApiService } from '../../orders/orders-api';
import { RequestFormComponent } from './request-form.component';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';

const baseMockRequest: PurchaseRequest = {
  id: 'r1',
  branch_id: 'b1',
  cost_centre_id: 'cc1',
  requested_by_membership_id: 'm1',
  required_by_date: '2026-09-15',
  status: 'draft',
  lines: [
    {
      id: 'l1',
      workspace_product_id: 'wp1',
      quantity: '5.000000',
      quoted_prices_include_vat: false,
      quoted_vat_rate: null,
      quoted_net_unit_price: null,
    },
  ],
  has_incomplete_estimate: false,
  created_at: '2026-08-23T00:00:00Z',
};

describe('RequestFormComponent — basket split submit toast (PPS-150 / P-119)', () => {
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let ordersApi: jasmine.SpyObj<OrdersApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'createRequest',
      'updateRequest',
      'submitRequest',
      'submitGroup',
      'withdrawGroup',
      'getRequest',
    ]);
    ordersApi = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
    ordersApi.getAllocations.and.returnValue(
      of({
        source_request_id: 'r1',
        lines: [],
        orders: [],
      }),
    );
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members', 'products']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);

    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.members.and.returnValue(of({ items: [], next_cursor: null }));
    api.products.and.returnValue(
      of({
        items: [
          {
            id: 'wp1',
            tenant_name: 'Product 1',
            canonical_name: 'Product 1',
            base_unit: 'each',
            pack: { pack_count: 1, unit_size: '1.000000' },
            status: 'active',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrdersApiService, useValue: ordersApi },
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: api },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => 'r1' } } },
        },
      ],
    })
      .overrideComponent(RequestFormComponent, {
        set: {
          providers: [
            provideAppDateAdapter(),
            { provide: MatSnackBar, useValue: snackBarSpy },
            { provide: Router, useValue: routerSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
  });

  function createComponentWithRequest(req: PurchaseRequest): ComponentFixture<RequestFormComponent> {
    requestsApi.getRequest.and.returnValue(of(req));
    const fixture = TestBed.createComponent(RequestFormComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('shows split success toast with count N when submitting a split with 2 requests', () => {
    const splitRequest: PurchaseRequest = {
      ...baseMockRequest,
      request_group: {
        id: 'grp-split-1',
        rfq_id: 'rfq-1',
        position: 1,
        size: 2,
        combined_total: { amount: '200.00', currency: 'SAR' },
        sibling_request_ids: ['r2'],
      },
    };
    requestsApi.submitGroup.and.returnValue(of([splitRequest, { ...splitRequest, id: 'r2' }]));

    const fixture = createComponentWithRequest(splitRequest);
    fixture.componentInstance.submitRequest();

    expect(requestsApi.submitGroup).toHaveBeenCalledWith('grp-split-1', jasmine.any(String));
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      '2 purchase requests submitted for approval as one split.',
      undefined,
      { duration: 3500 },
    );
  });

  it('shows split success toast with count N when submitting a split with 3 requests', () => {
    const splitRequest: PurchaseRequest = {
      ...baseMockRequest,
      request_group: {
        id: 'grp-split-2',
        rfq_id: 'rfq-2',
        position: 1,
        size: 3,
        combined_total: { amount: '450.00', currency: 'SAR' },
        sibling_request_ids: ['r2', 'r3'],
      },
    };
    requestsApi.submitGroup.and.returnValue(
      of([splitRequest, { ...splitRequest, id: 'r2' }, { ...splitRequest, id: 'r3' }]),
    );

    const fixture = createComponentWithRequest(splitRequest);
    fixture.componentInstance.submitRequest();

    expect(requestsApi.submitGroup).toHaveBeenCalledWith('grp-split-2', jasmine.any(String));
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      '3 purchase requests submitted for approval as one split.',
      undefined,
      { duration: 3500 },
    );
  });

  it('shows single request success toast when submitting a standalone request without split', () => {
    const singleRequest: PurchaseRequest = {
      ...baseMockRequest,
      request_group: undefined,
    };
    requestsApi.updateRequest.and.returnValue(of(singleRequest));
    requestsApi.submitRequest.and.returnValue(of({ ...singleRequest, status: 'submitted' }));

    const fixture = createComponentWithRequest(singleRequest);
    fixture.componentInstance.submitRequest();

    expect(requestsApi.updateRequest).toHaveBeenCalled();
    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request submitted for approval.',
      undefined,
      { duration: 3500 },
    );
  });
});
