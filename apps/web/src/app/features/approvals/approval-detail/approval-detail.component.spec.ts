import { HttpErrorResponse } from '@angular/common/http';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, of, Subject, throwError } from 'rxjs';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApiService } from '../../../core/api/api.service';
import type { PurchaseRequest } from '../../../core/api/models';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { ApprovalDetailComponent } from './approval-detail.component';

const request: PurchaseRequest = {
  id: 'request-001', branch_id: 'branch-1', cost_centre_id: 'cc-1',
  requested_by_membership_id: 'member-1', requester_name: 'Sara', requester_email: 'sara@example.test',
  required_by_date: '2026-11-10', status: 'submitted', created_at: '2026-11-01T10:00:00Z',
  submitted_at: '2026-11-01T11:00:00Z', has_incomplete_estimate: true,
  estimated_total: {amount: '120', currency: 'EGP'}, budget_status: {status: 'within', exceeds: false},
  approval_step: {id: 'step-1', assigned_membership_id: 'member-2', assigned_name: 'Layla',
    assigned_email: 'layla@example.test', source: 'threshold_match', status: 'pending'},
  source: {rfq_id: 'rfq-1', rfq_response_id: 'response-1', quotation_id: 'quote-1', supplier_id: 'supplier-1', supplier_name: 'Supplier'},
  lines: [{id: 'line-1', workspace_product_id: 'product-1', product_name: 'Rice', quantity: '2',
    base_unit: 'kg', pack_base_quantity: '5', estimated_unit_price: {amount: '60', currency: 'EGP'}, note: 'Before noon',
    quoted_prices_include_vat: false, quoted_vat_rate: null, quoted_net_unit_price: null}],
};

