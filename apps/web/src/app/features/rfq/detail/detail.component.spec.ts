import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter, Router, ActivatedRoute, convertToParamMap } from '@angular/router';
import { HttpErrorResponse, provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog } from '@angular/material/dialog';
import { BehaviorSubject, of, throwError } from 'rxjs';

import { DetailComponent } from './detail.component';
import { RfqApi, RfqDetail, RfqResponseComparisonList } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
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

    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['getRfq', 'listResponses', 'sendRfq', 'listGuardrails']);
    rfqApiSpy.getRfq.and.returnValue(of(mockSentDetail));
    rfqApiSpy.listResponses.and.returnValue(of(mockResponses));
    rfqApiSpy.listGuardrails.and.returnValue(of([]));

    apiSpy = jasmine.createSpyObj('ApiService', ['members', 'listBranches', 'suppliers', 'products']);
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
    }).compileComponents();

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
});
