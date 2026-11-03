import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter, Router, ActivatedRoute, convertToParamMap } from '@angular/router';
import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { BehaviorSubject, of, Subject, throwError } from 'rxjs';

import { DetailComponent } from './detail.component';
import { RfqActionKeys, RfqApi, RfqDetail, RfqRecipient, RfqResponseComparisonList, RfqSendResponse } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { FormatService } from '../../../core/format/format.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';

describe('DetailComponent (RFQ Details)', () => {
  let component: DetailComponent;
  let fixture: ComponentFixture<DetailComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let apiSpy: jasmine.SpyObj<ApiService>;
  let router: Router;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;

  let paramMapSubject: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let queryParamMapSubject: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  const mockSentDetail: RfqDetail = {
    rfq: {
      id: 'rfq-sent-1',
      tenant_id: 't-1',
      created_by_membership_id: 'm-creator',
      status: 'sent',
      needed_by_date: '2026-11-15',
      tenant_terms: 'Payment net 30 days',
      idempotency_key: 'idem-1',
      created_at: '2026-10-20T10:00:00Z',
    },
    lines: [
      {
        id: 'line-1',
        tenant_id: 't-1',
        rfq_id: 'rfq-sent-1',
        workspace_product_id: 'prod-1',
        quantity: '10.500000',
        created_at: '2026-10-20T10:00:00Z',
        position: 1,
        product_name: 'Organic Olive Oil',
        product_variant: '5L Tin',
      },
      {
        id: 'line-2',
        tenant_id: 't-1',
        rfq_id: 'rfq-sent-1',
        workspace_product_id: 'prod-2',
        quantity: 20,
        created_at: '2026-10-20T10:00:00Z',
        position: 2,
        product_name: null,
        product_variant: null,
      },
    ],
    recipients: [
      {
        id: 'rec-1',
        tenant_id: 't-1',
        rfq_id: 'rfq-sent-1',
        supplier_id: 'sup-1',
        status: 'sent',
        outbound_message_id: 'msg-1',
        sent_at: '2026-10-28T14:14:00Z',
        created_at: '2026-10-20T10:00:00Z',
        supplier_name: 'Al-Madina Foods',
        supplier_contact_email: 'contact@almadina.test',
      },
      {
        id: 'rec-2',
        tenant_id: 't-1',
        rfq_id: 'rfq-sent-1',
        supplier_id: 'sup-2',
        status: 'failed',
        outbound_message_id: null,
        sent_at: null,
        created_at: '2026-10-20T10:00:00Z',
        supplier_name: null,
        supplier_contact_email: null,
      },
    ],
  };

  const mockDraftDetail: RfqDetail = {
    rfq: {
      id: 'rfq-draft-1',
      tenant_id: 't-1',
      created_by_membership_id: 'm-creator',
      status: 'draft',
      needed_by_date: '2026-12-01',
      tenant_terms: null,
      idempotency_key: 'idem-2',
      created_at: '2026-10-25T08:00:00Z',
    },
    lines: [],
    recipients: [
      {
        id: 'rec-3',
        tenant_id: 't-1',
        rfq_id: 'rfq-draft-1',
        supplier_id: 'sup-3',
        status: 'draft',
        outbound_message_id: null,
        sent_at: null,
        created_at: '2026-10-25T08:00:00Z',
        supplier_name: 'Nile Traders',
        supplier_contact_email: 'sales@nile.test',
      },
    ],
  };

  const mockResponses: RfqResponseComparisonList = {
    items: [
      {
        id: 'resp-1',
        rfq_id: 'rfq-sent-1',
        supplier_id: 'sup-1',
        quotation_id: 'quote-1',
        submitted_at: '2026-10-28T15:00:00Z',
        quotation_status: 'extracted',
        lines: [],
      },
    ],
  };

  beforeEach(async () => {
    paramMapSubject = new BehaviorSubject(convertToParamMap({ id: 'rfq-sent-1' }));
    queryParamMapSubject = new BehaviorSubject(convertToParamMap({}));

    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['getRfq', 'listResponses', 'sendRfq', 'cancelRfq', 'listGuardrails']);
    rfqApiSpy.getRfq.and.returnValue(of(mockSentDetail));
    rfqApiSpy.listResponses.and.returnValue(of(mockResponses));
    rfqApiSpy.listGuardrails.and.returnValue(of([]));

    apiSpy = jasmine.createSpyObj('ApiService', [
      'members',
      'listBranches',
      'suppliers',
      'products',
      'supplier',
      'product',
    ]);
    apiSpy.supplier.and.returnValue(throwError(() => new Error('not found')));
    apiSpy.product.and.returnValue(throwError(() => new Error('not found')));
    apiSpy.members.and.returnValue(of({
      items: [{
        id: 'm-creator',
        email: 'creator@test.com',
        role: 'owner',
        status: 'active',
        mfa_enabled: false,
        created_at: '2026-01-01T00:00:00Z',
      }],
      next_cursor: null,
    }));
    apiSpy.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    apiSpy.suppliers.and.returnValue(of({ items: [], next_cursor: null }));
    apiSpy.products.and.returnValue(of({ items: [], next_cursor: null }));

    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);

    await TestBed.configureTestingModule({
      imports: [DetailComponent],
      providers: [
        provideNoopAnimations(),
        provideTranslateService(),
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: RfqApi, useValue: rfqApiSpy },
        { provide: ApiService, useValue: apiSpy },
        { provide: MatSnackBar, useValue: snackBarSpy },
        { provide: MatDialog, useValue: dialogSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: paramMapSubject.asObservable(),
            queryParamMap: queryParamMapSubject.asObservable(),
            snapshot: {
              paramMap: paramMapSubject.value,
              queryParamMap: queryParamMapSubject.value,
            },
          },
        },
        {
          provide: SessionService,
          useValue: {
            role: signal<'owner' | null>('owner'),
            hasRole: () => true,
            isAuthenticated: () => true,
            activeLocale: () => 'en',
            currentMember: () => ({ email: 'creator@test.com' }),
            tenant: () => ({ id: 't-1' }),
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

    fixture = TestBed.createComponent(DetailComponent);
    component = fixture.componentInstance;
    router = TestBed.inject(Router);
    spyOn(router, 'navigate');
    fixture.detectChanges();
  });

  describe('cancellation', () => {
    for (const status of [0, 503, 408, 429]) {
      it(`retains the cancel key after ${status} and rotates after success or definitive rejection`, () => {
        component.rfqId.set(mockSentDetail.rfq.id);
        component.rfqDetail.set(mockSentDetail);
        dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status })));
        component.onCancelRfq();
        const first = rfqApiSpy.cancelRfq.calls.mostRecent().args[1];
        expect(first).toEqual(jasmine.any(String));
        const pending = new Subject<RfqDetail['rfq']>();
        rfqApiSpy.cancelRfq.and.returnValue(pending);
        component.onCancelRfq();
        component.onCancelRfq();
        expect(rfqApiSpy.cancelRfq).toHaveBeenCalledTimes(2);
        expect(rfqApiSpy.cancelRfq.calls.mostRecent().args[1]).toBe(first);
        pending.next(mockSentDetail.rfq);
        pending.complete();
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
        component.onCancelRfq();
        const rejected = rfqApiSpy.cancelRfq.calls.mostRecent().args[1];
        expect(rejected).not.toBe(first);
        component.onCancelRfq();
        expect(rfqApiSpy.cancelRfq.calls.mostRecent().args[1]).not.toBe(rejected);
      });
    }

    it('shows Cancel for an owner on another buyer’s RFQ, and buyers only on their own', () => {
      const role = spyOn(TestBed.inject(SessionService), 'hasRole');
      role.and.callFake((...roles) => roles.includes('owner'));
      component.currentMembershipId.set('another-member');
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-detail-cancel-button"]')).not.toBeNull();
      role.and.callFake((...roles) => roles.includes('buyer'));
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-detail-cancel-button"]')).toBeNull();
      component.currentMembershipId.set('m-creator');
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-detail-cancel-button"]')).not.toBeNull();
      role.and.returnValue(false);
      expect(component.canCancel()).toBeFalse();
    });

    for (const status of ['draft', 'sent', 'responded', 'expired'] as const) {
      it(`allows cancellation of ${status}`, () => {
        component.rfqDetail.set({ ...mockSentDetail, rfq: { ...mockSentDetail.rfq, status } });
        expect(component.canCancel()).toBeTrue();
      });
    }

    for (const status of ['converted', 'cancelled'] as const) {
      it(`hides Cancel for ${status}`, () => {
        component.rfqDetail.set({ ...mockSentDetail, rfq: { ...mockSentDetail.rfq, status } });
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-detail-cancel-button"]')).toBeNull();
        component.onCancelRfq();
        expect(dialogSpy.open).not.toHaveBeenCalled();
      });
    }

    it('confirms a destructive action and calls cancel once despite repeated clicks or confirmation emissions', () => {
      const confirmation = new Subject<boolean>();
      const result = new Subject<RfqDetail['rfq']>();
      dialogSpy.open.and.returnValue({ afterClosed: () => confirmation } as unknown as MatDialogRef<CatalogueConfirmDialogComponent>);
      rfqApiSpy.cancelRfq.and.returnValue(result);
      const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-testid="rfq-detail-cancel-button"]')!;
      button.click();
      button.click();
      expect(dialogSpy.open).toHaveBeenCalledOnceWith(CatalogueConfirmDialogComponent, jasmine.objectContaining({
        data: jasmine.objectContaining({ isDestructive: true, confirmKey: 'rfq.cancel.confirm', cancelKey: 'rfq.cancel.keep' }),
      }));
      expect(rfqApiSpy.cancelRfq).not.toHaveBeenCalled();
      confirmation.next(true);
      confirmation.next(true);
      fixture.detectChanges();
      expect(button.disabled).toBeTrue();
      component.onCancelRfq();
      expect(rfqApiSpy.cancelRfq).toHaveBeenCalledOnceWith('rfq-sent-1', jasmine.any(String));
      const cancelled: RfqDetail = { ...mockSentDetail, rfq: { ...mockSentDetail.rfq, status: 'cancelled', cancelled_at: '2026-11-03T10:00:00Z' } };
      rfqApiSpy.getRfq.and.returnValue(of(cancelled));
      rfqApiSpy.getRfq.calls.reset();
      result.next(cancelled.rfq);
      result.complete();
      fixture.detectChanges();
      expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-sent-1');
      expect(snackBarSpy.open).toHaveBeenCalledWith(enCatalog.rfq.cancel.success, jasmine.any(String), jasmine.any(Object));
      const page = fixture.nativeElement as HTMLElement;
      for (const action of ['cancel', 'edit', 'send', 'retry']) {
        expect(page.querySelector(`[data-testid="rfq-detail-${action}-button"]`)).toBeNull();
      }
      expect(page.querySelector('.status-badge')?.textContent).toContain('Cancelled');
      expect(page.querySelector('[data-testid="rfq-detail-cancelled-at"]')?.textContent).toContain(component.formatDate(cancelled.rfq.cancelled_at));
      expect(component.getRecipientReplyState(cancelled.recipients[0]).status).toBe('no_reply');
      expect(component.getRecipientReplyState({ ...cancelled.recipients[0], response_count: 1 }).status).toBe('replied');
    });

    it('keeps the RFQ when confirmation is declined', () => {
      dialogSpy.open.and.returnValue({ afterClosed: () => of(false) } as MatDialogRef<CatalogueConfirmDialogComponent>);
      component.onCancelRfq();
      expect(rfqApiSpy.cancelRfq).not.toHaveBeenCalled();
      expect(component.cancelling()).toBeFalse();
    });

    for (const [status, reason, key] of [
      [403, 'not_creator', 'notCreator'], [409, 'not_cancellable', 'notCancellable'], [500, '', 'error'],
    ] as const) {
      it(`handles cancellation error ${status}`, () => {
        dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent>);
        rfqApiSpy.cancelRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status, error: { details: { reason } } })));
        rfqApiSpy.getRfq.calls.reset();
        component.onCancelRfq();
        expect(snackBarSpy.open).toHaveBeenCalledWith(enCatalog.rfq.cancel[key], jasmine.any(String), jasmine.any(Object));
        expect(component.cancelling()).toBeFalse();
        expect(rfqApiSpy.getRfq.calls.count()).toBe(status === 409 ? 1 : 0);
      });
    }

    it('provides cancellation copy and status in English and Arabic', () => {
      for (const catalog of [enCatalog, arCatalog]) {
        expect(catalog.rfq.history.status_cancelled).toBeTruthy();
        expect(catalog.rfq.detail.cancelledAtLabel).toBeTruthy();
        expect(catalog.rfq.compare.rfqCancelled).toBeTruthy();
        for (const value of Object.values(catalog.rfq.cancel)) expect(value.trim()).toBeTruthy();
      }
      expect(arCatalog.rfq.history.status_cancelled).toMatch(/[\u0600-\u06ff]/);
    });
  });

  it('loads RFQ detail and responses on init', () => {
    expect(component).toBeTruthy();
    expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-sent-1');
    expect(rfqApiSpy.listResponses).toHaveBeenCalledWith('rfq-sent-1');
    expect(component.rfqDetail()).toEqual(mockSentDetail);
  });

  it('renders breadcrumb with sent date and time for sent RFQ', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const breadcrumb = compiled.querySelector('nav.breadcrumb');
    expect(breadcrumb).not.toBeNull();
    expect(breadcrumb?.getAttribute('aria-label')).toBe(TestBed.inject(TranslateService).instant('common.breadcrumbLabel'));
    const link = breadcrumb?.querySelector('a.breadcrumb-link');
    expect(link?.getAttribute('routerLink') ?? link?.getAttribute('href')).toBe('/rfq/history');
    expect(breadcrumb?.querySelector('.breadcrumb-current')?.textContent).toContain('RFQ · Sent');
  });

  it('renders breadcrumb with Draft for draft RFQ', async () => {
    rfqApiSpy.getRfq.and.returnValue(of(mockDraftDetail));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-draft-1' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.breadcrumb-current')?.textContent?.trim()).toBe('RFQ · Draft');
  });

  it('renders tabs with correct titles and counts', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const tabLabels = compiled.querySelectorAll('.mat-mdc-tab .mdc-tab__text-label');
    const texts = Array.from(tabLabels).map((el) => el.textContent?.trim());
    expect(texts.some((t) => t?.includes('Details'))).toBeTrue();
    expect(texts.some((t) => t?.includes('Items'))).toBeTrue();
    expect(texts.some((t) => t?.includes('Recipients (2)'))).toBeTrue();
    expect(texts.some((t) => t?.includes('Responses (1)'))).toBeTrue();
  });

  it('syncs tab selection with query parameter ?tab=items', async () => {
    queryParamMapSubject.next(convertToParamMap({ tab: 'items' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.selectedTabIndex()).toBe(1);
  });

  it('updates query param when tab is changed', () => {
    component.onTabChange(2);
    expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
      queryParams: { tab: 'recipients' },
      replaceUrl: true,
    }));
  });

  it('renders items in order with product name, variant, and fallback for null product_name', async () => {
    component.selectedTabIndex.set(1);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const itemRows = compiled.querySelectorAll('[data-testid="detail-item-row"]');
    expect(itemRows.length).toBe(2);

    expect(itemRows[0].textContent).toContain('Organic Olive Oil');
    expect(itemRows[0].textContent).toContain('5L Tin');
    expect(itemRows[0].textContent).toContain('10.5');

    // line-2 has null product_name -> shows fallback "Unknown product"
    expect(itemRows[1].textContent).toContain('Unknown product');
    expect(itemRows[1].textContent).toContain('20');
  });

  it('renders recipients with status, LTR contact email, and fallback for null supplier_name', async () => {
    component.selectedTabIndex.set(2);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const recipientRows = compiled.querySelectorAll('[data-testid="detail-recipient-row"]');
    expect(recipientRows.length).toBe(2);

    expect(recipientRows[0].textContent).toContain('Al-Madina Foods');
    expect(recipientRows[0].querySelector('bdi')?.getAttribute('dir')).toBe('ltr');
    expect(recipientRows[0].querySelector('bdi')?.textContent).toContain('contact@almadina.test');
    expect(recipientRows[0].textContent).toContain('Sent');

    // rec-2 has null supplier_name and null email
    expect(recipientRows[1].textContent).toContain('Unknown supplier');
    expect(recipientRows[1].textContent).toContain('Failed');
  });

  it('renders draft notice and creator actions only when RFQ status is draft', async () => {
    rfqApiSpy.getRfq.and.returnValue(of(mockDraftDetail));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-draft-1' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const draftNotice = compiled.querySelector('[data-testid="rfq-detail-draft-notice"]');
    expect(draftNotice).not.toBeNull();
    expect(compiled.querySelector('[data-testid="rfq-detail-edit-button"]')).not.toBeNull();
    expect(compiled.querySelector('[data-testid="rfq-detail-send-button"]')).not.toBeNull();
  });

  it('displays 404 not-found state when RFQ does not exist', async () => {
    rfqApiSpy.getRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 404 })));
    component.loadRfq('rfq-non-existent');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const notFoundEl = compiled.querySelector('[data-testid="rfq-detail-not-found"]');
    expect(notFoundEl).not.toBeNull();
    expect(notFoundEl?.textContent).toContain('This RFQ was not found');
    const backLink = notFoundEl?.querySelector('a');
    expect(backLink?.getAttribute('routerLink') ?? backLink?.getAttribute('href')).toBe('/rfq/history');
  });

  it('renders responded banner with Compare responses button when status is responded', async () => {
    const mockRespondedDetail: RfqDetail = {
      ...mockSentDetail,
      rfq: {
        ...mockSentDetail.rfq,
        status: 'responded',
      },
    };
    rfqApiSpy.getRfq.and.returnValue(of(mockRespondedDetail));
    rfqApiSpy.listResponses.and.returnValue(of({
      items: [
        {
          id: 'resp-1',
          rfq_id: 'rfq-sent-1',
          supplier_id: 'sup-1',
          quotation_id: 'quote-1',
          submitted_at: '2026-10-28T15:00:00Z',
          quotation_status: 'reviewed',
          lines: [],
        },
        {
          id: 'resp-2',
          rfq_id: 'rfq-sent-1',
          supplier_id: 'sup-2',
          quotation_id: 'quote-2',
          submitted_at: '2026-10-28T16:00:00Z',
          quotation_status: 'reviewed',
          lines: [],
        },
      ],
    }));

    component.loadRfq('rfq-sent-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const banner = compiled.querySelector('[data-testid="rfq-detail-responded-notice"]');
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain('2 responses received');

    const compareBtn = banner?.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-compare-responses-button"]');
    expect(compareBtn).not.toBeNull();
    expect(compareBtn?.textContent?.trim()).toBe('Compare responses');

    compareBtn?.click();
    fixture.detectChanges();
    expect(component.selectedTabIndex()).toBe(3);
    expect(router.navigate).toHaveBeenCalledWith([], {
      relativeTo: jasmine.anything(),
      queryParams: { tab: 'responses' },
      replaceUrl: true,
    });
  });

  it('renders nothing for converted state when RFQ is not converted', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-detail-converted-notice"]')).toBeNull();
    expect(compiled.querySelectorAll('[data-testid="converted-request-link"]').length).toBe(0);
  });

  it('renders converted notice with one link when converted into a single request', async () => {
    const mockConvertedSingle: RfqDetail = {
      ...mockSentDetail,
      rfq: {
        ...mockSentDetail.rfq,
        id: 'rfq-conv-1',
        status: 'converted',
      },
      converted_purchase_request_ids: ['pr-101'],
      request_group_id: null,
    };

    rfqApiSpy.getRfq.and.returnValue(of(mockConvertedSingle));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-conv-1' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const banner = compiled.querySelector('[data-testid="rfq-detail-converted-notice"]');
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain('Converted into request');
    expect(banner?.textContent).toContain('pr-101');

    const links = banner?.querySelectorAll<HTMLAnchorElement>('[data-testid="converted-request-link"]');
    expect(links?.length).toBe(1);
    expect(links?.[0].getAttribute('href')).toBe('/requests/pr-101');
    expect(banner?.querySelector('[data-testid="rfq-detail-group-line"]')).toBeNull();
  });

  it('renders "Converted into 2 requests" with two links and group line when converted into two requests with group', async () => {
    const mockConvertedDouble: RfqDetail = {
      ...mockSentDetail,
      rfq: {
        ...mockSentDetail.rfq,
        id: 'rfq-conv-2',
        status: 'converted',
      },
      converted_purchase_request_ids: ['pr-201', 'pr-202'],
      request_group_id: 'grp-split-1',
    };

    rfqApiSpy.getRfq.and.returnValue(of(mockConvertedDouble));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-conv-2' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const banner = compiled.querySelector('[data-testid="rfq-detail-converted-notice"]');
    expect(banner).not.toBeNull();
    expect(banner?.textContent).toContain('Converted into 2 requests');

    const requestLinks = banner?.querySelectorAll<HTMLAnchorElement>('[data-testid="converted-request-link"]');
    expect(requestLinks?.length).toBe(2);
    expect(requestLinks?.[0].getAttribute('href')).toBe('/requests/pr-201');
    expect(requestLinks?.[1].getAttribute('href')).toBe('/requests/pr-202');

    const groupLine = banner?.querySelector('[data-testid="rfq-detail-group-line"]');
    expect(groupLine).not.toBeNull();
    expect(groupLine?.textContent).toContain('These requests are submitted and approved together');
    const groupLink = groupLine?.querySelector<HTMLAnchorElement>('a');
    expect(groupLink?.getAttribute('href')).toBe('/requests/pr-201');
  });

  it('renders correct Arabic plural forms and group text in Arabic locale', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.use('ar');

    const mockConvertedDouble: RfqDetail = {
      ...mockSentDetail,
      rfq: {
        ...mockSentDetail.rfq,
        id: 'rfq-conv-ar',
        status: 'converted',
      },
      converted_purchase_request_ids: ['pr-301', 'pr-302'],
      request_group_id: 'grp-split-ar',
    };

    rfqApiSpy.getRfq.and.returnValue(of(mockConvertedDouble));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-conv-ar' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const banner = compiled.querySelector('[data-testid="rfq-detail-converted-notice"]');
    expect(banner).not.toBeNull();
    // Dual form in Arabic: "تم التحويل إلى طلبين"
    expect(banner?.textContent).toContain('تم التحويل إلى طلبين');
    // Group line in Arabic: "تُقدَّم هذه الطلبات وتُعتمد معًا"
    expect(banner?.textContent).toContain('تُقدَّم هذه الطلبات وتُعتمد معًا');
  });

  it('opens send confirmation dialog with count and formatted needed-by date in messageParams', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(false),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    rfqApiSpy.getRfq.and.returnValue(of(mockDraftDetail));
    paramMapSubject.next(convertToParamMap({ id: 'rfq-draft-1' }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const sendBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-send-button"]');
    sendBtn?.click();

    const formatService = TestBed.inject(FormatService);
    const expectedDate = formatService.formatDate(mockDraftDetail.rfq.needed_by_date);

    expect(dialogSpy.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          messageParams: jasmine.objectContaining({
            count: mockDraftDetail.recipients.length,
            date: expectedDate,
          }),
        }),
      }),
    );
  });

  it('shows retry notice card for sent RFQ with failed recipient when viewer is creator', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryNotice = compiled.querySelector('[data-testid="rfq-detail-retry-notice"]');
    expect(retryNotice).not.toBeNull();
    expect(retryNotice?.querySelector('h2')?.textContent).toContain('1 supplier has not received this RFQ');
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    expect(retryBtn?.textContent?.trim()).toBe('Retry unsent recipients');
  });

  it('hides retry notice card when all recipients are sent', async () => {
    const allSentDetail: RfqDetail = {
      ...mockSentDetail,
      recipients: mockSentDetail.recipients.map((r) => ({ ...r, status: 'sent' as const })),
    };
    rfqApiSpy.getRfq.and.returnValue(of(allSentDetail));
    component.loadRfq('rfq-sent-all');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-detail-retry-notice"]')).toBeNull();
  });

  it('hides retry notice card when viewer is not creator', async () => {
    component.currentMembershipId.set('m-other-user');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-detail-retry-notice"]')).toBeNull();
  });

  it('hides retry notice card for draft and converted RFQs', async () => {
    // 1. draft status
    rfqApiSpy.getRfq.and.returnValue(of(mockDraftDetail));
    component.loadRfq('rfq-draft-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-detail-retry-notice"]')).toBeNull();

    // 2. converted status
    const convertedDetail: RfqDetail = {
      ...mockSentDetail,
      rfq: { ...mockSentDetail.rfq, status: 'converted' },
    };
    rfqApiSpy.getRfq.and.returnValue(of(convertedDetail));
    component.loadRfq('rfq-conv-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.querySelector('[data-testid="rfq-detail-retry-notice"]')).toBeNull();
  });

  it('opens confirm dialog and calls sendRfq exactly once even on double click', async () => {
    const sendSubject = new Subject<RfqSendResponse>();
    rfqApiSpy.sendRfq.and.returnValue(sendSubject);

    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();

    // First click triggers dialog -> confirm -> sendRfq
    retryBtn?.click();
    fixture.detectChanges();

    // In flight: button should now be disabled, and a second click must not trigger sendRfq again
    expect(retryBtn?.disabled).toBeTrue();
    retryBtn?.click();
    (component as unknown as { onRetryUnsent?: () => void }).onRetryUnsent?.();

    expect(rfqApiSpy.sendRfq).toHaveBeenCalledTimes(1);
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-sent-1', jasmine.any(String));

    // Complete the in-flight request
    sendSubject.next({ rfq: mockSentDetail.rfq, recipients: mockSentDetail.recipients });
    sendSubject.complete();
    fixture.detectChanges();
  });

  it('reloads RFQ and displays success snackbar on successful retry', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    const successResponse: RfqSendResponse = {
      rfq: mockSentDetail.rfq,
      recipients: [
        { ...mockSentDetail.recipients[0], status: 'sent' },
        { ...mockSentDetail.recipients[1], status: 'sent' },
      ],
    };
    rfqApiSpy.sendRfq.and.returnValue(of(successResponse));

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    const initialGetCalls = rfqApiSpy.getRfq.calls.count();
    retryBtn?.click();
    fixture.detectChanges();

    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-sent-1', jasmine.any(String));
    expect(rfqApiSpy.getRfq).toHaveBeenCalledTimes(initialGetCalls + 1);

    const translate = TestBed.inject(TranslateService);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      translate.instant('rfq.history.sentSuccess', { count: 2 }),
      translate.instant('rfq.history.dismiss'),
      jasmine.objectContaining({ duration: 5000 }),
    );
  });

  it('shows translated message for HTTP 422 needed_by_in_past and re-enables button', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    const errorResponse = new HttpErrorResponse({
      status: 422,
      error: { details: { reason: 'needed_by_in_past' } },
    });
    rfqApiSpy.sendRfq.and.returnValue(throwError(() => errorResponse));

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    retryBtn?.click();
    fixture.detectChanges();

    const translate = TestBed.inject(TranslateService);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      translate.instant('rfq.create.neededByPastError'),
      translate.instant('rfq.history.dismiss'),
      jasmine.objectContaining({ duration: 5000 }),
    );

    // Button should be re-enabled after error
    expect((component as unknown as { retrying?: () => boolean }).retrying?.()).toBeFalse();
    expect(retryBtn?.disabled).toBeFalse();
  });

  it('shows translated message for HTTP 403 error', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 403 })));

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    retryBtn?.click();
    fixture.detectChanges();

    const translate = TestBed.inject(TranslateService);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      translate.instant('rfq.creatorOnly'),
      translate.instant('rfq.history.dismiss'),
      jasmine.objectContaining({ duration: 5000 }),
    );
  });

  it('shows generic send error for other HTTP errors', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    retryBtn?.click();
    fixture.detectChanges();

    const translate = TestBed.inject(TranslateService);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      translate.instant('rfq.history.sendError'),
      translate.instant('rfq.history.dismiss'),
      jasmine.objectContaining({ duration: 5000 }),
    );
  });

  it('proves no placeholder is left unfilled by interpolating real en and ar strings for confirm dialog', async () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(false),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const retryBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
    expect(retryBtn).not.toBeNull();
    retryBtn?.click();
    fixture.detectChanges();

    expect(dialogSpy.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          titleKey: 'rfq.detail.confirmRetryTitle',
          messageKey: 'rfq.detail.confirmRetryMessage',
          confirmKey: 'rfq.detail.confirmRetryButton',
          cancelKey: 'rfq.detail.cancelRetryButton',
        }),
      }),
    );

    const callArgs = dialogSpy.open.calls.mostRecent().args;
    const data = callArgs[1]?.data as {
      messageKey: string;
      messageParams?: Record<string, unknown>;
    };

    expect(data.messageParams).toBeDefined();

    const getNested = (obj: Record<string, unknown>, path: string): string => {
      return path.split('.').reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], obj) as string;
    };

    const enTemplate = getNested(enCatalog as Record<string, unknown>, data.messageKey);
    const arTemplate = getNested(arCatalog as Record<string, unknown>, data.messageKey);

    expect(typeof enTemplate).toBe('string');
    expect(typeof arTemplate).toBe('string');

    const interpolate = (template: string, params: Record<string, unknown>) =>
      template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_match, key) =>
        params[key] !== undefined ? String(params[key]) : _match,
      );

    const enResult = interpolate(enTemplate, data.messageParams ?? {});
    const arResult = interpolate(arTemplate, data.messageParams ?? {});

    expect(enResult).not.toMatch(/\{\{.*?\}\}/);
    expect(arResult).not.toMatch(/\{\{.*?\}\}/);
  });

  describe('PPS-176 / P-142: Supplier reply status and summary', () => {
    const baseRecipient: RfqRecipient = {
      id: 'rec-test-1',
      tenant_id: 't-1',
      rfq_id: 'rfq-sent-1',
      supplier_id: 'sup-1',
      status: 'sent',
      outbound_message_id: 'msg-1',
      sent_at: '2026-10-28T14:14:00Z',
      created_at: '2026-10-20T10:00:00Z',
      supplier_name: 'Al-Madina Foods',
      supplier_contact_email: 'contact@almadina.test',
    };

    const pastDate = '2020-01-01';
    const futureDate = '2099-01-01';

    describe('getRecipientReplyState (five states)', () => {
      it('derives «Not delivered» for status draft or failed regardless of response_count', () => {
        const draftRec: RfqRecipient = { ...baseRecipient, status: 'draft', response_count: 0 };
        const failedRec: RfqRecipient = { ...baseRecipient, status: 'failed', response_count: 2 };
        const stateDraft = component.getRecipientReplyState(draftRec, { status: 'sent', needed_by_date: futureDate });
        const stateFailed = component.getRecipientReplyState(failedRec, { status: 'sent', needed_by_date: futureDate });

        expect(stateDraft.status).toBe('not_delivered');
        expect(stateDraft.icon).toBe('block');
        expect(stateDraft.label).toBe('Not delivered');
        expect(stateDraft.isOverdue).toBeFalse();

        expect(stateFailed.status).toBe('not_delivered');
        expect(stateFailed.icon).toBe('block');
        expect(stateFailed.label).toBe('Not delivered');
      });

      it('derives «Replied» for status sent and response_count > 0 (with count when > 1)', () => {
        const singleReply: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: 1 };
        const multiReply: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: 3 };

        const stateSingle = component.getRecipientReplyState(singleReply, { status: 'sent', needed_by_date: pastDate });
        const stateMulti = component.getRecipientReplyState(multiReply, { status: 'sent', needed_by_date: pastDate });

        expect(stateSingle.status).toBe('replied');
        expect(stateSingle.icon).toBe('check');
        expect(stateSingle.label).toBe('Replied');
        expect(stateSingle.isOverdue).toBeFalse();

        expect(stateMulti.status).toBe('replied');
        expect(stateMulti.icon).toBe('check');
        expect(stateMulti.label).toBe('Replied (3)');
        expect(stateMulti.isOverdue).toBeFalse();
      });

      it('derives «No reply» for status sent, no reply, when RFQ status is expired or converted', () => {
        const noReplyRec: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: 0 };

        const stateExpired = component.getRecipientReplyState(noReplyRec, { status: 'expired', needed_by_date: pastDate });
        const stateConverted = component.getRecipientReplyState(noReplyRec, { status: 'converted', needed_by_date: futureDate });

        expect(stateExpired.status).toBe('no_reply');
        expect(stateExpired.icon).toBe('close');
        expect(stateExpired.label).toBe('No reply');
        expect(stateExpired.isOverdue).toBeFalse();

        expect(stateConverted.status).toBe('no_reply');
        expect(stateConverted.icon).toBe('close');
        expect(stateConverted.label).toBe('No reply');
      });

      it('derives «Overdue — needed by <date>» for status sent, no reply, RFQ sent/responded and needed_by_date in past', () => {
        const noReplyRec: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: 0 };

        const stateSentOverdue = component.getRecipientReplyState(noReplyRec, { status: 'sent', needed_by_date: pastDate });
        const stateRespondedOverdue = component.getRecipientReplyState(noReplyRec, { status: 'responded', needed_by_date: pastDate });

        expect(stateSentOverdue.status).toBe('overdue');
        expect(stateSentOverdue.icon).toBe('warning');
        expect(stateSentOverdue.isOverdue).toBeTrue();
        expect(stateSentOverdue.label).toContain('Overdue — needed by');

        expect(stateRespondedOverdue.status).toBe('overdue');
        expect(stateRespondedOverdue.icon).toBe('warning');
        expect(stateRespondedOverdue.isOverdue).toBeTrue();
      });

      it('derives «Awaiting reply» otherwise (sent, no reply, not yet due)', () => {
        const noReplyRec: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: 0 };

        const stateAwaiting = component.getRecipientReplyState(noReplyRec, { status: 'sent', needed_by_date: futureDate });

        expect(stateAwaiting.status).toBe('awaiting_reply');
        expect(stateAwaiting.icon).toBe('schedule');
        expect(stateAwaiting.label).toBe('Awaiting reply');
        expect(stateAwaiting.isOverdue).toBeFalse();
      });

      it('treats response_count undefined as 0', () => {
        const undefinedCountRec: RfqRecipient = { ...baseRecipient, status: 'sent', response_count: undefined };

        const stateAwaiting = component.getRecipientReplyState(undefinedCountRec, { status: 'sent', needed_by_date: futureDate });
        expect(stateAwaiting.status).toBe('awaiting_reply');

        const stateOverdue = component.getRecipientReplyState(undefinedCountRec, { status: 'sent', needed_by_date: pastDate });
        expect(stateOverdue.status).toBe('overdue');
      });
    });

    describe('summary line counts and display', () => {
      it('calculates replied of delivered and overdue counts', () => {
        const detail: RfqDetail = {
          ...mockSentDetail,
          rfq: { ...mockSentDetail.rfq, status: 'sent', needed_by_date: pastDate },
          recipients: [
            { ...baseRecipient, id: 'r1', status: 'sent', response_count: 2 },
            { ...baseRecipient, id: 'r2', status: 'sent', response_count: 1 },
            { ...baseRecipient, id: 'r3', status: 'sent', response_count: 0 },
            { ...baseRecipient, id: 'r4', status: 'failed', response_count: 0 },
          ],
        };

        const counts = component.recipientSummaryCounts(detail);
        expect(counts).toEqual({ replied: 2, delivered: 3, overdue: 1 });

        const summaryText = component.recipientSummaryText(detail);
        expect(summaryText).toBe('2 of 3 suppliers replied · 1 overdue');
      });

      it('omits overdue part when overdue count is 0', () => {
        const detail: RfqDetail = {
          ...mockSentDetail,
          rfq: { ...mockSentDetail.rfq, status: 'sent', needed_by_date: futureDate },
          recipients: [
            { ...baseRecipient, id: 'r1', status: 'sent', response_count: 1 },
            { ...baseRecipient, id: 'r2', status: 'sent', response_count: 0 },
          ],
        };

        const counts = component.recipientSummaryCounts(detail);
        expect(counts).toEqual({ replied: 1, delivered: 2, overdue: 0 });

        const summaryText = component.recipientSummaryText(detail);
        expect(summaryText).toBe('1 of 2 suppliers replied');
      });

      it('renders the summary line under status in Details tab when status is sent or responded', async () => {
        const detail: RfqDetail = {
          ...mockSentDetail,
          rfq: { ...mockSentDetail.rfq, status: 'sent', needed_by_date: pastDate },
          recipients: [
            { ...baseRecipient, id: 'r1', status: 'sent', response_count: 2 },
            { ...baseRecipient, id: 'r2', status: 'sent', response_count: 0 },
          ],
        };
        rfqApiSpy.getRfq.and.returnValue(of(detail));
        component.loadRfq('rfq-sent-1');
        component.selectedTabIndex.set(0);
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const compiled = fixture.nativeElement as HTMLElement;
        const summaryEl = compiled.querySelector('[data-testid="rfq-detail-status-summary"]');
        expect(summaryEl).not.toBeNull();
        expect(summaryEl?.textContent?.trim()).toContain('1 of 2 suppliers replied · 1 overdue');
      });

      it('renders the Reply column in the Recipients tab', async () => {
        const detail: RfqDetail = {
          ...mockSentDetail,
          rfq: { ...mockSentDetail.rfq, status: 'sent', needed_by_date: pastDate },
          recipients: [
            { ...baseRecipient, id: 'r1', status: 'sent', response_count: 1 },
            { ...baseRecipient, id: 'r2', status: 'sent', response_count: 0 },
          ],
        };
        rfqApiSpy.getRfq.and.returnValue(of(detail));
        component.loadRfq('rfq-sent-1');
        component.selectedTabIndex.set(2);
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();

        const compiled = fixture.nativeElement as HTMLElement;
        const replyHeaders = Array.from(compiled.querySelectorAll('th')).map((th) => th.textContent?.trim());
        expect(replyHeaders).toContain('Reply');

        const replyCell1 = compiled.querySelector('[data-testid="recipient-reply-r1"]');
        expect(replyCell1?.textContent?.trim()).toContain('Replied');

        const replyCell2 = compiled.querySelector('[data-testid="recipient-reply-r2"]');
        expect(replyCell2?.classList).toContain('reply-overdue');
        expect(replyCell2?.textContent?.trim()).toContain('Overdue');
      });
    });

    describe('Arabic catalogue strings for new keys', () => {
      it('has Arabic strings for all new reply status and summary keys with matching interpolation', () => {
        const newKeys = [
          'rfq.detail.reply',
          'rfq.detail.replyStatus_notDelivered',
          'rfq.detail.replyStatus_replied',
          'rfq.detail.replyStatus_repliedCount',
          'rfq.detail.replyStatus_noReply',
          'rfq.detail.replyStatus_overdue',
          'rfq.detail.replyStatus_awaiting',
          'rfq.detail.suppliersRepliedTitle',
          'rfq.detail.suppliersReplied.zero',
          'rfq.detail.suppliersReplied.one',
          'rfq.detail.suppliersReplied.two',
          'rfq.detail.suppliersReplied.few',
          'rfq.detail.suppliersReplied.many',
          'rfq.detail.suppliersReplied.other',
          'rfq.detail.suppliersOverdueTitle',
          'rfq.detail.suppliersOverdue.zero',
          'rfq.detail.suppliersOverdue.one',
          'rfq.detail.suppliersOverdue.two',
          'rfq.detail.suppliersOverdue.few',
          'rfq.detail.suppliersOverdue.many',
          'rfq.detail.suppliersOverdue.other',
        ];

        const getNested = (obj: Record<string, unknown>, path: string): string => {
          return path.split('.').reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], obj) as string;
        };

        for (const key of newKeys) {
          const enVal = getNested(enCatalog as Record<string, unknown>, key);
          const arVal = getNested(arCatalog as Record<string, unknown>, key);
          expect(typeof enVal).withContext(`EN missing ${key}`).toBe('string');
          expect(typeof arVal).withContext(`AR missing ${key}`).toBe('string');
          expect(enVal.length).withContext(`EN empty ${key}`).toBeGreaterThan(0);
          expect(arVal.length).withContext(`AR empty ${key}`).toBeGreaterThan(0);
        }
      });
    });
  });

  describe('PPS-180: Resilient and honest RFQ Detail', () => {
    it('non-404 error shows Retry + back link and Retry reloads', fakeAsync(() => {
      rfqApiSpy.getRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
      component.loadRfq('rfq-error-500');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const errorEl = compiled.querySelector('.error-state');
      expect(errorEl).not.toBeNull();
      expect(errorEl?.getAttribute('role')).toBe('alert');
      expect(errorEl?.textContent).toContain('Failed to load RFQ details.');

      const retryBtn = errorEl?.querySelector<HTMLButtonElement>('[data-testid="rfq-detail-retry-button"]');
      expect(retryBtn).not.toBeNull();
      expect(retryBtn?.textContent?.trim()).toBe('Retry');

      const backLink = errorEl?.querySelector<HTMLAnchorElement>('.back-link');
      expect(backLink).not.toBeNull();
      expect(backLink?.textContent?.trim()).toBe('Back to RFQ History');
      expect(backLink?.getAttribute('routerLink') ?? backLink?.getAttribute('href')).toBe('/rfq/history');

      // Now retry reloads
      rfqApiSpy.getRfq.and.returnValue(of(mockSentDetail));
      retryBtn?.click();
      fixture.detectChanges();

      expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-error-500');
      expect(component.rfqDetail()).toEqual(mockSentDetail);
      expect(compiled.querySelector('.error-state')).toBeNull();
    }));

    it('switching ids A -> B with A response delayed shows only B data', fakeAsync(() => {
      const subjectA = new Subject<RfqDetail>();
      const subjectB = new Subject<RfqDetail>();

      rfqApiSpy.getRfq.and.callFake((id: string) => {
        if (id === 'rfq-A') return subjectA;
        if (id === 'rfq-B') return subjectB;
        return of(mockSentDetail);
      });

      component.loadRfq('rfq-A');
      fixture.detectChanges();

      expect(component.loading()).toBeTrue();
      expect(component.rfqDetail()).toBeNull();

      component.loadRfq('rfq-B');
      fixture.detectChanges();

      expect(component.loading()).toBeTrue();
      expect(component.rfqDetail()).toBeNull();

      // B responds first
      const detailB: RfqDetail = {
        ...mockSentDetail,
        rfq: { ...mockSentDetail.rfq, id: 'rfq-B' },
      };
      subjectB.next(detailB);
      subjectB.complete();
      fixture.detectChanges();

      expect(component.rfqDetail()?.rfq.id).toBe('rfq-B');

      // A delayed response arrives now
      const detailA: RfqDetail = {
        ...mockSentDetail,
        rfq: { ...mockSentDetail.rfq, id: 'rfq-A' },
      };
      subjectA.next(detailA);
      subjectA.complete();
      fixture.detectChanges();

      expect(component.rfqDetail()?.rfq.id).toBe('rfq-B');
    }));

    it('failed responses request renders tab label without a number', fakeAsync(() => {
      const failedDetail = {
        ...mockSentDetail,
        rfq: { ...mockSentDetail.rfq, id: 'rfq-sent-failed' },
      };
      rfqApiSpy.getRfq.and.returnValue(of(failedDetail));
      rfqApiSpy.listResponses.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));

      component.loadRfq('rfq-sent-failed');
      fixture.detectChanges();
      tick();
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const tabLabels = compiled.querySelectorAll('.mat-mdc-tab .mdc-tab__text-label');
      const texts = Array.from(tabLabels).map((el) => el.textContent?.trim());

      expect(texts.some((t) => t === 'Responses')).toBeTrue();
      expect(texts.some((t) => t?.includes('Responses ('))).toBeFalse();
    }));
  });
  for (const status of [0, 503]) {
    it(`reuses the send key after ${status}, rotates on success, and blocks concurrent sends`, () => {
      component.rfqId.set(mockSentDetail.rfq.id);
      component.rfqDetail.set(mockSentDetail);
      component.currentMembershipId.set(mockSentDetail.rfq.created_by_membership_id);
      dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
      rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status })));
      component.onRetryUnsent();
      const first = rfqApiSpy.sendRfq.calls.mostRecent().args[1];
      const pending = new Subject<RfqSendResponse>();
      rfqApiSpy.sendRfq.and.returnValue(pending);
      component.onRetryUnsent();
      component.onRetryUnsent();
      expect(rfqApiSpy.sendRfq).toHaveBeenCalledTimes(2);
      expect(rfqApiSpy.sendRfq.calls.mostRecent().args[1]).toBe(first);
      pending.next({ rfq: mockSentDetail.rfq, recipients: mockSentDetail.recipients });
      rfqApiSpy.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
      component.onRetryUnsent();
      const rejected = rfqApiSpy.sendRfq.calls.mostRecent().args[1];
      expect(rejected).not.toBe(first);
      component.onRetryUnsent();
      expect(rfqApiSpy.sendRfq.calls.mostRecent().args[1]).not.toBe(rejected);
    });
  }

});

// Exercise the real HTTP boundary here alongside the cancellation UI regression suite.
describe('RfqApi cancellation idempotency', () => {
  let api: RfqApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(withXhr()), provideHttpClientTesting()] });
    api = TestBed.inject(RfqApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('posts no body with the caller-supplied action key', () => {
    const keys = new RfqActionKeys();
    const key = keys.get('cancel:rfq-1');
    api.cancelRfq('rfq-1', key).subscribe();
    const request = http.expectOne((req) => req.url.endsWith('/rfq/rfq-1/cancel'));
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    expect(request.request.headers.get('Idempotency-Key')).toBe(key);
    request.flush({ status: 'cancelled' });
  });

  it('generates a fallback key when the caller does not supply one', () => {
    api.cancelRfq('rfq-1').subscribe();
    const request = http.expectOne((req) => req.url.endsWith('/rfq/rfq-1/cancel'));
    expect(request.request.headers.get('Idempotency-Key')).toEqual(jasmine.any(String));
    request.flush({ status: 'cancelled' });
  });
});