describe('ApprovalDetailComponent', () => {
  let fixture: ComponentFixture<ApprovalDetailComponent>;
  let api: jasmine.SpyObj<RequestsApiService>;
  let products: jasmine.SpyObj<ApiService>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let translate: TranslateService;
  const text = (): string => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const events = (): string[] => Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('ol li')).map(el => el.textContent?.trim() ?? '');
  beforeEach(async () => {
    api = jasmine.createSpyObj<RequestsApiService>('RequestsApiService', ['getRequest']);
    products = jasmine.createSpyObj<ApiService>('ApiService', ['products']);
    api.getRequest.and.returnValue(of(request));
    products.products.and.returnValue(of({items: [], next_cursor: null}));
    params = new BehaviorSubject(convertToParamMap({requestId: request.id}));
    await TestBed.configureTestingModule({imports: [ApprovalDetailComponent], providers: [
      provideRouter([]), provideTranslateService(),
      {provide: ActivatedRoute, useValue: {paramMap: params.asObservable()}},
      {provide: RequestsApiService, useValue: api}, {provide: ApiService, useValue: products},
      {provide: OrganisationApiService, useValue: {
        listBranches: () => of({items: [{id: 'branch-1', name: 'Cairo'}], next_cursor: null}),
        listCostCentres: () => of({items: [{id: 'cc-1', name: 'Kitchen'}], next_cursor: null}),
      }},
    ]}).compileComponents();
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog); translate.setTranslation('ar', arCatalog);
    translate.setFallbackLang('en'); translate.use('en');
  });
  // The component subscribes to paramMap in its constructor. Configure the response
  // before creating it: BehaviorSubject and of() both emit synchronously.
  function render(): void {
    expect(api.getRequest).not.toHaveBeenCalled();
    fixture = TestBed.createComponent(ApprovalDetailComponent);
    fixture.detectChanges();
  }
  function load(value: PurchaseRequest = request): void {
    api.getRequest.and.returnValue(of(value));
    render();
  }
  it('uses the response configured before construction, before the first change detection', () => {
    api.getRequest.and.returnValue(of({...request, requester_name: 'Configured requester'}));
    expect(api.getRequest).not.toHaveBeenCalled();
    fixture = TestBed.createComponent(ApprovalDetailComponent);
    expect(api.getRequest).toHaveBeenCalledOnceWith(request.id);
    expect(fixture.componentInstance.request()?.requester_name).toBe('Configured requester');
    fixture.detectChanges();
    expect(text()).toContain('Configured requester');
  });
  it('announces loading with a spinner', () => {
    api.getRequest.and.returnValue(new Subject<PurchaseRequest>()); render();
    expect(text()).toContain('Loading'); expect(fixture.nativeElement.querySelector('mat-spinner')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('[aria-live]')).not.toBeNull();
  });
  it('renders all blocks, enriched products and a read-only decision hint', () => {
    load();
    for (const value of ['Sara', 'sara@example.test', 'Cairo', 'Kitchen', 'EGP', '120', 'Rice', 'Before noon', 'Supplier', '5', 'kg', 'Decision', 'Timeline']) expect(text()).toContain(value);
    expect(fixture.nativeElement.querySelectorAll('h1').length).toBe(1);
    expect(fixture.nativeElement.querySelectorAll('table th[scope="col"]').length).toBe(4);
    expect(products.products).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
    expect(text()).toContain('incomplete');
  });
  it('shows pending events in order without inventing a routing timestamp', () => {
    load(); expect(events().length).toBe(3);
    expect(events()[0]).toContain('Submitted'); expect(events()[1]).toContain('Routed to Layla');
    expect(events()[2]).toContain('Awaiting a decision from Layla');
    expect(fixture.nativeElement.querySelectorAll('ol time').length).toBe(1);
  });
  for (const status of ['approved', 'rejected'] as const) {
    it(`shows the ${status} decider, comment, time and self-decision mark in order`, () => {
      load({...request, status, approval_step: {...request.approval_step!, status, decided_name: 'Omar', decided_email: 'omar@example.test',
        decided_by_membership_id: 'member-3', decided_at: '2026-11-02T12:00:00Z', comment: 'Decision reason', self_approval: true}});
      expect(events().length).toBe(3); expect(events()[0]).toContain('Submitted'); expect(events()[1]).toContain('Routed');
      expect(events()[2]).toContain(status === 'approved' ? 'Approved' : 'Rejected'); expect(events()[2]).toContain('Omar');
      expect(events()[2]).toContain('Decision reason');
      expect(text()).toContain(translate.instant(status === 'approved' ? 'requests.approval.selfApproved' : 'requests.approval.selfRejected'));
      expect(fixture.nativeElement.querySelector('ol li:last-child time').getAttribute('datetime')).toBe('2026-11-02T12:00:00Z');
      expect(fixture.nativeElement.querySelectorAll('button').length).toBe(0);
    });
  }
  it('places withdrawal after the recorded decision and sorts dated events chronologically', () => {
    load({...request, status: 'withdrawn', submitted_at: '2026-11-03T11:00:00Z', withdrawn_at: '2026-11-04T10:00:00Z',
      approval_step: {...request.approval_step!, status: 'approved', decided_name: 'Omar', decided_at: '2026-11-02T12:00:00Z'}});
    const times = Array.from(fixture.nativeElement.querySelectorAll('ol time') as NodeListOf<HTMLElement>).map(el => el.getAttribute('datetime'));
    expect(times).toEqual(['2026-11-02T12:00:00Z', '2026-11-03T11:00:00Z', '2026-11-04T10:00:00Z']);
    expect(events().at(-1)).toContain('Withdrawn'); expect(text()).not.toContain('Awaiting a decision');
  });
  it('links split siblings to their detail routes', () => {
    load({...request, request_group: {id: 'group-1', rfq_id: 'rfq-1', size: 2, position: 1, combined_total: {amount: '240', currency: 'EGP'}, sibling_request_ids: ['request-002']}});
    expect(fixture.nativeElement.querySelector('a[href="/approvals/request-002"]')).not.toBeNull(); expect(text()).toContain('Split');
  });
  for (const status of [403, 404]) it(`renders ${status} as not found without raw error`, () => {
    api.getRequest.and.returnValue(throwError(() => new HttpErrorResponse({status, error: {message: 'secret'}}))); render();
    expect(text()).toContain('This request was not found.'); expect(text()).not.toContain('secret');
    expect(fixture.nativeElement.querySelector('a[href="/approvals"]')).not.toBeNull();
  });
  it('retries other errors', () => {
    api.getRequest.and.returnValue(throwError(() => new HttpErrorResponse({status: 500}))); render();
    expect(text()).toContain('could not'); api.getRequest.and.returnValue(of(request));
    fixture.nativeElement.querySelector('button').click(); fixture.detectChanges(); expect(text()).toContain('Rice');
  });
  it('reloads when route params change and cancels stale reads', () => {
    const old = new Subject<PurchaseRequest>(); api.getRequest.and.returnValue(old); render();
    api.getRequest.and.returnValue(of({...request, id: 'request-002', requester_name: 'New requester'}));
    params.next(convertToParamMap({requestId: 'request-002'})); old.next(request); fixture.detectChanges();
    expect(api.getRequest).toHaveBeenCalledWith('request-002'); expect(text()).toContain('New requester'); expect(text()).not.toContain('Sara');
  });
  it('uses real Arabic translations and Latin digits', () => {
    translate.use('ar'); load({...request, approval_step: {...request.approval_step!, self_approval: true}});
    expect(text()).toContain(arCatalog.approvals.detail.timeline); expect(text()).toContain(arCatalog.requests.approval.selfApprovalPending);
    expect(text()).toContain('120'); expect(text()).not.toMatch(/[٠-٩]/); expect(text()).not.toContain('approvals.detail.');
  });
  it('omits missing timestamps and does not invent a submitted event', () => {
    load({...request, submitted_at: null}); expect(events().some(e => e.includes('Submitted'))).toBeFalse();
    expect(fixture.nativeElement.querySelectorAll('ol time').length).toBe(0);
  });
});
