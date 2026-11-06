import { ComponentFixture, TestBed } from '@angular/core/testing';
import { parseSearch, parseSort, parseStatusFilter, HistoryComponent } from './history.component';
import { RfqApi, RfqSummary, RfqList, RfqSendResponse, RfqDetail } from '../rfq-api';
import { ActivatedRoute, convertToParamMap, Router, provideRouter } from '@angular/router';
import { of, throwError, Subject } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { ApiService } from '../../../core/api/api.service';
import { BreakpointObserver, BreakpointState } from '@angular/cdk/layout';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';

describe('HistoryComponent', () => {
  let component: HistoryComponent;
  let fixture: ComponentFixture<HistoryComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let router: Router;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let breakpointSpy: jasmine.SpyObj<BreakpointObserver>;

  const mockRfqs: RfqSummary[] = [
    {
      id: 'rfq-draft-1',
      created_by_membership_id: 'm1',
      status: 'draft',
      needed_by_date: '2026-12-31',
      created_at: '2026-09-20T10:00:00Z',
      sent_at: null,
      recipient_count: 3,
      response_count: 0,
      converted_purchase_request_id: null,
    },
    {
      id: 'rfq-1',
      created_by_membership_id: 'm1',
      status: 'sent',
      needed_by_date: '2026-10-01',
      created_at: '2026-09-25T10:00:00Z',
      sent_at: '2026-09-26T14:30:00Z',
      recipient_count: 5,
      response_count: 2,
      converted_purchase_request_id: null,
    },
    {
      id: 'rfq-2',
      created_by_membership_id: 'm1',
      status: 'converted',
      needed_by_date: '2026-10-05',
      created_at: '2026-09-24T10:00:00Z',
      sent_at: '2026-09-24T12:00:00Z',
      recipient_count: 3,
      response_count: 3,
      converted_purchase_request_id: 'pr-1',
    },
  ];

  const mockRfqList: RfqList = {
    items: mockRfqs,
    next_cursor: null,
  };


  it('renders an isolated reference at every width and omits absent values', () => {
    fixture.detectChanges();
    component.rfqs.set([{ ...mockRfqs[0], reference_number: 123 }, mockRfqs[1]]);
    for (const narrow of [false, true]) {
      component.isBelow768.set(narrow);
      fixture.detectChanges();
      const cells = fixture.nativeElement.querySelectorAll('td.mat-column-reference');
      expect(cells.length).toBe(2);
      expect(cells[0].textContent.trim()).toBe('RFQ-000123');
      expect(cells[0].querySelector('bdi').dir).toBe('ltr');
      expect(cells[1].textContent.trim()).toBe('');
    }
  });

  for (const owner of [true, false]) {
    it('limits non-creator draft sending by owner role: ' + owner, () => {
      fixture.detectChanges();
      spyOn(TestBed.inject(SessionService), 'hasRole').and.callFake(role => role === (owner ? 'owner' : 'buyer'));
      component.currentMembershipId.set('other');
      fixture.detectChanges();
      expect(!!fixture.nativeElement.querySelector('[data-testid="rfq-send-button"]')).toBe(owner);
      expect(fixture.nativeElement.querySelector('[data-testid="rfq-edit-button"]')).toBeNull();
    });
  }
  beforeEach(async () => {
    jasmine.clock().install();
    jasmine.clock().mockDate(new Date(2026, 9, 28));
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['listRfqs', 'sendRfq', 'cancelRfq', 'getRfq']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    const apiSpy = jasmine.createSpyObj('ApiService', ['members']);
    apiSpy.members.and.returnValue(of({ items: [{ id: 'm1', email: 'user@test.com' }], next_cursor: null }));
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    breakpointSpy = jasmine.createSpyObj('BreakpointObserver', ['observe', 'isMatched']);
    breakpointSpy.observe.and.returnValue(of({ matches: false, breakpoints: {} }));
    breakpointSpy.isMatched.and.returnValue(false);

    rfqApiSpy.listRfqs.and.returnValue(of(mockRfqList));
    rfqApiSpy.getRfq.and.returnValue(
      of({
        rfq: { ...mockRfqs[1], tenant_id: 't1', idempotency_key: 'k1', tenant_terms: null },
        lines: [],
        recipients: [
          {
            id: 'rec-1',
            tenant_id: 't1',
            rfq_id: 'rfq-1',
            supplier_id: 's1',
            supplier_name: 'Supplier Alpha',
            supplier_contact_email: 'alpha@example.test',
            status: 'sent',
            outbound_message_id: null,
            sent_at: '2026-09-26T14:30:00Z',
            created_at: '2026-09-25T10:00:00Z',
          },
          {
            id: 'rec-2',
            tenant_id: 't1',
            rfq_id: 'rfq-1',
            supplier_id: 's2',
            supplier_name: null,
            supplier_contact_email: null,
            status: 'failed',
            outbound_message_id: null,
            sent_at: null,
            created_at: '2026-09-25T10:00:00Z',
          },
        ],
      }),
    );

    await TestBed.configureTestingModule({
      imports: [HistoryComponent, NoopAnimationsModule],
      providers: [
        provideTranslateService(),
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: RfqApi, useValue: rfqApiSpy },
        { provide: ApiService, useValue: apiSpy },
        { provide: MatSnackBar, useValue: snackBarSpy },
        { provide: MatDialog, useValue: dialogSpy },
        { provide: BreakpointObserver, useValue: breakpointSpy },
        {
          provide: SessionService,
          useValue: {
            role: signal<'owner' | null>('owner'),
            hasRole: () => true,
            isAuthenticated: () => true,
            activeLocale: () => 'en',
            currentMember: () => ({ email: 'user@test.com' }),
          },
        },
      ],
    })
      .overrideProvider(MatDialog, { useValue: dialogSpy })
      .overrideProvider(MatSnackBar, { useValue: snackBarSpy })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');

    fixture = TestBed.createComponent(HistoryComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
    spyOn(router, 'navigate');
    fixture.detectChanges();
  });

  afterEach(() => {
    jasmine.clock().uninstall();
  });

  describe('creator membership id (buyers cannot call the members API)', () => {
    const members = () => (TestBed.inject(ApiService) as unknown as jasmine.SpyObj<ApiService>).members;

    function createWithSession(sessionMember: object | null): HistoryComponent {
      spyOn(TestBed.inject(SessionService), 'currentMember').and.returnValue(sessionMember as never);
      members().calls.reset();
      const created = TestBed.createComponent(HistoryComponent);
      created.detectChanges();
      return created.componentInstance;
    }

    it('reads the membership id from the session and does not call members()', () => {
      const history = createWithSession({ email: 'buyer@test.com', membership_id: 'm-buyer' });
      expect(history.currentMembershipId()).toBe('m-buyer');
      expect(history.draftActionsUnavailable()).toBeFalse();
      expect(members()).not.toHaveBeenCalled();
    });

    it('falls back to members() when the session has no membership id', () => {
      members().and.returnValue(
        of({ items: [{ id: 'm-from-api', email: 'user@test.com' }], next_cursor: null } as unknown as { items: never[]; next_cursor: string | null }),
      );
      const history = createWithSession({ email: 'user@test.com' });
      expect(members()).toHaveBeenCalledTimes(1);
      expect(history.currentMembershipId()).toBe('m-from-api');
    });

    it('reports draft actions unavailable when neither source has an id', () => {
      members().and.returnValue(throwError(() => new HttpErrorResponse({ status: 403 })));
      const history = createWithSession({ email: 'buyer@test.com' });
      expect(history.currentMembershipId()).toBeNull();
      expect(history.draftActionsUnavailable()).toBeTrue();
    });
  });


  describe('search and sort', () => {
    function input(): HTMLInputElement {
      return fixture.nativeElement.querySelector('input[type="search"]');
    }
    function type(value: string): void {
      input().value = value;
      input().dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    function enter(): void {
      input().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      fixture.detectChanges();
    }
    function chooseSort(): void {
      (fixture.nativeElement.querySelector('mat-select') as HTMLElement).click();
      fixture.detectChanges();
      const option = Array.from(document.querySelectorAll<HTMLElement>('mat-option'))
        .find(el => el.textContent?.trim() === 'Needed by: soonest')!;
      option.click();
      fixture.detectChanges();
    }
    it('parses absent, invalid, trimmed and capped address values', () => {
      expect(parseSort(null)).toBe('created_desc');
      expect(parseSort('')).toBe('created_desc');
      expect(parseSort('invalid')).toBe('created_desc');
      expect(parseSearch(null)).toBe('');
      expect(parseSearch('   ')).toBe('');
      expect(parseSearch('  RFQ-000002  ')).toBe('RFQ-000002');
      expect(parseSearch('x'.repeat(101))).toBe('x'.repeat(100));
    });
    it('drops stale search responses after another search starts', () => {
      const stale = new Subject<RfqList>();
      rfqApiSpy.listRfqs.and.returnValue(stale);
      type('old'); enter();
      rfqApiSpy.listRfqs.and.returnValue(of({ items: [], next_cursor: null }));
      type('new'); enter();
      stale.next(mockRfqList);
      expect(component.rfqs()).toEqual([]);
      expect(component.nextCursor()).toBeNull();
      jasmine.clock().tick(300);
    });
    it('debounces two edits into one final request', () => {
      rfqApiSpy.listRfqs.calls.reset();
      type('sup');
      jasmine.clock().tick(200);
      type('supplier');
      jasmine.clock().tick(299);
      expect(rfqApiSpy.listRfqs).not.toHaveBeenCalled();
      jasmine.clock().tick(1);
      expect(rfqApiSpy.listRfqs.calls.allArgs()).toEqual([[undefined, undefined, undefined, 'supplier', 'created_desc']]);
    });
    it('Enter reloads immediately and cancels the pending debounce', () => {
      rfqApiSpy.listRfqs.calls.reset();
      type('2');
      enter();
      expect(rfqApiSpy.listRfqs.calls.count()).toBe(1);
      jasmine.clock().tick(300);
      expect(rfqApiSpy.listRfqs.calls.count()).toBe(1);
    });
    it('clear search resets the field and reloads once', () => {
      type('supplier');
      rfqApiSpy.listRfqs.calls.reset();
      (fixture.nativeElement.querySelector('[data-testid="rfq-clear-search"]') as HTMLButtonElement).click();
      fixture.detectChanges();
      jasmine.clock().tick(300);
      expect(input().value).toBe('');
      expect(rfqApiSpy.listRfqs.calls.allArgs()).toEqual([[undefined, undefined, undefined, undefined, 'created_desc']]);
    });
    it('sort reloads, persists all address parameters and keeps them for pagination', () => {
      type(' bolt ');
      enter();
      component.setStatusFilter('sent');
      rfqApiSpy.listRfqs.calls.reset();
      chooseSort();
      expect(rfqApiSpy.listRfqs.calls.allArgs()).toEqual([['sent', undefined, undefined, 'bolt', 'needed_asc']]);
      expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
        queryParams: { status: 'sent', q: 'bolt', sort: 'needed_asc' },
        queryParamsHandling: 'merge', replaceUrl: true,
      }));
      component.nextCursor.set('next');
      component.loadMore();
      expect(rfqApiSpy.listRfqs.calls.mostRecent().args).toEqual(['sent', 'next', undefined, 'bolt', 'needed_asc']);
    });
    it('keeps the applied query while an edit is waiting to debounce', () => {
      type('old'); enter();
      type('new');
      component.nextCursor.set('next');
      component.loadMore();
      expect(rfqApiSpy.listRfqs.calls.mostRecent().args).toEqual([undefined, 'next', undefined, 'old', 'created_desc']);
      jasmine.clock().tick(300);
    });
    it('initializes valid address values, trims and caps search and defaults invalid sort', () => {
      const route = TestBed.inject(ActivatedRoute);
      for (const sort of ['created_desc', 'created_asc', 'needed_asc', 'needed_desc', 'reference_desc', 'reference_asc', 'invalid']) {
        Object.defineProperty(route.snapshot, 'queryParamMap', { configurable: true, value: convertToParamMap({ status: 'sent', q: '  ' + 'x'.repeat(110) + '  ', sort }) });
        const other = TestBed.createComponent(HistoryComponent);
        other.detectChanges();
        expect(rfqApiSpy.listRfqs.calls.mostRecent().args).toEqual(['sent', undefined, undefined, 'x'.repeat(100), sort === 'invalid' ? 'created_desc' : sort]);
        other.destroy();
      }
    });
    it('shows an empty-match state and clears all controls in one reload', () => {
      rfqApiSpy.listRfqs.and.returnValue(of({ items: [], next_cursor: null }));
      type('missing'); enter();
      component.setStatusFilter('sent');
      chooseSort();
      expect(fixture.nativeElement.textContent).toContain('No RFQs match your search or filter.');
      rfqApiSpy.listRfqs.calls.reset();
      const clear = fixture.nativeElement.querySelector('[data-testid="rfq-clear-filter"]') as HTMLButtonElement;
      expect(clear.textContent).toContain('Clear search and filters');
      clear.click();
      fixture.detectChanges();
      jasmine.clock().tick(300);
      expect(rfqApiSpy.listRfqs.calls.allArgs()).toEqual([[undefined, undefined, undefined, undefined, 'created_desc']]);
      expect(fixture.nativeElement.textContent).toContain('No RFQs found.');
      expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({ queryParams: { q: null, sort: null, status: null } }));
    });
    for (const locale of ['en', 'ar']) {
      it('associates visible labels with search and sort in ' + locale, () => {
        TestBed.inject(TranslateService).use(locale);
        fixture.detectChanges();
        const host = fixture.nativeElement as HTMLElement;
        const field = input();
        expect(field).not.toBeNull();
        expect(field.maxLength).toBe(100);
        const label = host.querySelector('label[for="' + field.id + '"]');
        expect(label?.textContent).toContain(locale === 'en' ? 'Search RFQs' : 'البحث في طلبات عروض الأسعار');
        const select = host.querySelector('mat-select')!;
        const labels = select.getAttribute('aria-labelledby')!.split(' ').map(id => document.getElementById(id)?.textContent).join(' ');
        expect(labels).toContain(locale === 'en' ? 'Sort by' : 'ترتيب حسب');
      });
    }
  });

  describe('status filter', () => {
    function filterButtons(): HTMLButtonElement[] {
      return Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
          '[data-testid="rfq-status-filters"] button',
        ),
      );
    }

    it('parses only known statuses from the address', () => {
      expect(parseStatusFilter('sent')).toBe('sent');
      expect(parseStatusFilter('cancelled')).toBe('cancelled');
      expect(parseStatusFilter('bogus')).toBeNull();
      expect(parseStatusFilter('')).toBeNull();
      expect(parseStatusFilter(null)).toBeNull();
    });

    it('offers All plus every status, with All pressed by default', () => {
      const buttons = filterButtons();
      expect(buttons.map((b) => b.textContent?.trim())).toEqual([
        'All', 'Draft', 'Sent', 'Responded', 'Expired', 'Converted', 'Cancelled',
      ]);
      expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(
        ['true', 'false', 'false', 'false', 'false', 'false', 'false'],
      );
      const group = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-status-filters"]');
      expect(group?.getAttribute('role')).toBe('group');
      expect(group?.getAttribute('aria-label')).toBe('Filter by status');
    });

    it('loads the chosen status, marks it pressed and writes it to the address', () => {
      rfqApiSpy.listRfqs.calls.reset();
      filterButtons().find((b) => b.textContent?.trim() === 'Sent')?.click();
      fixture.detectChanges();
      expect(rfqApiSpy.listRfqs).toHaveBeenCalledOnceWith('sent', undefined, undefined, undefined, 'created_desc');
      expect(filterButtons().find((b) => b.textContent?.trim() === 'Sent')?.getAttribute('aria-pressed')).toBe('true');
      expect(filterButtons()[0].getAttribute('aria-pressed')).toBe('false');
      expect(router.navigate).toHaveBeenCalledWith(
        [],
        jasmine.objectContaining({ queryParams: { status: 'sent', q: null, sort: null }, replaceUrl: true }),
      );
    });

    it('keeps the filter when loading more and clears it with All', () => {
      component.setStatusFilter('expired');
      rfqApiSpy.listRfqs.calls.reset();
      component.nextCursor.set('cursor-2');
      component.loadMore();
      expect(rfqApiSpy.listRfqs).toHaveBeenCalledOnceWith('expired', 'cursor-2', undefined, undefined, 'created_desc');
      rfqApiSpy.listRfqs.calls.reset();
      component.setStatusFilter(null);
      expect(rfqApiSpy.listRfqs).toHaveBeenCalledOnceWith(undefined, undefined, undefined, undefined, 'created_desc');
      expect(router.navigate).toHaveBeenCalledWith(
        [],
        jasmine.objectContaining({ queryParams: { status: null, q: null, sort: null } }),
      );
    });

    it('does not reload when the same filter is chosen again', () => {
      component.setStatusFilter('sent');
      rfqApiSpy.listRfqs.calls.reset();
      component.setStatusFilter('sent');
      expect(rfqApiSpy.listRfqs).not.toHaveBeenCalled();
    });

    it('says no RFQ has the status, with a way back, instead of the generic empty state', () => {
      rfqApiSpy.listRfqs.and.returnValue(of({ items: [], next_cursor: null }));
      component.setStatusFilter('cancelled');
      fixture.detectChanges();
      const host = fixture.nativeElement as HTMLElement;
      expect(host.textContent).toContain('No RFQs match your search or filter.');
      const clear = host.querySelector<HTMLButtonElement>('[data-testid="rfq-clear-filter"]');
      expect(clear).not.toBeNull();
      rfqApiSpy.listRfqs.and.returnValue(of(mockRfqList));
      rfqApiSpy.listRfqs.calls.reset();
      clear?.click();
      expect(rfqApiSpy.listRfqs).toHaveBeenCalledOnceWith(undefined, undefined, undefined, undefined, 'created_desc');
    });
  });

  describe('cancellation', () => {
    for (const status of [0, 503, 408, 429]) {
      it(`retains the cancel key after ${status} and rotates after success or definitive rejection`, () => {
        component.currentMembershipId.set(mockRfqs[1].created_by_membership_id);
        dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status })));
        component.onCancelRfq(mockRfqs[1]);
        const first = rfqApiSpy.cancelRfq.calls.mostRecent().args[1];
        expect(first).toEqual(jasmine.any(String));
        const pending = new Subject<RfqDetail['rfq']>();
        rfqApiSpy.cancelRfq.and.returnValue(pending);
        component.onCancelRfq(mockRfqs[1]);
        component.onCancelRfq(mockRfqs[1]);
        expect(rfqApiSpy.cancelRfq).toHaveBeenCalledTimes(2);
        expect(rfqApiSpy.cancelRfq.calls.mostRecent().args[1]).toBe(first);
        pending.next({ ...mockRfqs[1], tenant_id: 't1', tenant_terms: null, idempotency_key: 'k1' });
        pending.complete();
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
        component.onCancelRfq(mockRfqs[1]);
        const rejected = rfqApiSpy.cancelRfq.calls.mostRecent().args[1];
        expect(rejected).not.toBe(first);
        component.onCancelRfq(mockRfqs[1]);
        expect(rfqApiSpy.cancelRfq.calls.mostRecent().args[1]).not.toBe(rejected);
      });
    }

    it('shows the menu item for owners and only the creating buyer', async () => {
      const role = spyOn(TestBed.inject(SessionService), 'hasRole');
      role.and.callFake((...roles) => roles.includes('owner'));
      component.currentMembershipId.set('another-member');
      expect(component.canCancel(mockRfqs[1])).toBeTrue();
      role.and.callFake((...roles) => roles.includes('buyer'));
      expect(component.canCancel(mockRfqs[1])).toBeFalse();
      component.currentMembershipId.set('m1');
      expect(component.canCancel(mockRfqs[1])).toBeTrue();
      expect(component.canCancel(mockRfqs[2])).toBeFalse();
      expect(component.canCancel({ ...mockRfqs[1], status: 'cancelled' })).toBeFalse();
      const page = fixture.nativeElement as HTMLElement;
      page.querySelector<HTMLButtonElement>('[data-testid="rfq-actions-button"]')!.click();
      fixture.detectChanges();
      await fixture.whenStable();
      expect(document.querySelector('[data-testid="rfq-history-cancel-button"]')?.textContent).toContain(enCatalog.rfq.cancel.confirm);
      component.currentMembershipId.set('another-member');
      fixture.detectChanges();
      expect(document.querySelector('[data-testid="rfq-history-cancel-button"]')).toBeNull();
      expect(router.navigate).not.toHaveBeenCalled();
    });

    it('confirms once, stops row navigation and reloads the list on success', () => {
      const confirmation = new Subject<boolean>();
      const result = new Subject<RfqDetail['rfq']>();
      dialogSpy.open.and.returnValue({ afterClosed: () => confirmation } as unknown as MatDialogRef<CatalogueConfirmDialogComponent>);
      rfqApiSpy.cancelRfq.and.returnValue(result);
      const event = new Event('click');
      spyOn(event, 'stopPropagation');
      component.onCancelRfq(mockRfqs[1], event);
      component.onCancelRfq(mockRfqs[1], event);
      expect(event.stopPropagation).toHaveBeenCalled();
      expect(dialogSpy.open.calls.count()).toBe(1);
      expect(dialogSpy.open.calls.mostRecent().args[1]?.data).toEqual(jasmine.objectContaining({ isDestructive: true }));
      confirmation.next(true);
      confirmation.next(true);
      component.onCancelRfq(mockRfqs[1]);
      expect(rfqApiSpy.cancelRfq).toHaveBeenCalledOnceWith(mockRfqs[1].id, jasmine.any(String));
      rfqApiSpy.listRfqs.calls.reset();
      result.next({ ...mockRfqs[1], tenant_id: 't1', tenant_terms: null, idempotency_key: 'key', status: 'cancelled' });
      result.complete();
      expect(rfqApiSpy.listRfqs.calls.count()).toBe(1);
      expect(component.cancellingIds().size).toBe(0);
      expect(router.navigate).not.toHaveBeenCalled();
    });

    for (const [status, key] of [[403, 'notCreator'], [409, 'notCancellable'], [500, 'error']] as const) {
      it(`handles cancellation error ${status}`, () => {
        dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent>);
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status, error: { details: { reason: 'not_creator' } } })));
        rfqApiSpy.listRfqs.calls.reset();
        component.onCancelRfq(mockRfqs[1]);
        expect(snackBarSpy.open).toHaveBeenCalledWith(enCatalog.rfq.cancel[key], jasmine.any(String), jasmine.any(Object));
        expect(rfqApiSpy.listRfqs.calls.count()).toBe(status === 409 ? 1 : 0);
        expect(component.cancellingIds().size).toBe(0);
      });
    }
  });

  it('should create and load RFQs', () => {
    expect(component).toBeTruthy();
    expect(rfqApiSpy.listRfqs).toHaveBeenCalled();
    expect(component.rfqs().length).toBe(3);
    expect(component.loading()).toBeFalse();
  });

  it('should navigate to edit view when clicking a draft row', () => {
    component.onRowClick(mockRfqs[0]);
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-draft-1', 'edit']);
  });

  it('routes another member’s draft to RFQ details and hides draft actions for a buyer', async () => {
    spyOn(TestBed.inject(SessionService), 'hasRole').and.callFake(role => role === 'buyer');
    component.currentMembershipId.set('different-member');
    component.onRowClick(mockRfqs[0]);
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-draft-1']);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-edit-button"]')).toBeNull();
    expect(compiled.querySelector('[data-testid="rfq-send-button"]')).toBeNull();
  });

  it('should navigate to details view for non-converted sent RFQ', () => {
    component.onRowClick(mockRfqs[1]);
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-1']);
  });

  it('should navigate to request view for converted RFQ', () => {
    component.onRowClick(mockRfqs[2]);
    expect(router.navigate).toHaveBeenCalledWith(['/requests', 'pr-1']);
  });

  it('navigates to details view for a converted RFQ with several requests', () => {
    const multiRequestRfq: RfqSummary = {
      ...mockRfqs[2],
      id: 'rfq-multi-1',
      status: 'converted',
      converted_purchase_request_id: 'pr-1',
      converted_purchase_request_ids: ['pr-1', 'pr-2'],
      request_group_id: 'grp-1',
    };
    component.onRowClick(multiRequestRfq);
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-multi-1']);
  });

  it('initial failure shows the error state with role alert and NOT the empty state, and Retry reloads', async () => {
    rfqApiSpy.listRfqs.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    component.loadRfqs();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(snackBarSpy.open).not.toHaveBeenCalled();
    const compiled = fixture.nativeElement as HTMLElement;
    const alertEl = compiled.querySelector('[role="alert"]');
    expect(alertEl).not.toBeNull();
    expect(alertEl?.textContent).toContain('Failed to load RFQs');
    expect(compiled.querySelector('.empty-state')).toBeNull();

    // Clicking Retry calls loadRfqs()
    rfqApiSpy.listRfqs.and.returnValue(of(mockRfqList));
    const retryBtn = alertEl?.querySelector('button');
    expect(retryBtn).not.toBeNull();
    retryBtn?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.rfqs().length).toBe(3);
    expect(compiled.querySelector('.error-state')).toBeNull();
  });

  it('load more appends and de-duplicates and hides the button on the last page', async () => {
    const initialList: RfqList = {
      items: [mockRfqs[0], mockRfqs[1]],
      next_cursor: 'cursor-page-2',
    };
    rfqApiSpy.listRfqs.and.returnValue(of(initialList));
    component.loadRfqs();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    let loadMoreBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-load-more-button"]');
    expect(loadMoreBtn).not.toBeNull();

    const secondPage: RfqList = {
      items: [mockRfqs[1], mockRfqs[2]],
      next_cursor: null,
    };
    rfqApiSpy.listRfqs.and.returnValue(of(secondPage));

    loadMoreBtn?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(rfqApiSpy.listRfqs).toHaveBeenCalledWith(undefined, 'cursor-page-2', undefined, undefined, 'created_desc');
    expect(component.rfqs().length).toBe(3);
    expect(component.rfqs().map((r) => r.id)).toEqual(['rfq-draft-1', 'rfq-1', 'rfq-2']);
    expect(component.nextCursor()).toBeNull();

    loadMoreBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-load-more-button"]');
    expect(loadMoreBtn).toBeNull();
  });

  it('double click on Load more sends one request', () => {
    component.nextCursor.set('cursor-1');
    const subject = new Subject<RfqList>();
    rfqApiSpy.listRfqs.and.returnValue(subject);
    rfqApiSpy.listRfqs.calls.reset();

    component.loadMore();
    component.loadMore();

    expect(rfqApiSpy.listRfqs).toHaveBeenCalledTimes(1);
    subject.next({ items: [], next_cursor: null });
    subject.complete();
  });

  it('Load more pending, then loadRfqs() refresh, then old page resolves -> rows are exactly refreshed first page and cursor is refreshed cursor', () => {
    component.rfqs.set([mockRfqs[0]]);
    component.nextCursor.set('cursor-page-2');

    const loadMoreSubject = new Subject<RfqList>();
    const refreshedFirstPage: RfqList = {
      items: [
        {
          ...mockRfqs[0],
          id: 'rfq-fresh-1',
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
      next_cursor: 'cursor-fresh-2',
    };

    rfqApiSpy.listRfqs.and.returnValue(loadMoreSubject);
    component.loadMore();
    expect(component.loadingMore()).toBeTrue();

    const refreshSubject = new Subject<RfqList>();
    rfqApiSpy.listRfqs.and.returnValue(refreshSubject);
    component.loadRfqs();
    refreshSubject.next(refreshedFirstPage);
    refreshSubject.complete();

    expect(component.rfqs()).toEqual(refreshedFirstPage.items);
    expect(component.nextCursor()).toBe('cursor-fresh-2');

    const oldPage: RfqList = {
      items: [mockRfqs[1]],
      next_cursor: 'cursor-old-page-3',
    };
    loadMoreSubject.next(oldPage);
    loadMoreSubject.complete();

    expect(component.rfqs()).toEqual(refreshedFirstPage.items);
    expect(component.nextCursor()).toBe('cursor-fresh-2');
  });

  it('load-more failure keeps rows and shows retry', async () => {
    component.nextCursor.set('cursor-1');
    rfqApiSpy.listRfqs.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));

    component.loadMore();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.rfqs().length).toBe(3);
    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-load-more-retry"]');
    expect(retryBtn).not.toBeNull();

    rfqApiSpy.listRfqs.and.returnValue(of({ items: [], next_cursor: null }));
    retryBtn?.click();
    expect(rfqApiSpy.listRfqs).toHaveBeenCalledWith(undefined, 'cursor-1', undefined, undefined, 'created_desc');
  });

  it('the row link has the expected accessible name and navigates', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const rowLinks = compiled.querySelectorAll<HTMLButtonElement>('[data-testid="rfq-row-link"]');
    expect(rowLinks.length).toBe(3);

    const ariaLabel = rowLinks[1].getAttribute('aria-label');
    expect(ariaLabel).toContain('Open RFQ');
    expect(ariaLabel).toContain('Sent');
    expect(ariaLabel).toContain('Oct 1, 2026');

    spyOn(component, 'onRowClick').and.callThrough();
    rowLinks[1].click();
    expect(component.onRowClick).toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-1']);
  });

  it('count controls have labels', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const recipientBtns = compiled.querySelectorAll<HTMLButtonElement>('[data-testid="rfq-recipients-button"]');
    expect(recipientBtns.length).toBeGreaterThanOrEqual(2);
    expect(recipientBtns[1].getAttribute('aria-label')).toBe('5 recipients — show list');

    const responseLinks = compiled.querySelectorAll<HTMLAnchorElement>('[data-testid="rfq-responses-cell"] a');
    expect(responseLinks.length).toBeGreaterThanOrEqual(1);
    expect(responseLinks[0].getAttribute('aria-label')).toBe('2 responses — compare');
  });

  it('members failure falls back to session current member id', () => {
    const api = TestBed.inject(ApiService) as jasmine.SpyObj<ApiService>;
    api.members.and.returnValue(throwError(() => new Error('Network error')));
    const session = TestBed.inject(SessionService);
    spyOn(session, 'currentMember').and.returnValue({
      id: 'u1',
      membership_id: 'fallback-mem-1',
      email: 'user@test.com',
      role: 'owner',
      preferred_locale: 'en',
      mfa_enabled: false,
      tenant: {
        id: 't1',
        name: 'Tenant 1',
        slug: 't1',
        region: 'us',
        currency: 'USD',
        tax_model: 'standard',
        default_locale: 'en',
        created_at: '2026-01-01',
      },
    });

    const compFixture = TestBed.createComponent(HistoryComponent);
    compFixture.detectChanges();

    expect(compFixture.componentInstance.currentMembershipId()).toBe('fallback-mem-1');
    expect(compFixture.componentInstance.draftActionsUnavailable()).toBeFalse();
  });

  it('members failure without session member id shows notice without crashing', async () => {
    const api = TestBed.inject(ApiService) as jasmine.SpyObj<ApiService>;
    api.members.and.returnValue(throwError(() => new Error('Network error')));
    const session = TestBed.inject(SessionService);
    spyOn(session, 'currentMember').and.returnValue({
      id: 'u1',
      membership_id: null,
      email: 'user@test.com',
      role: 'owner',
      preferred_locale: 'en',
      mfa_enabled: false,
      tenant: {
        id: 't1',
        name: 'Tenant 1',
        slug: 't1',
        region: 'us',
        currency: 'USD',
        tax_model: 'standard',
        default_locale: 'en',
        created_at: '2026-01-01',
      },
    });

    const compFixture = TestBed.createComponent(HistoryComponent);
    compFixture.detectChanges();
    await compFixture.whenStable();
    compFixture.detectChanges();

    expect(compFixture.componentInstance.currentMembershipId()).toBeNull();
    expect(compFixture.componentInstance.draftActionsUnavailable()).toBeTrue();
    const compiled = compFixture.nativeElement as HTMLElement;
    const notice = compiled.querySelector('[data-testid="draft-actions-notice"]');
    expect(notice).not.toBeNull();
  });

  it('polite live region announces showing N RFQs', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const statusEl = compiled.querySelector('[role="status"]');
    expect(statusEl).not.toBeNull();
    expect(statusEl?.textContent).toContain('Showing 3 RFQs');
  });

  it('renders "—" for draft Sent Date and date + time with middle dot for sent RFQs', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const sentCells = compiled.querySelectorAll('[data-testid="rfq-sent-at-cell"]');
    expect(sentCells.length).toBe(3);
    expect(sentCells[0].textContent?.trim()).toBe('—');
    expect(sentCells[1].textContent?.trim()).toContain('·');
  });

  it('renders responses count as link with ?tab=responses when > 0, and plain 0 when 0', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const responseCells = compiled.querySelectorAll('[data-testid="rfq-responses-cell"]');
    expect(responseCells.length).toBe(3);

    // mockRfqs[0] has response_count: 0 -> plain "0", no link
    expect(responseCells[0].querySelector('a')).toBeNull();
    expect(responseCells[0].textContent?.trim()).toBe('0');

    // mockRfqs[1] has response_count: 2 -> link
    const link = responseCells[1].querySelector<HTMLAnchorElement>('a');
    expect(link).not.toBeNull();
    expect(link?.textContent?.trim()).toBe('2');
  });

  it('stops propagation when clicking the responses link', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    spyOn(component, 'onRowClick');
    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      '[data-testid="rfq-responses-cell"] a',
    );
    expect(link).not.toBeNull();
    link?.click();
    expect(component.onRowClick).not.toHaveBeenCalled();
  });

  it('renders actions menu button for all rows and stops propagation on click', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    spyOn(component, 'onRowClick');
    const actionButtons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="rfq-actions-button"]',
    );
    expect(actionButtons.length).toBe(3);

    actionButtons[0].click();
    expect(component.onRowClick).not.toHaveBeenCalled();
  });

  it('recipients count is a button when count > 0 and clicking stops propagation and opens popover lazily', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    spyOn(component, 'onRowClick');
    const recipientButtons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="rfq-recipients-button"]',
    );
    expect(recipientButtons.length).toBeGreaterThan(0);

    recipientButtons[0].click();
    expect(component.onRowClick).not.toHaveBeenCalled();
    expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-draft-1');

    // Close and reopen: the second opening should use the cached response.
    fixture.detectChanges();
    recipientButtons[0].click();
    fixture.detectChanges();
    recipientButtons[0].click();
    fixture.detectChanges();
    expect(rfqApiSpy.getRfq).toHaveBeenCalledTimes(1);
  });

  it('shows error state in popover when rfqApi.getRfq fails', async () => {
    rfqApiSpy.getRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    component.loadRecipients('rfq-error');
    expect(component.recipientsCache()['rfq-error']?.error).toBeTrue();
  });

  it('navigates to edit page when Edit button is clicked without triggering row click', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    spyOn(component, 'onRowClick');
    const editBtn = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[data-testid="rfq-edit-button"]',
    );
    expect(editBtn).not.toBeNull();
    editBtn?.click();

    expect(component.onRowClick).not.toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-draft-1', 'edit']);
  });

  it('confirms via dialog before calling sendRfq, shows snackbar, and reloads list without triggering row click', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
    rfqApiSpy.sendRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-draft-1', status: 'sent' },
        recipients: [{ id: 'r1' }, { id: 'r2' }, { id: 'r3' }],
      } as unknown as RfqSendResponse),
    );

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    spyOn(component, 'onRowClick');
    rfqApiSpy.listRfqs.calls.reset();

    const sendBtn = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[data-testid="rfq-send-button"]',
    );
    expect(sendBtn).not.toBeNull();
    sendBtn?.click();

    expect(component.onRowClick).not.toHaveBeenCalled();
    expect(dialogSpy.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          messageParams: jasmine.objectContaining({
            count: 3,
            date: jasmine.any(String),
          }),
        }),
      }),
    );
    const sendDialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as Record<string, unknown>;
    expect(sendDialogData['warningKey']).toBeUndefined();
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1', jasmine.any(String));
    expect(snackBarSpy.open).toHaveBeenCalled();
    expect(rfqApiSpy.listRfqs).toHaveBeenCalled();
  });

  it('history send with a past date opens the "has passed" dialog and confirming navigates to edit', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    const pastRfq: RfqSummary = {
      ...mockRfqs[0],
      id: 'rfq-draft-past',
      needed_by_date: '2026-09-01',
    };

    component.onSendDraft(pastRfq);

    expect(dialogSpy.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          titleKey: 'rfq.history.neededByPassedTitle',
          messageKey: 'rfq.history.neededByPassedMessage',
          confirmKey: 'rfq.history.neededByPassedConfirm',
        }),
      }),
    );
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-draft-past', 'edit']);
    expect(rfqApiSpy.sendRfq).not.toHaveBeenCalled();
  });

  it('confirms send without past-date warning when needed_by_date is in the future', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
    rfqApiSpy.sendRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-draft-future', status: 'sent' },
        recipients: [{ id: 'r1' }],
      } as unknown as RfqSendResponse),
    );

    const futureRfq: RfqSummary = {
      ...mockRfqs[0],
      id: 'rfq-draft-future',
      needed_by_date: '2026-12-31',
    };

    component.onSendDraft(futureRfq);

    expect(dialogSpy.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          messageParams: jasmine.objectContaining({
            date: jasmine.any(String),
          }),
        }),
      }),
    );
    const futureDialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as Record<string, unknown>;
    expect(futureDialogData['warningKey']).toBeUndefined();
  });

  it('shows error snackbar when sendRfq fails after confirmation', () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
    rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));

    component.onSendDraft(mockRfqs[0]);

    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1', jasmine.any(String));
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      jasmine.any(String),
      jasmine.any(String),
      { duration: 5000 },
    );
  });

  it('invalidates recipientsCache on loadRfqs so reopening popover after sending refetches recipients with new status', async () => {
    const draftRecipients = [
      {
        id: 'rec-draft-1',
        tenant_id: 't1',
        rfq_id: 'rfq-draft-1',
        supplier_id: 's1',
        supplier_name: 'Supplier Alpha',
        supplier_contact_email: 'alpha@example.test',
        status: 'draft' as const,
        outbound_message_id: null,
        sent_at: null,
        created_at: '2026-09-25T10:00:00Z',
      },
    ];
    rfqApiSpy.getRfq.and.returnValue(
      of({
        rfq: { ...mockRfqs[0], tenant_id: 't1', idempotency_key: 'k0', tenant_terms: null },
        lines: [],
        recipients: draftRecipients,
      }),
    );

    // Popover opened on draft RFQ
    component.loadRecipients('rfq-draft-1');
    expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-draft-1');
    expect(rfqApiSpy.getRfq).toHaveBeenCalledTimes(1);
    expect(component.recipientsCache()['rfq-draft-1']?.recipients?.[0].status).toBe('draft');

    // sendRfq succeeds
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    const sentRecipients = [
      {
        ...draftRecipients[0],
        status: 'sent' as const,
        sent_at: '2026-09-26T14:30:00Z',
      },
    ];
    rfqApiSpy.sendRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-draft-1', status: 'sent' },
        recipients: sentRecipients,
      } as unknown as RfqSendResponse),
    );

    rfqApiSpy.getRfq.and.returnValue(
      of({
        rfq: { ...mockRfqs[0], status: 'sent', tenant_id: 't1', idempotency_key: 'k0', tenant_terms: null },
        lines: [],
        recipients: sentRecipients,
      }),
    );

    component.onSendDraft(mockRfqs[0]);
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1', jasmine.any(String));

    // Reopen popover on the RFQ
    component.loadRecipients('rfq-draft-1');
    expect(rfqApiSpy.getRfq).toHaveBeenCalledTimes(2);
    expect(component.recipientsCache()['rfq-draft-1']?.recipients?.[0].status).toBe('sent');
  });

  it('renders recipientsDraftHeader for draft RFQ and sentToSuppliers for sent RFQ in popover header', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    translate.use('en');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const recipientButtons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="rfq-recipients-button"]',
    );
    expect(recipientButtons.length).toBeGreaterThanOrEqual(2);

    // Open popover for draft (mockRfqs[0] has count 3, status draft)
    recipientButtons[0].click();
    fixture.detectChanges();
    await fixture.whenStable();

    const draftHeader = document.querySelector('.popover-header strong');
    expect(draftHeader?.textContent?.trim()).toBe('3 suppliers, not sent yet');

    // Open popover for sent RFQ (mockRfqs[1] has count 5, status sent)
    recipientButtons[1].click();
    fixture.detectChanges();
    await fixture.whenStable();

    const sentHeaders = document.querySelectorAll('.popover-header strong');
    const sentHeader = sentHeaders[sentHeaders.length - 1];
    expect(sentHeader?.textContent?.trim()).toBe('Sent to 5 suppliers');
  });

  it('provides English and Arabic recipientsDraftHeader translation keys', () => {
    for (const catalog of [enCatalog, arCatalog]) {
      const history = (catalog.rfq as { history: Record<string, unknown> }).history;
      expect(history['recipientsDraftHeader']).toBeTruthy();
      expect(history['recipientsDraftHeader']).toContain('{{count}}');
      expect(history['neededByPassedTitle']).toBeTruthy();
      expect(history['neededByPassedMessage']).toBeTruthy();
      expect(history['neededByPassedConfirm']).toBeTruthy();
      expect(history['neededByPassedCancel']).toBeTruthy();
      expect(history['neededByPastWarning']).toBeUndefined();
    }
  });

  async function openRecipientsPopover(): Promise<HTMLButtonElement> {
    fixture.detectChanges();
    const trigger = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[data-testid="rfq-recipients-button"]',
    )!;
    trigger.focus();
    trigger.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return trigger;
  }

  it('opens a named dialog disclosure and moves focus inside', async () => {
    const trigger = await openRecipientsPopover();
    const dialog = document.querySelector<HTMLElement>('.recipients-popover[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(trigger.getAttribute('aria-controls')).toBe(dialog.id);
    const title = document.getElementById(dialog.getAttribute('aria-labelledby')!);
    expect(title?.textContent).toContain('3 suppliers');
    expect(dialog.contains(document.activeElement)).toBeTrue();
    expect(dialog.querySelector('[role="menuitem"]')).toBeNull();
    expect(dialog.querySelector('.status-dot')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('names and positions the recipients dialog in Arabic', async () => {
    TestBed.inject(TranslateService).use('ar');
    await openRecipientsPopover();
    const dialog = document.querySelector<HTMLElement>('.recipients-popover')!;
    const title = document.getElementById(dialog.getAttribute('aria-labelledby')!);
    expect(title?.textContent?.trim()).toBe(arCatalog.rfq.history.recipientsDraftHeader.replace('{{count}}', '3'));
    expect(dialog.closest('[dir]')?.getAttribute('dir')).toBe('rtl');
  });

  it('closes on Escape and restores focus to the trigger', async () => {
    const trigger = await openRecipientsPopover();
    document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.querySelector('.recipients-popover')).toBeNull();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(trigger);
  });

  it('keeps the footer link in the dialog tab order and focus trap', async () => {
    await openRecipientsPopover();
    const dialog = document.querySelector<HTMLElement>('.recipients-popover')!;
    const link = dialog.querySelector<HTMLAnchorElement>('.view-all-link')!;
    expect(link.textContent).toContain('View all recipients');
    expect(link.getAttribute('href')).toBe('/rfq/rfq-draft-1?tab=recipients');
    expect(link.tabIndex).toBe(0);
    // Synthetic Tab events cannot invoke browser navigation in Karma. Exercise the
    // focus trap's end anchor to verify its first tabbable target is the footer.
    const endAnchor = dialog.nextElementSibling as HTMLElement;
    expect(endAnchor.classList.contains('cdk-focus-trap-anchor')).toBeTrue();
    endAnchor.focus();
    expect(document.activeElement).toBe(link);
  });

  it('closes on an outside click and restores focus to the trigger', async () => {
    const trigger = await openRecipientsPopover();
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.querySelector('.recipients-popover')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('renders the loading spinner while recipients are pending', async () => {
    const pending = new Subject<RfqDetail>();
    rfqApiSpy.getRfq.and.returnValue(pending);
    await openRecipientsPopover();
    const spinner = document.querySelector('.recipients-popover mat-spinner');
    expect(spinner?.getAttribute('aria-label')).toBe('Loading recipients');
    expect(document.querySelector('.recipients-popover .recipient-row')).toBeNull();
    expect(document.querySelector('.recipients-popover .view-all-link')).not.toBeNull();
  });

  it('renders the recipients error inside the open dialog', async () => {
    rfqApiSpy.getRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    await openRecipientsPopover();
    const error = document.querySelector('.recipients-popover [role="alert"]');
    expect(error?.textContent?.trim()).toBe(enCatalog.rfq.history.recipientsLoadError);
    expect(document.querySelector('.recipients-popover mat-spinner')).toBeNull();
    expect(document.querySelector('.recipients-popover .view-all-link')).not.toBeNull();
  });

  describe('Responsive columns (PPS-94)', () => {
    it('shows all columns at desktop (>= 1200px)', () => {
      component.isBelow1200.set(false);
      component.isBelow768.set(false);
      expect(component.displayedColumns()).toEqual([
        'reference',
        'status',
        'neededBy',
        'sentAt',
        'recipients',
        'responses',
        'actions',
      ]);
      expect(component.showCountsInMenu()).toBeFalse();
    });

    it('hides recipients and responses below 1200px', () => {
      component.isBelow1200.set(true);
      component.isBelow768.set(false);
      expect(component.displayedColumns()).toEqual(['reference', 'status', 'neededBy', 'sentAt', 'actions']);
      expect(component.showCountsInMenu()).toBeTrue();
    });

    it('shows only status, neededBy, and actions below 768px', () => {
      component.isBelow1200.set(true);
      component.isBelow768.set(true);
      expect(component.displayedColumns()).toEqual(['reference', 'status', 'neededBy', 'actions']);
      expect(component.showCountsInMenu()).toBeTrue();
    });

    it('updates displayed columns when BreakpointObserver emits matches', () => {
      const tabletSubject = new Subject<BreakpointState>();
      const mobileSubject = new Subject<BreakpointState>();

      breakpointSpy.observe.and.callFake((query: string | readonly string[]) => {
        const q = Array.isArray(query) ? query.join(',') : query;
        if (q.includes('1199.98')) return tabletSubject;
        if (q.includes('767.98')) return mobileSubject;
        return of({ matches: false, breakpoints: {} });
      });

      const respFixture = TestBed.createComponent(HistoryComponent);
      const respComp = respFixture.componentInstance;
      respFixture.detectChanges();

      // Tablet size (below 1200px, not below 768px)
      tabletSubject.next({ matches: true, breakpoints: { '(max-width: 1199.98px)': true } });
      mobileSubject.next({ matches: false, breakpoints: { '(max-width: 767.98px)': false } });
      expect(respComp.displayedColumns()).toEqual(['reference', 'status', 'neededBy', 'sentAt', 'actions']);

      // Mobile size (below 768px)
      mobileSubject.next({ matches: true, breakpoints: { '(max-width: 767.98px)': true } });
      expect(respComp.displayedColumns()).toEqual(['reference', 'status', 'neededBy', 'actions']);

      // Back to desktop (above 1200px)
      tabletSubject.next({ matches: false, breakpoints: { '(max-width: 1199.98px)': false } });
      mobileSubject.next({ matches: false, breakpoints: { '(max-width: 767.98px)': false } });
      expect(respComp.displayedColumns()).toEqual([
        'reference',
        'status',
        'neededBy',
        'sentAt',
        'recipients',
        'responses',
        'actions',
      ]);
    });
  });

  describe('accessible names contain visible text (axe label-content-name-mismatch)', () => {
    const testCounts = [0, 1, 2, 3, 11];

    it('ensures recipients and responses aria-labels contain raw count string and row-open label contains status in en', () => {
      const translate = TestBed.inject(TranslateService);
      translate.use('en');

      for (const count of testCounts) {
        expect(component.getRecipientsAriaLabel(count)).toContain(String(count));
        expect(component.getResponsesAriaLabel(count)).toContain(String(count));
      }

      for (const rfq of mockRfqs) {
        const expectedStatus = translate.instant(`rfq.history.status_${rfq.status}`);
        expect(component.getRowAccessibleName(rfq)).toContain(expectedStatus);
      }
    });

    it('ensures recipients and responses aria-labels contain raw count string and row-open label contains status in ar', () => {
      const translate = TestBed.inject(TranslateService);
      translate.use('ar');

      for (const count of testCounts) {
        expect(component.getRecipientsAriaLabel(count)).toContain(String(count));
        expect(component.getResponsesAriaLabel(count)).toContain(String(count));
      }

      for (const rfq of mockRfqs) {
        const expectedStatus = translate.instant(`rfq.history.status_${rfq.status}`);
        expect(component.getRowAccessibleName(rfq)).toContain(expectedStatus);
      }
    });
  });
  for (const status of [0, 503]) {
    it(`reuses the send key after ${status}, rotates on success, and blocks concurrent sends`, () => {
      component.currentMembershipId.set(mockRfqs[0].created_by_membership_id);
      dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
      rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status })));
      component.onSendDraft(mockRfqs[0]);
      const first = rfqApiSpy.sendRfq.calls.mostRecent().args[1];
      const pending = new Subject<RfqSendResponse>();
      rfqApiSpy.sendRfq.and.returnValue(pending);
      component.onSendDraft(mockRfqs[0]);
      component.onSendDraft(mockRfqs[0]);
      expect(rfqApiSpy.sendRfq).toHaveBeenCalledTimes(2);
      expect(rfqApiSpy.sendRfq.calls.mostRecent().args[1]).toBe(first);
      pending.next({ rfq: { id: mockRfqs[0].id, status: 'sent' }, recipients: [] } as unknown as RfqSendResponse);
      rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
      component.onSendDraft(mockRfqs[0]);
      const rejected = rfqApiSpy.sendRfq.calls.mostRecent().args[1];
      expect(rejected).not.toBe(first);
      component.onSendDraft(mockRfqs[0]);
      expect(rfqApiSpy.sendRfq.calls.mostRecent().args[1]).not.toBe(rejected);
    });
  }

});
