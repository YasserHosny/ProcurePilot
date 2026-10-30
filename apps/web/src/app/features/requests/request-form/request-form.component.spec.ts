import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink, provideRouter } from '@angular/router';
import { By } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, Subject, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { BranchList, Member, PurchaseRequest } from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import { OrdersApiService } from '../../orders/orders-api';
import { RequestFormComponent } from './request-form.component';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';

const mockRequest: PurchaseRequest = {
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
      quantity: '10.000000',
      estimated_unit_price: { amount: '25.5000', currency: 'GBP' },
      estimated_unit_price_source_landed_cost_id: 'lc1',
    },
  ],
  has_incomplete_estimate: false,
  created_at: '2026-08-23T00:00:00Z',
};

describe('RequestFormComponent — create mode (T017)', () => {
  let component: RequestFormComponent;
  let fixture: ComponentFixture<RequestFormComponent>;
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
        lines: [
          {
            source_request_line_id: 'l1',
            requested_quantity: '10.000000',
            allocated_quantity: '0',
            remaining_quantity: '10.000000',
          },
        ],
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
          useValue: { snapshot: { paramMap: { get: () => null } } },
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

    fixture = TestBed.createComponent(RequestFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('filters cost centres to the selected branch and keeps tenant-wide centres', () => {
    component.allCostCentres.set([
      { id: 'global', name: 'Global', code: 'G', branch_id: null, is_orphaned: false, is_archived: false, created_at: '' },
      { id: 'b1cc', name: 'Branch 1', code: '1', branch_id: 'b1', is_orphaned: false, is_archived: false, created_at: '' },
      { id: 'b2cc', name: 'Branch 2', code: '2', branch_id: 'b2', is_orphaned: false, is_archived: false, created_at: '' },
    ]);
    component.form.controls.branch_id.setValue('b1');
    expect(component.costCentres().map((centre) => centre.id)).toEqual(['global', 'b1cc']);
    component.form.controls.cost_centre_id.setValue('b1cc');
    component.form.controls.branch_id.setValue('b2');
    expect(component.costCentres().map((centre) => centre.id)).toEqual(['global', 'b2cc']);
    expect(component.form.controls.cost_centre_id.value).toBe('');
  });

  it('should start with one empty line in create mode', () => {
    expect(component.isEditMode()).toBeFalse();
    expect(component.lines.length).toBe(1);
  });

  it('should keep the form gated until branch options finish loading', () => {
    const delayedBranches$ = new Subject<BranchList>();
    organisationApi.listBranches.and.returnValue(delayedBranches$);

    const delayedFixture = TestBed.createComponent(RequestFormComponent);
    const delayedComponent = delayedFixture.componentInstance;
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeTrue();
    expect(delayedFixture.nativeElement.querySelector('.loading-state')).not.toBeNull();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).toBeNull();

    delayedBranches$.next({
      items: [{ id: 'b1', name: 'Main branch', is_active: true, created_at: '2026-01-01T00:00:00Z' }],
      next_cursor: null,
    });
    delayedBranches$.complete();
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeFalse();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).not.toBeNull();
  });

  it('should add and remove lines', () => {
    component.addLine();
    expect(component.lines.length).toBe(2);

    component.removeLine(0);
    expect(component.lines.length).toBe(1);
  });

  it('should save a draft and navigate to the detail', () => {
    requestsApi.createRequest.and.returnValue(of(mockRequest));

    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');
    component.lines.at(0).controls.workspace_product_id.setValue('wp1');
    component.lines.at(0).controls.quantity.setValue('10');

    component.saveDraft();

    expect(requestsApi.createRequest).toHaveBeenCalledTimes(1);
    expect(component.isSaving()).toBeFalse();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request saved as a draft.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should not save when form is invalid', () => {
    component.saveDraft();
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('should not save when lines are empty', () => {
    component.removeLine(0);
    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');

    component.saveDraft();
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('should display an error on API failure', () => {
    const error422 = new HttpErrorResponse({
      status: 422,
      error: { code: 'unprocessable', message: 'Zero lines', trace_id: 'tr_422' },
    });
    requestsApi.createRequest.and.returnValue(throwError(() => error422));

    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');
    component.lines.at(0).controls.workspace_product_id.setValue('wp1');
    component.lines.at(0).controls.quantity.setValue('5');

    component.saveDraft();

    expect(component.errorMessage()).toBe('Zero lines');
    expect(component.isSaving()).toBeFalse();
  });

  it('should cancel and navigate back', () => {
    component.cancel();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests']);
  });
});

describe('RequestFormComponent — edit mode (T017)', () => {
  let component: RequestFormComponent;
  let fixture: ComponentFixture<RequestFormComponent>;
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
        lines: [
          {
            source_request_line_id: 'l1',
            requested_quantity: '10.000000',
            allocated_quantity: '0',
            remaining_quantity: '10.000000',
          },
        ],
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
            tenant_name: 'Nitrile Gloves',
            canonical_name: 'Gloves',
            base_unit: 'each',
            pack: { pack_count: 1, unit_size: '1.000000' },
            status: 'active',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    requestsApi.getRequest.and.returnValue(of(mockRequest));
    requestsApi.updateRequest.and.returnValue(of(mockRequest));

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

    fixture = TestBed.createComponent(RequestFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('preserves all decimal digits when prefilling an editable quantity', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, lines: [
      { ...mockRequest.lines[0], quantity: '999999999999.999999' },
    ] }));
    const editFixture = TestBed.createComponent(RequestFormComponent);
    editFixture.detectChanges();
    expect(editFixture.componentInstance.lines.at(0).controls.quantity.value)
      .toBe('999999999999.999999');
  });

  it('should load the existing request and pre-fill the form', () => {
    expect(requestsApi.getRequest).toHaveBeenCalledWith('r1');
    expect(component.isEditMode()).toBeTrue();
    expect(component.form.controls.branch_id.value).toBe('b1');
    expect(component.form.controls.cost_centre_id.value).toBe('cc1');
    expect(component.form.controls.required_by_date.value).toEqual(new Date(2026, 8, 15));
    expect(component.lines.length).toBe(1);
    expect(component.lines.at(0).controls.workspace_product_id.value).toBe('wp1');
    expect(component.products()[0]?.tenant_name).toBe('Nitrile Gloves');
    expect(api.products).toHaveBeenCalledWith({ status: 'all', limit: 100 });
  });

  it('should wait for branches before rendering an edit form with a patched branch', () => {
    const delayedBranches$ = new Subject<BranchList>();
    organisationApi.listBranches.and.returnValue(delayedBranches$);
    requestsApi.getRequest.and.returnValue(of(mockRequest));

    const delayedFixture = TestBed.createComponent(RequestFormComponent);
    const delayedComponent = delayedFixture.componentInstance;
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeTrue();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).toBeNull();

    delayedBranches$.next({
      items: [{ id: 'b1', name: 'Main branch', is_active: true, created_at: '2026-01-01T00:00:00Z' }],
      next_cursor: null,
    });
    delayedBranches$.complete();
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeFalse();
    expect(delayedComponent.form.controls.branch_id.value).toBe('b1');
    expect(delayedFixture.nativeElement.querySelector('mat-select')).not.toBeNull();
  });

  it('should update an existing draft via updateRequest', () => {
    const updated = { ...mockRequest, required_by_date: '2026-10-01' };
    requestsApi.updateRequest.and.returnValue(of(updated));

    component.form.controls.required_by_date.setValue('2026-10-01');
    component.saveDraft();

    expect(requestsApi.updateRequest).toHaveBeenCalledWith('r1', jasmine.objectContaining({
      branch_id: 'b1',
      required_by_date: '2026-10-01',
    }));
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('accepts a typed day-first date, displays day-first format, and emits ISO date in payload', () => {
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector(
      'input[formcontrolname="required_by_date"]'
    ) as HTMLInputElement;
    expect(input).toBeTruthy();

    input.value = '';
    for (const char of '22/10/2026') {
      input.value += char;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    input.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    const val = component.form.controls.required_by_date.value;
    expect(val instanceof Date).toBeTrue();
    if (val instanceof Date) {
      expect([val.getFullYear(), val.getMonth(), val.getDate()]).toEqual([2026, 9, 22]);
    }
    expect(input.value).toBe('22/10/2026');

    component.saveDraft();
    expect(requestsApi.updateRequest).toHaveBeenCalledWith('r1', jasmine.objectContaining({
      required_by_date: '2026-10-22',
    }));
  });

  it('should submit the request and navigate to the list', () => {
    requestsApi.submitRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    component.submitRequest();

    expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests']);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request submitted for approval.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should save dirty valid form before submitting, in order', () => {
    const callOrder: string[] = [];
    requestsApi.updateRequest.and.callFake((id, body) => {
      callOrder.push('save');
      return of({ ...mockRequest, id, cost_centre_id: body.cost_centre_id });
    });
    requestsApi.submitRequest.and.callFake(() => {
      callOrder.push('submit');
      return of({ ...mockRequest, status: 'submitted' } as PurchaseRequest);
    });

    component.form.controls.cost_centre_id.setValue('cc-new');
    component.form.markAsDirty();

    component.submitRequest();

    expect(callOrder).toEqual(['save', 'submit']);
    expect(requestsApi.updateRequest).toHaveBeenCalledWith(
      'r1',
      jasmine.objectContaining({ cost_centre_id: 'cc-new' }),
    );
    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
  });

  it('should call neither save nor submit when form is dirty and invalid', () => {
    requestsApi.updateRequest.calls.reset();
    requestsApi.submitRequest.calls.reset();

    component.form.controls.branch_id.setValue('');
    component.form.controls.branch_id.markAsDirty();
    component.form.markAsDirty();

    component.submitRequest();
    fixture.detectChanges();

    expect(requestsApi.updateRequest).not.toHaveBeenCalled();
    expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    expect(component.form.controls.branch_id.touched).toBeTrue();
  });

  it('should not call submit when save fails before submit', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Failed to save draft', trace_id: 'tr_save_err' },
    });
    requestsApi.updateRequest.and.returnValue(throwError(() => error500));
    requestsApi.submitRequest.calls.reset();

    component.form.controls.cost_centre_id.setValue('cc-fail');
    component.form.markAsDirty();

    component.submitRequest();

    expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
    expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    expect(component.errorMessage()).toBe('Failed to save draft');
    expect(component.isSubmitting()).toBeFalse();
  });

  it('should display the estimate for a line with price history', () => {
    expect(component.formatEstimate(mockRequest.lines[0])).toBe('GBP 25.50');
  });

  it('should display a fallback for a line without price history', () => {
    const noEstimateLine = { id: 'l2', workspace_product_id: 'wp2', quantity: '5.000000' };
    expect(component.formatEstimate(noEstimateLine)).toBe(
      'No price history available for this product.',
    );
  });

  it('should disable the form and show read-only title + status chip when viewing a non-draft request', async () => {
    const compiledDraft = fixture.nativeElement as HTMLElement;
    expect(compiledDraft.querySelector('.form-title')?.textContent?.trim()).toBe(
      'Edit Purchase Request',
    );
    expect(compiledDraft.querySelector('[data-testid="request-status-chip"]')).toBeNull();

    requestsApi.getRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    const submittedRoute = TestBed.createComponent(RequestFormComponent);
    submittedRoute.detectChanges();

    expect(submittedRoute.componentInstance.form.disabled).toBeTrue();
    const compiledSubmitted = submittedRoute.nativeElement as HTMLElement;
    expect(compiledSubmitted.querySelector('.form-title')?.textContent?.trim()).toBe(
      'Purchase Request',
    );
    const chip = compiledSubmitted.querySelector('[data-testid="request-status-chip"]');
    expect(chip).toBeTruthy();
    expect(chip?.textContent?.trim()).toBe('Submitted');

    const qtyInput = compiledSubmitted.querySelector<HTMLInputElement>('.line-quantity input');
    expect(qtyInput?.value).toBe('10');
  });

  it('shows Create purchase order for an approved step on an ordered request', () => {
    const compiledDraft = fixture.nativeElement as HTMLElement;
    expect(compiledDraft.querySelector('[data-testid="request-create-order-btn"]')).toBeNull();

    requestsApi.getRequest.and.returnValue(
      of({ ...mockRequest, status: 'ordered', approval_step: {
        id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'approved',
        decided_by_membership_id: 'm1', decided_at: '2026-10-01T00:00:00Z',
      } } as PurchaseRequest),
    );

    const approvedFixture = TestBed.createComponent(RequestFormComponent);
    approvedFixture.detectChanges();

    const compiledApproved = approvedFixture.nativeElement as HTMLElement;
    const createOrderBtn = compiledApproved.querySelector<HTMLButtonElement>(
      '[data-testid="request-create-order-btn"]',
    );
    expect(createOrderBtn).toBeTruthy();
    expect(createOrderBtn?.textContent).toContain('Create purchase order');
    expect(compiledApproved.querySelector('.form-title')?.textContent?.trim()).toBe('Purchase Request');
    expect(compiledApproved.querySelector('[data-testid="request-status-chip"]')?.textContent?.trim()).toBe('Ordered');

    createOrderBtn?.click();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/orders/new'], {
      queryParams: { source_request_id: 'r1' },
    });
  });

  it('hides Create purchase order while approval is pending', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'submitted', approval_step: {
      id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'pending',
      decided_by_membership_id: null, decided_at: null,
    } } as PurchaseRequest));
    const pendingFixture = TestBed.createComponent(RequestFormComponent);
    pendingFixture.detectChanges();
    expect(pendingFixture.nativeElement.querySelector('[data-testid="request-create-order-btn"]')).toBeNull();
  });

  it('does not show the auto-prepared banner on a manually created request', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="auto-prepared-banner"]')).toBeNull();
  });

  it('tells the owner a guardrail drafted the request from the winning quote', () => {
    requestsApi.getRequest.and.returnValue(
      of({
        ...mockRequest,
        auto_prepared: {
          guardrail_id: 'g1',
          rfq_id: 'rfq1',
          supplier_id: 's1',
          supplier_name: 'Nile Bakery',
          created_at: '2026-10-18T09:00:00Z',
        },
      }),
    );
    const autoFixture = TestBed.createComponent(RequestFormComponent);
    autoFixture.detectChanges();

    const banner = (autoFixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="auto-prepared-banner"]',
    );
    expect(banner).toBeTruthy();
    expect(banner?.textContent).toContain('Prepared automatically by a guardrail');
    expect(banner?.textContent).toContain("from Nile Bakery's quote. Review it and submit it");
  });

  it('should not display budget status block when budget_status is absent', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();
    expect(compiled.querySelector('.budget-status-row')).toBeNull();
  });

  it('should display informational warning with remaining budget when budget_status.exceeds is true without disabling submit', () => {
    const exceedingRequest: PurchaseRequest = {
      ...mockRequest,
      budget_status: {
        status: 'over',
        remaining_amount: { amount: '75.0000', currency: 'GBP' },
        exceeds: true,
        reason_code: 'budget_exceeded',
      },
    };
    requestsApi.getRequest.and.returnValue(of(exceedingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const warningBanner = compiled.querySelector('.budget-warning-banner');
    expect(warningBanner).toBeTruthy();
    expect(warningBanner?.textContent).toContain(
      'This request would exceed the remaining budget for its scope.',
    );
    expect(warningBanner?.textContent).toContain('Remaining budget');
    expect(warningBanner?.textContent).toContain('GBP 75');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
  });

  it('should display quiet remaining budget status when budget_status exists and exceeds is false', () => {
    const withinBudgetRequest: PurchaseRequest = {
      ...mockRequest,
      budget_status: {
        status: 'within',
        remaining_amount: { amount: '500.0000', currency: 'GBP' },
        exceeds: false,
        reason_code: null,
      },
    };
    requestsApi.getRequest.and.returnValue(of(withinBudgetRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();

    const budgetRow = compiled.querySelector('.budget-status-row');
    expect(budgetRow).toBeTruthy();
    expect(budgetRow?.textContent).toContain('Remaining budget');
    expect(budgetRow?.textContent).toContain('GBP 500');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
  });

  it('does not render a budget row or warning when there is no budget', () => {
    requestsApi.getRequest.and.returnValue(of({
      ...mockRequest,
      budget_status: {
        status: 'no_budget',
        remaining_amount: null,
        exceeds: false,
        reason_code: 'no_budget',
      },
    } as PurchaseRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();
    expect(compiled.querySelector('.budget-status-row')).toBeNull();
  });

  it('should not render an approval section when the request has no approval_step', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.approval-step')).toBeNull();
  });

  it('should render a pending approval_step with assigned approver email and no comment/decided-at', () => {
    const approverMember = { id: 'm-approver', email: 'approver@example.com' } as Member;
    api.members.and.returnValue(of({ items: [approverMember], next_cursor: null }));

    const pendingRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'submitted',
      approval_step: {
        id: 'as1',
        assigned_membership_id: 'm-approver',
        source: 'threshold_match',
        status: 'pending',
      },
    };
    requestsApi.getRequest.and.returnValue(of(pendingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('Approval');
    expect(section?.textContent).toContain('Pending approval');
    expect(section?.textContent).toContain('Assigned to');
    expect(section?.textContent).toContain('approver@example.com');
    expect(section?.textContent).not.toContain('Decision comment');
    expect(section?.textContent).not.toContain('Decided on');

    const chip = section?.querySelector('.status-chip');
    expect(chip?.getAttribute('data-status')).toBe('pending');
    expect(chip?.textContent).toContain('Pending');
  });

  it('should render an approved approval_step with comment and decided-at', () => {
    const approverMember = { id: 'm-approver', email: 'approver@example.com' } as Member;
    api.members.and.returnValue(of({ items: [approverMember], next_cursor: null }));

    const approvedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'approved',
      approval_step: {
        id: 'as2',
        assigned_membership_id: 'm-approver',
        source: 'threshold_match',
        status: 'approved',
        comment: 'Budget confirmed.',
        decided_by_membership_id: 'm-approver',
        decided_at: '2026-09-10T12:00:00Z',
      },
    };
    requestsApi.getRequest.and.returnValue(of(approvedRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('Decision comment');
    expect(section?.textContent).toContain('Budget confirmed.');
    expect(section?.textContent).toContain('Decided on');
    expect(section?.textContent).toContain('Sep 10, 2026');

    const chip = section?.querySelector('.status-chip');
    expect(chip?.getAttribute('data-status')).toBe('approved');
    expect(chip?.textContent).toContain('Approved');
  });

  it('should fall back to the raw membership id when the approver is not in the members list', () => {
    api.members.and.returnValue(of({ items: [], next_cursor: null }));

    const pendingRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'submitted',
      approval_step: {
        id: 'as3',
        assigned_membership_id: 'unknown-approver-id',
        source: 'owner_fallback',
        status: 'pending',
      },
    };
    requestsApi.getRequest.and.returnValue(of(pendingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section?.textContent).toContain('unknown-approver-id');
  });

  it('renders a source line linking to RFQ and quote and naming the supplier with dir="auto"', () => {
    const sourcedRequest: PurchaseRequest = {
      ...mockRequest,
      source: {
        rfq_id: 'rfq-123',
        rfq_response_id: 'resp-456',
        quotation_id: 'quote-789',
        supplier_id: 'sup-1',
        supplier_name: 'الوفرة للمواد الغذائية',
      },
    };
    requestsApi.getRequest.and.returnValue(of(sourcedRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const sourceLine = compiled.querySelector('[data-testid="request-source-line"]');
    expect(sourceLine).toBeTruthy();
    expect(sourceLine?.textContent).toContain('الوفرة للمواد الغذائية');

    const supplierSpan = sourceLine?.querySelector('.source-supplier');
    expect(supplierSpan?.getAttribute('dir')).toBe('auto');

    const linkDirectives = hostFixture.debugElement.queryAll(By.directive(RouterLink));
    expect(linkDirectives.length).toBe(2);
    const getLinkInput = (dir: typeof linkDirectives[0]) =>
      (dir.injector.get(RouterLink) as unknown as Record<string, () => unknown>)['routerLinkInput']();
    expect(getLinkInput(linkDirectives[0])).toEqual(['/rfq', 'rfq-123']);
    expect(getLinkInput(linkDirectives[1])).toEqual(['/quotations', 'quote-789', 'review']);
  });

  describe('Spec 024 User Story 3 (T030) — Grouped request', () => {
    const groupedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'draft',
      request_group: {
        id: 'grp-001',
        rfq_id: 'rfq-split-001',
        position: 1,
        size: 2,
        combined_total: { amount: '4063.00', currency: 'SAR' },
        best_single_total: { amount: '4137.00', currency: 'SAR' },
        saving: { amount: '74.00', currency: 'SAR' },
        sibling_request_ids: ['r2'],
      },
    };

    it('shows 1 of 2 and links to sibling request', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('1 of 2');
      expect(compiled.textContent).toContain('Part of a split');
      expect(compiled.textContent).toContain('4,063');

      const siblingLinks = compiled.querySelectorAll('a.sibling-link');
      expect(siblingLinks.length).toBe(1);
    });

    it('a grouped draft renders read-only with no Save and explains why', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const comp = hostFixture.componentInstance;
      const compiled = hostFixture.nativeElement as HTMLElement;

      expect(comp.isReadOnly()).toBeTrue();
      expect(comp.form.disabled).toBeTrue();
      expect(compiled.querySelector('button[type="submit"]')).toBeNull();
      expect(compiled.textContent).toContain(
        'Part of a split: these requests are submitted and approved together',
      );
      expect(compiled.querySelector('.submit-request-btn')).toBeTruthy();
    });

    it('Submit calls submitGroup once directly and never updateRequest', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      requestsApi.submitGroup.and.returnValue(of([groupedRequest]));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;
      expect(submitBtn).toBeTruthy();
      expect(submitBtn.textContent).toContain('Submits both requests of this split');

      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(1);
      expect(requestsApi.submitGroup.calls.mostRecent().args[0]).toBe('grp-001');
      expect(requestsApi.submitGroup.calls.mostRecent().args[1]).toEqual(jasmine.any(String));
      expect(requestsApi.updateRequest).not.toHaveBeenCalled();
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    });

    it('a retry after an error reuses the same key', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      requestsApi.submitGroup.and.returnValue(throwError(() => new Error('Network error')));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;

      // First click -> error
      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(1);
      const firstKey = requestsApi.submitGroup.calls.mostRecent().args[1];
      expect(firstKey).toBeTruthy();

      // Retry click -> reuses key
      requestsApi.submitGroup.and.returnValue(of([groupedRequest]));
      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(2);
      const retryKey = requestsApi.submitGroup.calls.mostRecent().args[1];
      expect(retryKey).toBe(firstKey);
    });

    it('withdraw retry after an error reuses the same key', () => {
      const submittedGrouped = { ...groupedRequest, status: 'submitted' as const };
      requestsApi.getRequest.and.returnValue(of(submittedGrouped));
      requestsApi.withdrawGroup.and.returnValue(throwError(() => new Error('Server error')));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const withdrawBtn = compiled.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();

      // First click -> error
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.withdrawGroup).toHaveBeenCalledTimes(1);
      const firstKey = requestsApi.withdrawGroup.calls.mostRecent().args[1];
      expect(firstKey).toBeTruthy();

      // Retry click -> reuses key
      requestsApi.withdrawGroup.and.returnValue(of([submittedGrouped]));
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.withdrawGroup).toHaveBeenCalledTimes(2);
      const retryKey = requestsApi.withdrawGroup.calls.mostRecent().args[1];
      expect(retryKey).toBe(firstKey);
    });

    it('part_of_split shows the message pointing to the group action', () => {
      requestsApi.getRequest.and.returnValue(of(mockRequest));
      requestsApi.updateRequest.and.returnValue(of(mockRequest));
      const errorResp = new HttpErrorResponse({
        error: { code: 'conflict', message: 'Conflict', details: { reason: 'part_of_split' } },
        status: 409,
        statusText: 'Conflict',
      });
      requestsApi.submitRequest.and.returnValue(throwError(() => errorResp));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;
      submitBtn.click();
      hostFixture.detectChanges();

      expect(hostFixture.componentInstance.errorMessage()).toBeTruthy();
      expect(compiled.querySelector('.error-banner')?.textContent?.toLowerCase()).toContain('split');
    });
  });

  describe('PPS-119: offer Create purchase order only while something is left', () => {
    const baseApprovedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'approved',
      approval_step: {
        id: 'step1',
        assigned_membership_id: 'm1',
        source: 'owner_fallback',
        status: 'approved',
        decided_by_membership_id: 'm1',
        decided_at: '2026-10-01T00:00:00Z',
      },
    };

    it('approved request with (none ordered) → button, no PO row', () => {
      requestsApi.getRequest.and.returnValue(of(baseApprovedRequest));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '0',
              remaining_quantity: '10',
            },
          ],
          orders: [],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeNull();
    });

    it('(partly ordered) → button and PO-000005 link', () => {
      requestsApi.getRequest.and.returnValue(of({ ...baseApprovedRequest, status: 'ordered' }));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '4',
              remaining_quantity: '6',
            },
          ],
          orders: [
            {
              id: 'po-5',
              order_number: 'PO-000005',
              status: 'draft',
            },
          ],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeTruthy();

      const link = Array.from((f.nativeElement as HTMLElement).querySelectorAll('a')).find((a) =>
        a.textContent?.includes('PO-000005'),
      );
      expect(link).toBeTruthy();
    });

    it('(fully ordered) → no button, link, ordered text', () => {
      requestsApi.getRequest.and.returnValue(of({ ...baseApprovedRequest, status: 'ordered' }));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '10',
              remaining_quantity: '0',
            },
          ],
          orders: [
            {
              id: 'po-5',
              order_number: 'PO-000005',
              status: 'draft',
            },
          ],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeNull();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeTruthy();

      const link = Array.from((f.nativeElement as HTMLElement).querySelectorAll('a')).find((a) =>
        a.textContent?.includes('PO-000005'),
      );
      expect(link).toBeTruthy();

      const orderedText = f.nativeElement.querySelector('[data-testid="request-fully-ordered-text"]');
      expect(orderedText).toBeTruthy();
      expect(orderedText?.textContent).toContain('Everything on this request has been ordered.');
    });

    it('(allocation call fails) → button', () => {
      requestsApi.getRequest.and.returnValue(of(baseApprovedRequest));
      ordersApi.getAllocations.and.returnValue(throwError(() => new Error('Failed to load allocations')));

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();
    });

    it('(status withdrawn with an approved step) → no button', () => {
      requestsApi.getRequest.and.returnValue(
        of({
          ...baseApprovedRequest,
          status: 'withdrawn',
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeNull();
      expect(ordersApi.getAllocations).not.toHaveBeenCalled();
    });
  });
});
