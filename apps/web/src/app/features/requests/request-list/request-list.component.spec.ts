import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { PurchaseRequest } from '../../../core/api/models';
import { RequestsApiService } from '../requests-api';
import { RequestListComponent } from './request-list.component';

const mockRequests: PurchaseRequest[] = [
  {
    id: 'r1',
    branch_id: 'b1',
    requested_by_membership_id: 'm1',
    required_by_date: '2026-09-01',
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
  let component: RequestListComponent;
  let fixture: ComponentFixture<RequestListComponent>;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'listRequests',
      'withdrawRequest',
    ]);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);

    requestsApi.listRequests.and.returnValue(of({ items: mockRequests, next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [RequestListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: RequestsApiService, useValue: requestsApi },
      ],
    })
      .overrideComponent(RequestListComponent, {
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

    fixture = TestBed.createComponent(RequestListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load requests on init', () => {
    expect(requestsApi.listRequests).toHaveBeenCalledWith({ status: undefined });
    expect(component.requests().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
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

  it('should filter by status', () => {
    component.onStatusFilterChange('submitted');
    expect(requestsApi.listRequests).toHaveBeenCalledWith({ status: 'submitted' });
  });

  it('should format money from estimated_total', () => {
    expect(component.formatMoney(mockRequests[0])).toBe('—');
    expect(component.formatMoney(mockRequests[1])).toBe('GBP 500.0000');
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
});
