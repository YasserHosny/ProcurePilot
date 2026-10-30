import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HistoryComponent } from './history.component';
import { RfqApi, RfqSummary, RfqList, RfqSendResponse } from '../rfq-api';
import { Router, provideRouter } from '@angular/router';
import { of, throwError, Subject } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatMenu } from '@angular/material/menu';
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

  beforeEach(async () => {
    jasmine.clock().install();
    jasmine.clock().mockDate(new Date(2026, 9, 28));
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['listRfqs', 'sendRfq', 'getRfq']);
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

    fixture = TestBed.createComponent(HistoryComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
    spyOn(router, 'navigate');
    fixture.detectChanges();
  });

  afterEach(() => {
    jasmine.clock().uninstall();
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

  it('routes another member’s draft to RFQ details and hides draft actions', async () => {
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

  it('should display error snackbar on load failure', () => {
    rfqApiSpy.listRfqs.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    component.loadRfqs();
    expect(component.loading()).toBeFalse();
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      jasmine.any(String),
      jasmine.any(String),
      { duration: 5000 },
    );
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

    // Second click should use cache
    recipientButtons[0].click();
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
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1');
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

    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1');
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
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1');

    // Reopen popover on the RFQ
    component.loadRecipients('rfq-draft-1');
    expect(rfqApiSpy.getRfq).toHaveBeenCalledTimes(2);
    expect(component.recipientsCache()['rfq-draft-1']?.recipients?.[0].status).toBe('sent');
  });

  it('renders recipientsDraftHeader for draft RFQ and sentToSuppliers for sent RFQ in popover header', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
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
      const history = (catalog.rfq as { history: Record<string, string> }).history;
      expect(history['recipientsDraftHeader']).toBeTruthy();
      expect(history['recipientsDraftHeader']).toContain('{{count}}');
      expect(history['neededByPassedTitle']).toBeTruthy();
      expect(history['neededByPassedMessage']).toBeTruthy();
      expect(history['neededByPassedConfirm']).toBeTruthy();
      expect(history['neededByPassedCancel']).toBeTruthy();
      expect(history['neededByPastWarning']).toBeUndefined();
    }
  });

  it('applies recipients-popover-menu panel class to recipients mat-menu', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const menuDebugEls = fixture.debugElement.queryAll(By.directive(MatMenu));
    const recipientsMatMenu = menuDebugEls
      .map((debugEl) => debugEl.componentInstance as MatMenu)
      .find((menu) => menu.panelClass?.includes('recipients-popover-menu'));
    expect(recipientsMatMenu).toBeDefined();

    const recipientButtons = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[data-testid="rfq-recipients-button"]',
    );
    expect(recipientButtons.length).toBeGreaterThan(0);
    recipientButtons[0].click();
    fixture.detectChanges();
    await fixture.whenStable();

    const panel = document.querySelector('.mat-mdc-menu-panel.recipients-popover-menu');
    expect(panel).not.toBeNull();
  });

  describe('Responsive columns (PPS-94)', () => {
    it('shows all columns at desktop (>= 1200px)', () => {
      component.isBelow1200.set(false);
      component.isBelow768.set(false);
      expect(component.displayedColumns()).toEqual([
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
      expect(component.displayedColumns()).toEqual(['status', 'neededBy', 'sentAt', 'actions']);
      expect(component.showCountsInMenu()).toBeTrue();
    });

    it('shows only status, neededBy, and actions below 768px', () => {
      component.isBelow1200.set(true);
      component.isBelow768.set(true);
      expect(component.displayedColumns()).toEqual(['status', 'neededBy', 'actions']);
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
      expect(respComp.displayedColumns()).toEqual(['status', 'neededBy', 'sentAt', 'actions']);

      // Mobile size (below 768px)
      mobileSubject.next({ matches: true, breakpoints: { '(max-width: 767.98px)': true } });
      expect(respComp.displayedColumns()).toEqual(['status', 'neededBy', 'actions']);

      // Back to desktop (above 1200px)
      tabletSubject.next({ matches: false, breakpoints: { '(max-width: 1199.98px)': false } });
      mobileSubject.next({ matches: false, breakpoints: { '(max-width: 767.98px)': false } });
      expect(respComp.displayedColumns()).toEqual([
        'status',
        'neededBy',
        'sentAt',
        'recipients',
        'responses',
        'actions',
      ]);
    });
  });
});
