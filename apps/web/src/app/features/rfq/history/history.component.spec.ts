import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HistoryComponent } from './history.component';
import { RfqApi, RfqSummary, RfqList, RfqSendResponse } from '../rfq-api';
import { Router, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService } from '@ngx-translate/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { ApiService } from '../../../core/api/api.service';

describe('HistoryComponent', () => {
  let component: HistoryComponent;
  let fixture: ComponentFixture<HistoryComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let router: Router;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;

  const mockRfqs: RfqSummary[] = [
    {
      id: 'rfq-draft-1',
      created_by_membership_id: 'm1',
      status: 'draft',
      needed_by_date: '2026-10-10',
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
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['listRfqs', 'sendRfq', 'getRfq']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    const apiSpy = jasmine.createSpyObj('ApiService', ['members']);
    apiSpy.members.and.returnValue(of({ items: [{ id: 'm1', email: 'user@test.com' }], next_cursor: null }));
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);

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
          messageParams: { count: 3 },
        }),
      }),
    );
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-draft-1');
    expect(snackBarSpy.open).toHaveBeenCalled();
    expect(rfqApiSpy.listRfqs).toHaveBeenCalled();
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
});
