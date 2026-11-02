import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Member, PurchaseRequest } from '../../../core/api/models';
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
  status: 'submitted',
  lines: [],
  has_incomplete_estimate: false,
  created_at: '2026-08-23T00:00:00Z',
};

describe('RequestFormComponent — approver name display (PPS-145 / P-114)', () => {
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let ordersApi: jasmine.SpyObj<OrdersApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;

  const approverMember: Member = {
    id: 'm-approver',
    email: 'approver@example.com',
    role: 'approver',
    status: 'active',
    mfa_enabled: false,
    created_at: '2026-01-01T00:00:00Z',
  };

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
    api.members.and.returnValue(of({ items: [approverMember], next_cursor: null }));
    api.products.and.returnValue(of({ items: [], next_cursor: null }));

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

  it('shows assigned_name and not email when assigned_name is present', () => {
    const requestWithName: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as1',
        assigned_membership_id: 'm-approver',
        assigned_name: 'Sarah Connor',
        assigned_email: 'approver@example.com',
        source: 'threshold_match',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithName);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('Sarah Connor');
    expect(section?.textContent).not.toContain('approver@example.com');
  });

  it('shows approver email when assigned_name is null', () => {
    const requestWithNullName: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as2',
        assigned_membership_id: 'm-approver',
        assigned_name: null,
        assigned_email: 'approver@example.com',
        source: 'threshold_match',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithNullName);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('approver@example.com');
  });

  it('shows approver email when assigned_name is empty string', () => {
    const requestWithEmptyName: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as3',
        assigned_membership_id: 'm-approver',
        assigned_name: '',
        source: 'threshold_match',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithEmptyName);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('approver@example.com');
  });

  it('shows approver email when assigned_name is whitespace-only string', () => {
    const requestWithWhitespaceName: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as4',
        assigned_membership_id: 'm-approver',
        assigned_name: '   ',
        source: 'threshold_match',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithWhitespaceName);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('approver@example.com');
  });

  it('shows approver email when assigned_name is undefined', () => {
    const requestWithoutName: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as5',
        assigned_membership_id: 'm-approver',
        source: 'threshold_match',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithoutName);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('approver@example.com');
  });

  it('falls back to raw membership id when assigned_name is missing and member is unknown', () => {
    api.members.and.returnValue(of({ items: [], next_cursor: null }));

    const requestWithUnknownMember: PurchaseRequest = {
      ...baseMockRequest,
      approval_step: {
        id: 'as6',
        assigned_membership_id: 'unknown-id-999',
        assigned_name: null,
        source: 'owner_fallback',
        status: 'pending',
      },
    };

    const fixture = createComponentWithRequest(requestWithUnknownMember);
    const compiled = fixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');

    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('unknown-id-999');
  });
});
