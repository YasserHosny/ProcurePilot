import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Member, PurchaseRequest } from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import { RequestFormComponent } from './request-form.component';

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
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'createRequest',
      'updateRequest',
      'submitRequest',
      'getRequest',
    ]);
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);

    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.members.and.returnValue(of({ items: [], next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [RequestFormComponent, TranslateModule.forRoot()],
      providers: [
        { provide: RequestsApiService, useValue: requestsApi },
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

  it('should start with one empty line in create mode', () => {
    expect(component.isEditMode()).toBeFalse();
    expect(component.lines.length).toBe(1);
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
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'createRequest',
      'updateRequest',
      'submitRequest',
      'getRequest',
    ]);
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);

    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.members.and.returnValue(of({ items: [], next_cursor: null }));
    requestsApi.getRequest.and.returnValue(of(mockRequest));

    await TestBed.configureTestingModule({
      imports: [RequestFormComponent, TranslateModule.forRoot()],
      providers: [
        { provide: RequestsApiService, useValue: requestsApi },
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

  it('should load the existing request and pre-fill the form', () => {
    expect(requestsApi.getRequest).toHaveBeenCalledWith('r1');
    expect(component.isEditMode()).toBeTrue();
    expect(component.form.controls.branch_id.value).toBe('b1');
    expect(component.form.controls.cost_centre_id.value).toBe('cc1');
    expect(component.form.controls.required_by_date.value).toBe('2026-09-15');
    expect(component.lines.length).toBe(1);
    expect(component.lines.at(0).controls.workspace_product_id.value).toBe('wp1');
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

  it('should submit the request and navigate to the list', () => {
    requestsApi.submitRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    component.submitRequest();

    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests']);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request submitted for approval.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should display the estimate for a line with price history', () => {
    expect(component.formatEstimate(mockRequest.lines[0])).toBe('GBP 25.5000');
  });

  it('should display a fallback for a line without price history', () => {
    const noEstimateLine = { id: 'l2', workspace_product_id: 'wp2', quantity: '5.000000' };
    expect(component.formatEstimate(noEstimateLine)).toBe(
      'No price history available for this product.',
    );
  });

  it('should disable the form when viewing a non-draft request', async () => {
    requestsApi.getRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    const submittedRoute = TestBed.createComponent(RequestFormComponent);
    submittedRoute.detectChanges();

    expect(submittedRoute.componentInstance.form.disabled).toBeTrue();
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
        remaining_amount: { amount: '75.0000', currency: 'GBP' },
        exceeds: true,
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
    expect(warningBanner?.textContent).toContain('GBP 75.0000');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
  });

  it('should display quiet remaining budget status when budget_status exists and exceeds is false', () => {
    const withinBudgetRequest: PurchaseRequest = {
      ...mockRequest,
      budget_status: {
        remaining_amount: { amount: '500.0000', currency: 'GBP' },
        exceeds: false,
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
    expect(budgetRow?.textContent).toContain('GBP 500.0000');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
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
});
