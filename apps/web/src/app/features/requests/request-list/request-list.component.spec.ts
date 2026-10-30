import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { SessionService } from '../../../core/auth/session.service';
import type { Me, PurchaseRequest, Role } from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import { RequestListComponent } from './request-list.component';

const mockRequests: PurchaseRequest[] = [
  {
    id: 'r1',
    branch_id: 'b1',
    requested_by_membership_id: 'm1',
    required_by_date: '2026-09-20',
    status: 'draft',
    lines: [],
    has_incomplete_estimate: false,
    created_at: '2026-08-23T00:00:00Z',
  },
  {
    id: 'r2',
    branch_id: 'b2',
    requested_by_membership_id: 'm1',
    required_by_date: '2026-09-15',
    status: 'submitted',
    lines: [],
    estimated_total: { amount: '500.0000', currency: 'GBP' },
    has_incomplete_estimate: true,
    created_at: '2026-08-23T10:00:00Z',
    submitted_at: '2026-08-23T11:00:00Z',
  },
];

describe('RequestListComponent (T017)', () => {
  const currentMember = signal<Pick<Me, 'id' | 'membership_id'> | null>(null);
  const role = signal<Role | null>(null);
  let component: RequestListComponent;
  let fixture: ComponentFixture<RequestListComponent>;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    currentMember.set({ id: 'user-1', membership_id: 'm1' });
    role.set('buyer');
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'listRequests',
      'withdrawRequest',
      'withdrawGroup',
    ]);
    organisationApi = jasmine.createSpyObj('OrganisationApiService', ['listBranches']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);

    requestsApi.listRequests.and.returnValue(of({ items: mockRequests, next_cursor: null }));
    organisationApi.listBranches.and.returnValue(
      of({
        items: [
          { id: 'b1', name: 'North Branch', is_active: true, created_at: '2026-01-01T00:00:00Z' },
          { id: 'b2', name: 'South Branch', is_active: true, created_at: '2026-01-01T00:00:00Z' },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [RequestListComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: SessionService, useValue: { currentMember, role } },
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrganisationApiService, useValue: organisationApi },
      ],
    })
      .overrideComponent(RequestListComponent, {
        set: {
          providers: [
            { provide: MatSnackBar, useValue: snackBarSpy },
            { provide: Router, useValue: routerSpy },
            { provide: MatDialog, useValue: dialogSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(RequestListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load requests on init', () => {
    expect(requestsApi.listRequests).toHaveBeenCalledWith({ status: undefined });
    expect(organisationApi.listBranches).toHaveBeenCalledWith({ limit: 100 });
    expect(component.requests().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should display branch names instead of raw branch IDs when lookup data is available', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('New request');
    expect(compiled.textContent).toContain('North Branch');
    expect(compiled.textContent).toContain('South Branch');
    expect(compiled.textContent).not.toContain('b1');
    expect(compiled.textContent).not.toContain('b2');
  });

  it('should fall back to the branch ID when a branch lookup is missing', () => {
    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));

    component.loadRequests();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('b1');
  });

  it('renders a Supplier column placed after Branch, showing source.supplier_name or —', () => {
    expect(component.displayedColumns).toEqual([
      'requiredByDate',
      'branch',
      'supplier',
      'status',
      'estimatedTotal',
      'actions',
    ]);

    requestsApi.listRequests.and.returnValue(
      of({
        items: [
          {
            ...mockRequests[0],
            source: {
              rfq_id: 'rfq-1',
              rfq_response_id: 'resp-1',
              quotation_id: 'q-1',
              supplier_id: 'sup-1',
              supplier_name: 'الوفرة للمواد الغذائية',
            },
          },
          mockRequests[1],
        ],
        next_cursor: null,
      }),
    );
    component.loadRequests();
    fixture.detectChanges();

    const header = fixture.nativeElement.querySelector('th.mat-column-supplier');
    expect(header?.textContent?.trim()).toBe('Supplier');

    const cells = fixture.nativeElement.querySelectorAll('td.mat-column-supplier');
    expect(cells.length).toBe(2);
    expect(cells[0].textContent?.trim()).toBe('الوفرة للمواد الغذائية');
    expect(cells[0].getAttribute('dir')).toBe('auto');
    expect(cells[1].textContent?.trim()).toBe('—');
  });

  it('marks a guardrail-prepared request and leaves manual ones unmarked', () => {
    requestsApi.listRequests.and.returnValue(
      of({
        items: [
          {
            ...mockRequests[0],
            source_rfq_response_id: 'resp-1',
            auto_prepared: {
              guardrail_id: 'g1',
              rfq_id: 'rfq1',
              supplier_id: 's1',
              supplier_name: 'Nile Bakery',
              created_at: '2026-10-18T09:00:00Z',
            },
          },
          mockRequests[1],
        ],
        next_cursor: null,
      }),
    );
    component.loadRequests();
    fixture.detectChanges();

    const badges = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '[data-testid="auto-prepared-badge"]',
    );
    expect(badges.length).toBe(1);
    expect(badges[0].textContent?.trim()).toBe('Auto-prepared');
    expect(badges[0].getAttribute('title')).toBe(
      "Prepared automatically by a guardrail from Nile Bakery's quote",
    );
  });

  it('should show the empty state when no requests exist', () => {
    requestsApi.listRequests.and.returnValue(of({ items: [], next_cursor: null }));
    component.loadRequests();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.empty-state')).toBeTruthy();
    expect(compiled.querySelector('.requests-table')).toBeNull();
  });

  it('should navigate to create on button click', () => {
    component.navigateToCreate();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests/new']);
  });

  it('should navigate to detail on row click', () => {
    component.navigateToDetail(mockRequests[0]);
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
  });

  it('should expose create-order only for requests with an approved approval step', () => {
    expect(
      component.canCreateOrder({
        ...mockRequests[1],
        id: 'ordered-with-approval',
        status: 'ordered',
        approval_step: {
          id: 'step-1',
          assigned_membership_id: 'm1',
          source: 'owner_fallback',
          status: 'approved',
          decided_by_membership_id: 'm1',
          decided_at: '2026-09-30T00:00:00Z',
        },
      }),
    ).toBeTrue();
    expect(component.canCreateOrder({ ...mockRequests[1], status: 'ordered' })).toBeFalse();
  });

  describe('create-order action button / shopping_cart icon visibility (PPS-132)', () => {
    const approvedStep = {
      id: 'step-1',
      assigned_membership_id: 'm1',
      source: 'owner_fallback' as const,
      status: 'approved' as const,
      decided_by_membership_id: 'm1',
      decided_at: '2026-09-30T00:00:00Z',
    };

    const pendingStep = {
      id: 'step-2',
      assigned_membership_id: 'm1',
      source: 'owner_fallback' as const,
      status: 'pending' as const,
    };

    const getCartButton = (): HTMLButtonElement | null =>
      fixture.nativeElement.querySelector('button[aria-label="Create Order"]');

    const getCartIcon = (): HTMLElement | null => {
      const root = fixture.nativeElement as HTMLElement;
      const icons = Array.from(root.querySelectorAll<HTMLElement>('mat-icon'));
      return icons.find((el) => el.textContent?.trim() === 'shopping_cart') ?? null;
    };

    it('shows the cart icon when step is approved, status is ordered, and has_quantity_to_order is true', () => {
      const req: PurchaseRequest = {
        ...mockRequests[0],
        status: 'ordered',
        approval_step: approvedStep,
        has_quantity_to_order: true,
      };
      component.requests.set([req]);
      fixture.detectChanges();

      expect(component.canCreateOrder(req)).toBeTrue();
      expect(getCartButton()).toBeTruthy();
      expect(getCartIcon()?.textContent?.trim()).toBe('shopping_cart');
    });

    it('hides the cart icon when step is approved, status is ordered, and has_quantity_to_order is false', () => {
      const req: PurchaseRequest = {
        ...mockRequests[0],
        status: 'ordered',
        approval_step: approvedStep,
        has_quantity_to_order: false,
      };
      component.requests.set([req]);
      fixture.detectChanges();

      expect(component.canCreateOrder(req)).toBeFalse();
      expect(getCartButton()).toBeNull();
    });

    it('shows the cart icon when step is approved, status is ordered, and has_quantity_to_order is missing', () => {
      const req: PurchaseRequest = {
        ...mockRequests[0],
        status: 'ordered',
        approval_step: approvedStep,
      };
      component.requests.set([req]);
      fixture.detectChanges();

      expect(component.canCreateOrder(req)).toBeTrue();
      expect(getCartButton()).toBeTruthy();
      expect(getCartIcon()?.textContent?.trim()).toBe('shopping_cart');
    });

    it('hides the cart icon when status is withdrawn even with an approved step', () => {
      const req: PurchaseRequest = {
        ...mockRequests[0],
        status: 'withdrawn',
        approval_step: approvedStep,
      };
      component.requests.set([req]);
      fixture.detectChanges();

      expect(component.canCreateOrder(req)).toBeFalse();
      expect(getCartButton()).toBeNull();
    });

    it('hides the cart icon when approval step is pending', () => {
      const req: PurchaseRequest = {
        ...mockRequests[0],
        status: 'submitted',
        approval_step: pendingStep,
      };
      component.requests.set([req]);
      fixture.detectChanges();

      expect(component.canCreateOrder(req)).toBeFalse();
      expect(getCartButton()).toBeNull();
    });
  });

  it('shows Withdraw on an ordered request and hides it on terminal requests', () => {
    for (const status of ['ordered', 'withdrawn', 'rejected', 'approved'] as const) {
      component.requests.set([{ ...mockRequests[0], status }]);
      fixture.detectChanges();
      const element = fixture.nativeElement as HTMLElement;
      expect(Boolean(element.querySelector('button.danger-action'))).toBe(status === 'ordered');
    }
  });

  it('asks for confirmation and leaves the request unchanged when cancelled', () => {
    dialogSpy.open.and.returnValue({ afterClosed: () => of(false) } as ReturnType<MatDialog['open']>);
    requestsApi.withdrawRequest.and.returnValue(of(mockRequests[0]));
    component.withdrawRequest({ ...mockRequests[0], status: 'ordered' });
    expect(dialogSpy.open).toHaveBeenCalled();
    expect(requestsApi.withdrawRequest).not.toHaveBeenCalled();
  });

  it('should withdraw a request and reload', () => {
    requestsApi.withdrawRequest.and.returnValue(
      of({ ...mockRequests[0], status: 'withdrawn' } as PurchaseRequest),
    );

    component.withdrawRequest(mockRequests[0]);

    expect(requestsApi.withdrawRequest).toHaveBeenCalledWith('r1');
    expect(requestsApi.listRequests).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request withdrawn.',
      undefined,
      { duration: 3500 },
    );
  });

  for (const scenario of [
    { label: 'requester', memberId: 'm1', role: 'buyer', visible: true },
    { label: 'owner', memberId: 'm2', role: 'owner', visible: true },
    { label: 'another buyer', memberId: 'm2', role: 'buyer', visible: false },
  ] as const) {
    it(`shows ordered Withdraw only when permitted: ${scenario.label}`, () => {
      currentMember.set({ id: 'user-1', membership_id: scenario.memberId });
      role.set(scenario.role);
      component.requests.set([{ ...mockRequests[0], status: 'ordered' }]);
      fixture.detectChanges();

      const button = (fixture.nativeElement as HTMLElement).querySelector(
        'button[aria-label="Withdraw request"]',
      );
      expect(button !== null).toBe(scenario.visible);
    });
  }

  it('keeps draft and submitted Withdraw visible for another buyer', () => {
    currentMember.set({ id: 'user-2', membership_id: 'm2' });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelectorAll(
      'button[aria-label="Withdraw request"]',
    ).length).toBe(2);
  });

  it('should filter by status', () => {
    component.onStatusFilterChange('submitted');
    expect(requestsApi.listRequests).toHaveBeenCalledWith({ status: 'submitted' });
  });

  it('should format money from estimated_total', () => {
    expect(component.formatMoney(mockRequests[0])).toBe('—');
    expect(component.formatMoney(mockRequests[1])).toBe('GBP 500');
    expect(
      component.formatMoney({
        ...mockRequests[1],
        estimated_total: { amount: '56425.0000', currency: 'EGP' },
      }),
    ).toBe('EGP 56,425');
  });

  it('should show the incomplete estimate badge for flagged requests', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const badges = compiled.querySelectorAll('.incomplete-badge');
    expect(badges.length).toBe(1);
  });

  it('should display an error message on API failure', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Boom', trace_id: 'tr_err' },
    });
    requestsApi.listRequests.and.returnValue(throwError(() => error500));

    component.loadRequests();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('Boom');
    expect(component.errorTraceId()).toBe('tr_err');
  });

  it('formats required-by date with locale sensitivity in en and ar', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const dateCell = compiled.querySelector('td.cdk-column-requiredByDate, td.mat-column-requiredByDate');
    expect(dateCell?.textContent?.trim()).toBe('Sep 20, 2026');
    expect(component.formatRequiredBy('2026-09-20')).toBe('Sep 20, 2026');

    TestBed.inject(TranslateService).use('ar');
    fixture.detectChanges();

    expect(dateCell?.textContent).toContain('٢٠');
    expect(dateCell?.textContent).toContain('٢٠٢٦');
    expect(/[0-9]/.test(dateCell?.textContent ?? '')).toBeFalse();
    expect(component.formatRequiredBy('2026-09-20')).toContain('٢٠');
    expect(/[0-9]/.test(component.formatRequiredBy('2026-09-20'))).toBeFalse();
  });

  // Guards PPS-60: in Arabic, the Required By date suffered a sub-pixel overflow
  // under Material's table ellipsis. Setting overflow: visible prevents the clip
  // without distorting column widths. The clip itself depends on real font metrics
  // and is verified by the landing-gallery capture.
  it('prevents clipping on the Required By cell via date-cell styling', () => {
    const cell = fixture.nativeElement.querySelector('td.mat-column-requiredByDate') as HTMLElement;
    expect(cell).toBeTruthy();
    expect(cell.classList.contains('date-cell')).toBeTrue();
    expect(getComputedStyle(cell).overflow).toBe('visible');
  });

  describe('Spec 024 User Story 3 (T030) — Grouped requests in list', () => {
    const groupedListRequest: PurchaseRequest = {
      ...mockRequests[0],
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

    it('shows a small "Split 1 of 2" marker on grouped rows', () => {
      requestsApi.listRequests.and.returnValue(of({ items: [groupedListRequest], next_cursor: null }));
      component.loadRequests();
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const marker = compiled.querySelector('.split-badge, [data-testid="split-badge"]');
      expect(marker).toBeTruthy();
      expect(marker?.textContent).toContain('Split 1 of 2');
    });

    it('Withdraw on a grouped request calls withdrawGroup and says "Withdraws both requests of this split"', () => {
      requestsApi.listRequests.and.returnValue(of({ items: [groupedListRequest], next_cursor: null }));
      requestsApi.withdrawGroup.and.returnValue(of([groupedListRequest]));
      component.loadRequests();
      fixture.detectChanges();

      component.withdrawRequest(groupedListRequest);

      expect(dialogSpy.open).toHaveBeenCalled();
      const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as {
        titleKey?: string;
        messageKey?: string;
        confirmKey?: string;
      };
      expect(dialogData?.confirmKey).toBe('requests.split.withdrawBoth');
      // Dialog message or confirmation references withdrawing both requests
      expect(requestsApi.withdrawGroup).toHaveBeenCalledWith('grp-001', jasmine.any(String));
      expect(requestsApi.withdrawRequest).not.toHaveBeenCalled();
    });

    it('part_of_split shows the message pointing to the group action', () => {
      requestsApi.listRequests.and.returnValue(of({ items: [mockRequests[0]], next_cursor: null }));
      const errorResp = new HttpErrorResponse({
        error: { code: 'conflict', message: 'Conflict', details: { reason: 'part_of_split' } },
        status: 409,
        statusText: 'Conflict',
      });
      requestsApi.withdrawRequest.and.returnValue(throwError(() => errorResp));

      component.loadRequests();
      fixture.detectChanges();

      component.withdrawRequest(mockRequests[0]);

      expect(snackBarSpy.open).toHaveBeenCalled();
      const snackMsg = snackBarSpy.open.calls.mostRecent().args[0];
      expect(snackMsg.toLowerCase()).toContain('split');
    });
  });
});
