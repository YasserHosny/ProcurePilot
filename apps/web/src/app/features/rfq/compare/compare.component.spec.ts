import { signal, WritableSignal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync } from '@angular/core/testing';
import { CompareComponent } from './compare.component';
import { formatExactQuantity, formatLocaleNumber, FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import {
  RfqApi,
  RfqDetail,
  RfqResponseComparison,
  RfqResponseComparisonList,
  PrepareRequestResponse,
  RfqSendResponse,
} from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { ActivatedRoute, Router, UrlTree } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import { of, throwError, Subject } from 'rxjs';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { Branch, Member, Supplier, Product, BasketSplitJob } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';

describe('CompareComponent (RFQ)', () => {
  let component: CompareComponent;
  let fixture: ComponentFixture<CompareComponent>;
  let mockRfqApi: jasmine.SpyObj<RfqApi>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockRouter: jasmine.SpyObj<Router>;
  let mockSnackBar: jasmine.SpyObj<MatSnackBar>;
  let mockDialog: jasmine.SpyObj<MatDialog>;
  let mockSession: jasmine.SpyObj<SessionService>;

  const sentDetail: RfqDetail = {
    rfq: {
      id: 'rfq-1',
      tenant_id: 'tenant-1',
      created_by_membership_id: 'member-1',
      status: 'sent',
      needed_by_date: '2026-10-20',
      tenant_terms: null,
      idempotency_key: 'k-1',
      created_at: '2026-09-25T09:00:00Z',
    },
    lines: [],
    recipients: [],
  };

  const draftDetail: RfqDetail = {
    rfq: {
      ...sentDetail.rfq,
      status: 'draft',
    },
    lines: [],
    recipients: [
      {
        id: 'rec-1',
        tenant_id: 'tenant-1',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-1',
        status: 'draft',
        outbound_message_id: null,
        sent_at: null,
        created_at: '2026-09-25T09:00:00Z',
      },
    ],
  };

  const dummyResponses: RfqResponseComparisonList = {
    items: [
      {
        id: 'resp-1',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-1',
        quotation_id: 'quote-1',
        quotation_status: 'reviewed',
        submitted_at: '2026-09-25T10:00:00Z',
        lines: [
          {
            workspace_product_id: 'prod-1',
            original_text: 'Supplier Product 1 text',
            quoted_quantity: '10',
            quoted_unit_price_amount: '5.00',
            quoted_unit_price_currency: 'USD',
            pending_match: false,
          },
        ],
        guardrail_evaluations: [{ guardrail_id: 'g-1', fired: false, reason: 'price_variance_exceeded' }],
      },
      {
        id: 'resp-2',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-2',
        quotation_id: 'quote-2',
        quotation_status: 'reviewed',
        submitted_at: '2026-09-25T11:00:00Z',
        lines: [
          {
            workspace_product_id: null,
            original_text: 'Unmatched Special Spices 500g',
            quoted_quantity: '10',
            quoted_unit_price_amount: '4.50',
            quoted_unit_price_currency: 'USD',
            pending_match: true,
          },
        ],
      },
    ],
  };

  beforeEach(async () => {
    mockRfqApi = jasmine.createSpyObj('RfqApi', [
      'getRfq',
      'sendRfq',
      'listResponses',
      'prepareRequest',
      'splitRfq',
    ]);
    mockRfqApi.getRfq.and.returnValue(of(sentDetail));
    mockRfqApi.listResponses.and.returnValue(of(dummyResponses));
    mockRfqApi.prepareRequest.and.returnValue(
      of({ purchase_request_id: 'pr-1' } as PrepareRequestResponse),
    );
    mockRfqApi.listGuardrails = jasmine.createSpy('listGuardrails').and.returnValue(
      of([
        {
          id: 'g-1',
          tenant_id: 'tenant-1',
          created_by_membership_id: 'member-1',
          max_order_value_amount: '500.00',
          max_order_value_currency: 'GBP',
          supplier_allowlist: null,
          category_allowlist: null,
          min_response_count: 1,
          max_price_variance_pct: '0.10',
          enabled: true,
          default_branch_id: 'branch-1',
          created_at: '2026-09-25T09:00:00Z',
        },
      ]),
    );
    mockSession = jasmine.createSpyObj('SessionService', ['hasRole'], {
      isAuthenticated: signal(true),
      activeLocale: signal('en'),
      currentMember: signal<{ email: string } | null>({ email: 'owner@test.com' }),
      tenant: signal(null),
    });
    mockSession.hasRole.and.returnValue(true);

    mockApiService = jasmine.createSpyObj('ApiService', [
      'listBranches',
      'suppliers',
      'products',
      'members',
      'supplier',
      'product',
    ]);
    // Ids outside the first page of the lists are looked up one by one; by default they are unknown.
    mockApiService.supplier.and.returnValue(throwError(() => new Error('not found')));
    mockApiService.product.and.returnValue(throwError(() => new Error('not found')));
    mockApiService.members.and.returnValue(
      of({ items: [{ id: 'member-1', email: 'owner@test.com' }], next_cursor: null } as unknown as { items: Member[]; next_cursor: string | null }),
    );
    mockApiService.listBranches.and.returnValue(
      of({ items: [{ id: 'branch-1', name: 'Main Branch' }], next_cursor: null } as unknown as {
        items: Branch[];
        next_cursor: string | null;
      }),
    );
    mockApiService.suppliers.and.returnValue(
      of({ items: [{ id: 'supp-1', name: 'Supplier One' }], next_cursor: null } as unknown as {
        items: Supplier[];
        next_cursor: string | null;
      }),
    );
    mockApiService.products.and.returnValue(
      of({ items: [{ id: 'prod-1', tenant_name: 'Product One' }], next_cursor: null } as unknown as {
        items: Product[];
        next_cursor: string | null;
      }),
    );
    mockRouter = jasmine.createSpyObj('Router', ['navigate', 'createUrlTree', 'serializeUrl']);
    mockRouter.createUrlTree.and.callFake((commands: unknown[], navigationExtras?: { queryParams?: Record<string, string> }) => {
      return { commands, navigationExtras } as unknown as ReturnType<Router['createUrlTree']>;
    });
    mockRouter.serializeUrl.and.callFake((urlTree: UrlTree) => {
      const treeRecord = urlTree as unknown as { commands?: string[]; navigationExtras?: { queryParams?: Record<string, string> } };
      const qp = treeRecord.navigationExtras?.queryParams;
      const qStr = qp ? '?' + new URLSearchParams(qp).toString() : '';
      const path = (treeRecord.commands || []).join('/');
      return (path.startsWith('/') ? path : '/' + path) + qStr;
    });
    mockSnackBar = jasmine.createSpyObj('MatSnackBar', ['open']);
    mockSnackBar.open.and.returnValue({
      onAction: () => of(undefined),
    } as unknown as ReturnType<MatSnackBar['open']>);
    mockDialog = jasmine.createSpyObj('MatDialog', ['open']);

    await TestBed.configureTestingModule({
      imports: [CompareComponent],
      providers: [
        provideTranslateService(),
        { provide: RfqApi, useValue: mockRfqApi },
        { provide: ApiService, useValue: mockApiService },
        { provide: Router, useValue: mockRouter },
        { provide: MatSnackBar, useValue: mockSnackBar },
        { provide: MatDialog, useValue: mockDialog },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of({ get: () => 'rfq-1' }),
          },
        },
        provideNoopAnimations(),
      ],
    })
      .overrideProvider(MatSnackBar, { useValue: mockSnackBar })
      .overrideProvider(MatDialog, { useValue: mockDialog })
      .compileComponents();

    fixture = TestBed.createComponent(CompareComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load responses, prefill requiredByDate from needed_by_date, and preselect sole branch on init', () => {
    expect(mockRfqApi.getRfq).toHaveBeenCalledWith('rfq-1');
    expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-1');
    expect(mockRfqApi.listGuardrails).toHaveBeenCalled();
    expect(mockApiService.listBranches).toHaveBeenCalled();
    expect(mockApiService.suppliers).toHaveBeenCalled();
    expect(mockApiService.products).toHaveBeenCalled();

    expect(component.responses().length).toBe(2);
    expect(component.selectedBranchId()).toBe('branch-1');
    const reqDate = component.requiredByDate();
    expect(reqDate).toBeTruthy();
    expect(reqDate?.getFullYear()).toBe(2026);
    expect(reqDate?.getMonth()).toBe(9);
    expect(reqDate?.getDate()).toBe(20);
    expect(component.supplierNames()['supp-1']).toBe('Supplier One');
    expect(component.productNames()['prod-1']).toBe('Product One');
  });

  it('keeps a refused response visible with an explanation and no prepare action', () => {
    const response = Object.assign({}, dummyResponses.items[0], { quotation_status: 'refused' as const, lines: [] });
    component.responses.set([response]);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.response-card')).not.toBeNull();
    expect(element.textContent).toContain('rfq.compare.refused');
    expect(element.textContent).toContain('rfq.compare.refusedExplanation');
    expect(element.querySelector('mat-card-actions button')).toBeNull();
    expect(component.canPrepare(response)).toBeFalse();
    component.prepareRequest(response);
    expect(mockRfqApi.prepareRequest).not.toHaveBeenCalled();
  });

  it('provides English and Arabic refused response copy', () => {
    for (const catalog of [enCatalog, arCatalog]) {
      const compare = catalog.rfq.compare as Record<string, string>;
      expect(compare['refused']).toBeTruthy();
      expect(compare['refusedExplanation']).toBeTruthy();
    }
  });

  it('renders quoted quantities without trailing decimal zeroes in the comparison table', () => {
    const response = dummyResponses.items[0];
    mockRfqApi.listResponses.and.returnValue(of({
      items: [{ ...response, lines: [{ ...response.lines[0], quoted_quantity: '50.000000' }] }],
    }));

    component.loadData('rfq-1');
    fixture.detectChanges();

    const quantityCell = (fixture.nativeElement as HTMLElement).querySelector('td.mat-column-quantity');
    const text = quantityCell?.textContent?.trim();
    expect(text).toBe('50');
    expect(text).not.toContain('50.000000');
  });

  it('should not preselect branch when multiple branches exist and none saved in localStorage, and should remember choice per tenant', () => {
    try {
      localStorage.removeItem('pp.rfq.lastBranchId.tenant-1');
    } catch {
      // ignore
    }
    mockApiService.listBranches.and.returnValue(
      of({
        items: [
          { id: 'branch-1', name: 'Main Branch' },
          { id: 'branch-2', name: 'Second Branch' },
        ],
        next_cursor: null,
      } as unknown as { items: Branch[]; next_cursor: string | null }),
    );

    component.loadBranches();
    expect(component.selectedBranchId()).toBe('');
    expect(component.canPrepare(dummyResponses.items[0])).toBeFalse();

    component.onBranchChange('branch-2');
    expect(component.selectedBranchId()).toBe('branch-2');

    // Reloading branches for same tenant restores saved branch-2
    component.selectedBranchId.set('');
    component.loadBranches();
    expect(component.selectedBranchId()).toBe('branch-2');

    try {
      localStorage.removeItem('pp.rfq.lastBranchId.tenant-1');
    } catch {
      // ignore
    }
  });

  describe('creator membership id (buyers cannot call the members API)', () => {
    function createWithSession(sessionMember: { email: string; membership_id?: string } | null): CompareComponent {
      (mockSession.currentMember as unknown as WritableSignal<object | null>).set(sessionMember);
      mockApiService.members.calls.reset();
      const created = TestBed.createComponent(CompareComponent);
      created.detectChanges();
      return created.componentInstance;
    }

    it('reads the membership id from the session and does not call members()', () => {
      const compare = createWithSession({ email: 'buyer@test.com', membership_id: 'm-buyer' });
      expect(compare.currentMembershipId()).toBe('m-buyer');
      expect(mockApiService.members).not.toHaveBeenCalled();
    });

    it('stays without an id, and without an unhandled error, when members() is forbidden', () => {
      mockApiService.members.and.returnValue(throwError(() => new HttpErrorResponse({ status: 403 })));
      const compare = createWithSession({ email: 'buyer@test.com' });
      expect(mockApiService.members).toHaveBeenCalledTimes(1);
      expect(compare.currentMembershipId()).toBeNull();
    });
  });

  it('shows draft notice card only when RFQ status is draft', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="rfq-compare-draft-notice"]')).toBeNull();

    mockRfqApi.getRfq.and.returnValue(of(draftDetail));
    component.loadData('rfq-1');
    fixture.detectChanges();

    const draftNotice = compiled.querySelector('[data-testid="rfq-compare-draft-notice"]');
    expect(draftNotice).not.toBeNull();

    const editBtn = compiled.querySelector<HTMLButtonElement>(
      '[data-testid="rfq-compare-edit-button"]',
    );
    editBtn?.click();
    expect(mockRouter.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-1', 'edit']);

    mockDialog.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
    mockRfqApi.sendRfq.and.returnValue(
      of({ rfq: sentDetail.rfq, recipients: draftDetail.recipients } as RfqSendResponse),
    );
    mockRfqApi.getRfq.and.returnValue(of(sentDetail));

    const sendBtn = compiled.querySelector<HTMLButtonElement>(
      '[data-testid="rfq-compare-send-button"]',
    );
    sendBtn?.click();
    expect(mockRfqApi.sendRfq).toHaveBeenCalledWith('rfq-1', jasmine.any(String));
    expect(mockSnackBar.open).toHaveBeenCalled();
  });

  it('reuses the draft send key after 503, clears it on success, and blocks concurrent sends', () => {
    component.rfqDetail.set(draftDetail);
    component.currentMembershipId.set(draftDetail.rfq.created_by_membership_id);
    mockDialog.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
    mockRfqApi.sendRfq.and.returnValue(throwError(() => new HttpErrorResponse({ status: 503 })));

    component.onSendDraft();
    const firstKey = mockRfqApi.sendRfq.calls.mostRecent().args[1];
    expect(firstKey).toEqual(jasmine.any(String));

    const pending = new Subject<RfqSendResponse>();
    mockRfqApi.sendRfq.and.returnValue(pending);
    component.onSendDraft();
    expect(mockRfqApi.sendRfq.calls.mostRecent().args[1]).toBe(firstKey);
    component.onSendDraft();
    expect(mockRfqApi.sendRfq).toHaveBeenCalledTimes(2);
    expect(mockDialog.open).toHaveBeenCalledTimes(2);

    pending.next({ rfq: sentDetail.rfq, recipients: draftDetail.recipients });
    component.onSendDraft();
    expect(mockRfqApi.sendRfq).toHaveBeenCalledTimes(3);
    expect(mockRfqApi.sendRfq.calls.mostRecent().args[1]).toEqual(jasmine.any(String));
    expect(mockRfqApi.sendRfq.calls.mostRecent().args[1]).not.toBe(firstKey);
    pending.complete();
  });

  it('shows draft actions only to the RFQ creator', async () => {
    mockRfqApi.getRfq.and.returnValue(of(draftDetail));
    component.loadData('rfq-1');
    await fixture.whenStable();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-compare-send-button"]')).not.toBeNull();
    component.currentMembershipId.set('another-member');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-compare-send-button"]')).toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="rfq-compare-edit-button"]')).toBeNull();
  });

  it('opens send confirmation dialog with count and formatted needed-by date in messageParams', async () => {
    mockDialog.open.and.returnValue({
      afterClosed: () => of(false),
    } as MatDialogRef<CatalogueConfirmDialogComponent, boolean>);

    mockRfqApi.getRfq.and.returnValue(of(draftDetail));
    component.loadData('rfq-1');
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const sendBtn = compiled.querySelector<HTMLButtonElement>(
      '[data-testid="rfq-compare-send-button"]',
    );
    sendBtn?.click();

    const formatService = TestBed.inject(FormatService);
    const expectedDate = formatService.formatDate(draftDetail.rfq.needed_by_date);

    expect(mockDialog.open).toHaveBeenCalledWith(
      CatalogueConfirmDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          messageParams: jasmine.objectContaining({
            count: draftDetail.recipients.length,
            date: expectedDate,
          }),
        }),
      }),
    );
  });

  it('should disable prepare action for responses with pending match lines', () => {
    expect(component.isEligible(dummyResponses.items[0])).toBeTrue();
    expect(component.isEligible(dummyResponses.items[1])).toBeFalse();
  });

  it('renders a non-fired guardrail reason', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('rfq.guardrails.reasons.price_variance_exceeded');
  });

  it('labels a known guardrail by its limit', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');
    expect(component.guardrailLabel('g-1')).toBe('Up to GBP 500');
    expect(component.guardrails()[0].max_order_value_amount).toBe('500.00');
  });

  it('does not load guardrails for buyers', () => {
    mockRfqApi.listGuardrails.calls.reset();
    mockSession.hasRole.and.returnValue(false);
    component.loadData('rfq-1');
    expect(mockRfqApi.listGuardrails).not.toHaveBeenCalled();
  });

  it('should show error snackbar when preparing an ineligible response', () => {
    component.prepareRequest(dummyResponses.items[1]);
    expect(mockSnackBar.open).toHaveBeenCalledWith(
      'rfq.compare.cannotPreparePending',
      'rfq.history.dismiss',
      { duration: 3000 },
    );
    expect(mockRfqApi.prepareRequest).not.toHaveBeenCalled();
  });

  it('should call prepareRequest API, show Open draft snackbar, and navigate to /requests/<id>', () => {
    component.prepareRequest(dummyResponses.items[0]);

    expect(mockRfqApi.prepareRequest).toHaveBeenCalledWith('rfq-1', {
      rfq_response_id: 'resp-1',
      branch_id: 'branch-1',
      required_by_date: '2026-10-20',
    }, jasmine.any(String));

    expect(mockSnackBar.open).toHaveBeenCalledWith(
      'rfq.compare.prepareSuccess',
      'rfq.compare.openDraft',
      { duration: 5000 },
    );
    expect(mockRouter.navigate).toHaveBeenCalledWith(['/requests', 'pr-1']);
  });

  it('formats 6-decimal precision quantities in compare cells', () => {
    expect(component.formatQuantity('0.000001')).toBe('0.000001');
    expect(component.formatQuantity('1.234567')).toBe('1.234567');
    expect(component.formatQuantity('50.000000')).toBe('50');
  });

  it('renders breadcrumb on standalone compare page', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const breadcrumb = compiled.querySelector('nav.breadcrumb');
    expect(breadcrumb).not.toBeNull();
    expect(breadcrumb?.getAttribute('aria-label')).toBe(TestBed.inject(TranslateService).instant('common.breadcrumbLabel'));
    const link = breadcrumb?.querySelector('a.breadcrumb-link');
    expect(link?.getAttribute('routerLink') ?? link?.getAttribute('href')).toBe('/rfq/history');
  });

  it('supports embedded input mode: loads data from rfqId input and hides header/breadcrumb', async () => {
    mockRfqApi.getRfq.calls.reset();
    mockRfqApi.listResponses.calls.reset();

    fixture.componentRef.setInput('embedded', true);
    fixture.componentRef.setInput('rfqId', 'rfq-embedded-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(mockRfqApi.getRfq).toHaveBeenCalledWith('rfq-embedded-1');
    expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-embedded-1');

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('nav.breadcrumb')).toBeNull();
    expect(compiled.querySelector('.page-header')).toBeNull();
  });

  it('loads data exactly once when embedded with rfqId input bound (embedded mode)', () => {
    mockRfqApi.getRfq.calls.reset();
    mockRfqApi.listResponses.calls.reset();

    const embeddedFixture = TestBed.createComponent(CompareComponent);
    embeddedFixture.componentRef.setInput('embedded', true);
    embeddedFixture.componentRef.setInput('rfqId', 'rfq-embedded-1');
    embeddedFixture.detectChanges();

    expect(mockRfqApi.getRfq).toHaveBeenCalledTimes(1);
    expect(mockRfqApi.getRfq).toHaveBeenCalledWith('rfq-embedded-1');
    expect(mockRfqApi.listResponses).toHaveBeenCalledTimes(1);
    expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-embedded-1');
  });

  it('loads data exactly once in standalone route mode without rfqId input', () => {
    expect(mockRfqApi.getRfq).toHaveBeenCalledTimes(1);
    expect(mockRfqApi.getRfq).toHaveBeenCalledWith('rfq-1');
    expect(mockRfqApi.listResponses).toHaveBeenCalledTimes(1);
    expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-1');
  });

  it('renders unmatched line with pending match badge and supplier original_text', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const cards = compiled.querySelectorAll('.response-card');
    const resp2Card = cards[1];
    const productCell = resp2Card.querySelector('td.mat-column-product');
    expect(productCell).not.toBeNull();
    expect(productCell?.textContent).toContain('Pending Match');
    expect(productCell?.textContent).toContain('Unmatched Special Spices 500g');
    const originalTextSpan = productCell?.querySelector('[dir="auto"]');
    expect(originalTextSpan).not.toBeNull();
    expect(originalTextSpan?.textContent?.trim()).toBe('Unmatched Special Spices 500g');
  });

  it('renders total row per supplier card with formatted total in figures style', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const totalRows = compiled.querySelectorAll('tr.total-row');
    expect(totalRows.length).toBe(2);

    const totalCells = compiled.querySelectorAll('td.total-value-cell');
    expect(totalCells.length).toBe(2);
    // resp-1: 10 * 5.00 = USD 50
    expect(totalCells[0].textContent).toContain('USD 50');
    expect(totalCells[0].classList.contains('pp-figures')).toBeTrue();
  });

  it('renders Lowest total chip when at least two non-refused responses are fully matched and share a currency', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    const resp3 = {
      id: 'resp-3',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-3',
      quotation_id: 'quote-3',
      quotation_status: 'reviewed' as const,
      submitted_at: '2026-09-25T12:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Supplier Product 1 text',
          quoted_quantity: '10',
          quoted_unit_price_amount: '3.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };
    // resp-1 total is 50 USD, resp-3 total is 30 USD, resp-2 has unmatched lines
    component.responses.set([dummyResponses.items[0], dummyResponses.items[1], resp3]);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const chips = compiled.querySelectorAll('.pp-chip-best');
    expect(chips.length).toBe(1);
    expect(chips[0].textContent?.trim()).toBe('Lowest total');

    // resp-3 card has the chip, resp-1 does not
    const cards = compiled.querySelectorAll('.response-card');
    expect(cards[0].querySelector('.pp-chip-best')).toBeNull();
    expect(cards[2].querySelector('.pp-chip-best')).not.toBeNull();
  });

  it('does NOT render Lowest total chip on refused response or when currencies are mixed', () => {
    const respRefused = {
      ...dummyResponses.items[0],
      id: 'resp-refused',
      quotation_status: 'refused' as const,
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Cheap but refused',
          quoted_quantity: '10',
          quoted_unit_price_amount: '1.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };
    const respMatched = {
      ...dummyResponses.items[0],
      id: 'resp-matched',
      quotation_status: 'reviewed' as const,
    };
    // Only one non-refused fully matched response
    component.responses.set([respRefused, respMatched]);
    fixture.detectChanges();

    let compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pp-chip-best')).toBeNull();

    // Mixed currencies: USD and SAR
    const respSar = {
      ...dummyResponses.items[0],
      id: 'resp-sar',
      quotation_status: 'reviewed' as const,
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'SAR Product',
          quoted_quantity: '10',
          quoted_unit_price_amount: '10.00',
          quoted_unit_price_currency: 'SAR',
          pending_match: false,
        },
      ],
    };
    component.responses.set([respMatched, respSar]);
    fixture.detectChanges();
    compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pp-chip-best')).toBeNull();
  });

  it('does NOT render Lowest total chip when responses cover different sets of products (e.g. four-product vs one-product)', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    const fourProductResp: RfqResponseComparison = {
      id: 'resp-four-prod',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-1',
      quotation_id: 'quote-4p',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T10:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '100.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '10',
          quoted_unit_price_amount: '100.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-3',
          original_text: 'Product 3',
          quoted_quantity: '10',
          quoted_unit_price_amount: '100.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-4',
          original_text: 'Product 4',
          quoted_quantity: '10',
          quoted_unit_price_amount: '100.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    const oneProductResp: RfqResponseComparison = {
      id: 'resp-one-prod',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-2',
      quotation_id: 'quote-1p',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T11:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1 only',
          quoted_quantity: '10',
          quoted_unit_price_amount: '90.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    component.responses.set([fourProductResp, oneProductResp]);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pp-chip-best')).toBeNull();
    expect(component.lowestTotalResponseIds().size).toBe(0);
  });

  it('does NOT render Lowest total chip when responses cover same products but differ in quantity on any product', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    const respA: RfqResponseComparison = {
      id: 'resp-a',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-1',
      quotation_id: 'quote-a',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T10:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '20',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    const respB: RfqResponseComparison = {
      id: 'resp-b',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-2',
      quotation_id: 'quote-b',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T11:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '15',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    component.responses.set([respA, respB]);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pp-chip-best')).toBeNull();
    expect(component.lowestTotalResponseIds().size).toBe(0);
  });

  it('renders Lowest total chip on cheapest response (and both on tie) when products and quantities match', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    const respHigher: RfqResponseComparison = {
      id: 'resp-higher',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-1',
      quotation_id: 'quote-h',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T10:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '20',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    const respCheapest1: RfqResponseComparison = {
      id: 'resp-cheap-1',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-2',
      quotation_id: 'quote-c1',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T11:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '4.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '20',
          quoted_unit_price_amount: '4.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    const respCheapest2: RfqResponseComparison = {
      id: 'resp-cheap-2',
      rfq_id: 'rfq-1',
      supplier_id: 'supp-3',
      quotation_id: 'quote-c2',
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T12:00:00Z',
      lines: [
        {
          workspace_product_id: 'prod-1',
          original_text: 'Product 1',
          quoted_quantity: '10',
          quoted_unit_price_amount: '4.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
        {
          workspace_product_id: 'prod-2',
          original_text: 'Product 2',
          quoted_quantity: '20',
          quoted_unit_price_amount: '4.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    };

    // Subcase 1: single cheapest
    component.responses.set([respHigher, respCheapest1]);
    fixture.detectChanges();

    let compiled = fixture.nativeElement as HTMLElement;
    let chips = compiled.querySelectorAll('.pp-chip-best');
    expect(chips.length).toBe(1);
    expect(component.lowestTotalResponseIds()).toEqual(new Set(['resp-cheap-1']));
    let cards = compiled.querySelectorAll('.response-card');
    expect(cards[0].querySelector('.pp-chip-best')).toBeNull();
    expect(cards[1].querySelector('.pp-chip-best')).not.toBeNull();

    // Subcase 2: tie for cheapest -> both get the chip
    component.responses.set([respHigher, respCheapest1, respCheapest2]);
    fixture.detectChanges();

    compiled = fixture.nativeElement as HTMLElement;
    chips = compiled.querySelectorAll('.pp-chip-best');
    expect(chips.length).toBe(2);
    expect(component.lowestTotalResponseIds()).toEqual(new Set(['resp-cheap-1', 'resp-cheap-2']));
    cards = compiled.querySelectorAll('.response-card');
    expect(cards[0].querySelector('.pp-chip-best')).toBeNull();
    expect(cards[1].querySelector('.pp-chip-best')).not.toBeNull();
    expect(cards[2].querySelector('.pp-chip-best')).not.toBeNull();
  });

  it('renders Match N lines link with href carrying quotation_id when lines are unmatched', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const cards = compiled.querySelectorAll('.response-card');
    const resp2Card = cards[1];
    const matchLink = resp2Card.querySelector<HTMLAnchorElement>('a.match-lines-link');
    expect(matchLink).not.toBeNull();
    expect(matchLink?.textContent?.trim()).toBe('Match 1 line');
    expect(matchLink?.getAttribute('href')).toContain('quotation_id=quote-2');
  });

  it('shows short reason under prepare button when no delivery branch is chosen', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.use('en');

    component.selectedBranchId.set('');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const cards = compiled.querySelectorAll('.response-card');
    // resp-1 is eligible but branch is empty -> shows short reason
    const resp1Actions = cards[0].querySelector('.prepare-actions');
    expect(resp1Actions?.textContent).toContain('Choose a delivery branch first');

    // resp-2 has unmatched lines -> disabled, but no branch reason under button (the link above is the reason)
    const resp2Actions = cards[1].querySelector('.prepare-actions');
    expect(resp2Actions?.textContent).not.toContain('Choose a delivery branch first');
  });

  it('renders non-fired guardrail reason in muted style and fired reason in red', () => {
    const respWithEvaluations = {
      ...dummyResponses.items[0],
      guardrail_evaluations: [
        { guardrail_id: 'g-1', fired: false, reason: 'price_variance_exceeded' },
        { guardrail_id: 'g-1', fired: true, reason: 'min_responses_unmet' },
      ],
    };
    component.responses.set([respWithEvaluations]);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const reasons = compiled.querySelectorAll('.outcome-reason');
    expect(reasons.length).toBe(2);
    expect(reasons[0].classList.contains('fired')).toBeFalse();
    expect(reasons[1].classList.contains('fired')).toBeTrue();
  });

  describe('Split between suppliers (T015)', () => {
    it('disables split button with "Needs two matched replies" and "Match 1 line" link when only 1 reply is matched', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const splitBtns = compiled.querySelectorAll<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtns.length).toBe(1);
      const splitBtn = splitBtns[0];
      expect(splitBtn).not.toBeNull();
      expect(splitBtn?.disabled).toBeTrue();

      const reasons = compiled.querySelectorAll('[data-testid="split-disabled-reason"]');
      expect(reasons.length).toBe(1);
      const reason = reasons[0];
      expect(reason?.textContent).toContain('Needs two matched replies');
      const matchLink = reason?.querySelector<HTMLAnchorElement>('a.match-lines-link');
      expect(matchLink).not.toBeNull();
      expect(matchLink?.textContent?.trim()).toBe('Match 1 line');
      expect(matchLink?.getAttribute('href')).toContain('quotation_id=quote-2');
    });

    it('disables split button with "Replies are in different currencies" when currencies differ', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const respUsd = dummyResponses.items[0];
      const respSar = {
        ...dummyResponses.items[0],
        id: 'resp-sar',
        supplier_id: 'supp-sar',
        quotation_id: 'quote-sar',
        lines: [
          {
            ...dummyResponses.items[0].lines[0],
            quoted_unit_price_currency: 'SAR',
          },
        ],
      };
      component.responses.set([respUsd, respSar]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtn?.disabled).toBeTrue();

      const reason = compiled.querySelector('[data-testid="split-disabled-reason"]');
      expect(reason?.textContent).toContain('Replies are in different currencies');
    });

    it('enables split button when at least 2 replies are reviewed, fully matched, and in same currency', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const resp1 = dummyResponses.items[0];
      const resp2 = {
        ...dummyResponses.items[0],
        id: 'resp-usd-2',
        supplier_id: 'supp-2',
        quotation_id: 'quote-2',
      };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const splitBtns = compiled.querySelectorAll<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtns.length).toBe(1);
      const splitBtn = splitBtns[0];
      expect(splitBtn?.disabled).toBeFalse();
      expect(compiled.querySelector('[data-testid="split-disabled-reason"]')).toBeNull();
    });

    it('hides the split button when RFQ is converted', () => {
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'converted' },
      });
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="rfq-compare-split-button"]')).toBeNull();
    });

    it('calls splitRfq API on click and navigates to /offers/basket-split/:jobId', () => {
      const resp1 = dummyResponses.items[0];
      const resp2 = {
        ...dummyResponses.items[0],
        id: 'resp-usd-2',
        supplier_id: 'supp-2',
        quotation_id: 'quote-2',
      };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      mockRfqApi.splitRfq.and.returnValue(
        of({ id: 'job-999', rfq_id: 'rfq-1' } as unknown as BasketSplitJob),
      );

      const splitBtn = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
        '[data-testid="rfq-compare-split-button"]',
      );
      splitBtn?.click();

      expect(mockRfqApi.splitRfq).toHaveBeenCalledWith('rfq-1', jasmine.any(String));
      expect(mockRouter.navigate).toHaveBeenCalledWith(['/offers/basket-split', 'job-999']);
    });

    it('disables split button while request is in flight', () => {
      const resp1 = dummyResponses.items[0];
      const resp2 = { ...dummyResponses.items[0], id: 'resp-usd-2', supplier_id: 'supp-2', quotation_id: 'quote-2' };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      component.isSplitting.set(true);
      fixture.detectChanges();

      const splitBtn = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
        '[data-testid="rfq-compare-split-button"]',
      );
      expect(splitBtn?.disabled).toBeTrue();
      expect((fixture.nativeElement as HTMLElement).querySelector('.btn-spinner')).not.toBeNull();
    });

    it('maps 409 conflict reasons to specific messages and reuses idempotency key on retry', () => {
      const resp1 = dummyResponses.items[0];
      const resp2 = { ...dummyResponses.items[0], id: 'resp-usd-2', supplier_id: 'supp-2', quotation_id: 'quote-2' };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      // Test rfq_already_converted
      mockRfqApi.splitRfq.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 409, error: { details: { reason: 'rfq_already_converted' } } })),
      );
      component.splitRfq();
      expect(mockSnackBar.open).toHaveBeenCalledWith('rfq.compare.alreadyConverted', 'rfq.history.dismiss', { duration: 5000 });
      const firstKey = mockRfqApi.splitRfq.calls.mostRecent().args[1];

      // Test mixed_currency
      mockRfqApi.splitRfq.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 409, error: { details: { reason: 'mixed_currency' } } })),
      );
      component.splitRfq();
      expect(mockSnackBar.open).toHaveBeenCalledWith('rfq.compare.differentCurrencies', 'rfq.history.dismiss', { duration: 5000 });
      const secondKey = mockRfqApi.splitRfq.calls.mostRecent().args[1];
      // Key should be reused across retries of the same click attempt
      expect(secondKey).toBe(firstKey);

      // Test not_enough_replies
      mockRfqApi.splitRfq.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 409, error: { details: { reason: 'not_enough_replies' } } })),
      );
      component.splitRfq();
      expect(mockSnackBar.open).toHaveBeenCalledWith('rfq.compare.needsTwoMatched', 'rfq.history.dismiss', { duration: 5000 });
    });

    it('has English and Arabic translation keys for split reasons and button', () => {
      for (const catalog of [enCatalog, arCatalog]) {
        const compare = catalog.rfq.compare as Record<string, string>;
        expect(compare['splitBetweenSuppliers']).toBeTruthy();
        expect(compare['needsTwoMatched']).toBeTruthy();
        expect(compare['differentCurrencies']).toBeTruthy();
        expect(compare['replyMixedCurrency']).toBeTruthy();
        expect(compare['alreadyConverted']).toBeTruthy();
        expect(compare['splitError']).toBeTruthy();
      }
    });

    it('mixed-currency reply next to a single-currency reply never gets the lowest-total badge and disables split with the translated reason', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const respMixed: RfqResponseComparison = {
        id: 'resp-mixed',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-mixed',
        quotation_id: 'quote-mixed',
        quotation_status: 'reviewed',
        submitted_at: '2026-09-25T10:00:00Z',
        lines: [
          {
            workspace_product_id: 'prod-1',
            original_text: 'Product 1',
            quoted_quantity: '10',
            quoted_unit_price_amount: '5.00',
            quoted_unit_price_currency: 'USD',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-2',
            original_text: 'Product 2',
            quoted_quantity: '20',
            quoted_unit_price_amount: '10.00',
            quoted_unit_price_currency: 'EUR',
            pending_match: false,
          },
        ],
        guardrail_evaluations: [],
      };

      const respSingle: RfqResponseComparison = {
        id: 'resp-single',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-single',
        quotation_id: 'quote-single',
        quotation_status: 'reviewed',
        submitted_at: '2026-09-25T11:00:00Z',
        lines: [
          {
            workspace_product_id: 'prod-1',
            original_text: 'Product 1',
            quoted_quantity: '10',
            quoted_unit_price_amount: '20.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-2',
            original_text: 'Product 2',
            quoted_quantity: '20',
            quoted_unit_price_amount: '40.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
        ],
        guardrail_evaluations: [],
      };

      component.responses.set([respMixed, respSingle]);
      fixture.detectChanges();

      expect(component.hasLowestTotal(respMixed)).toBeFalse();
      expect(component.lowestTotalResponseIds().has(respMixed.id)).toBeFalse();
      const compiled = fixture.nativeElement as HTMLElement;
      const bestChips = compiled.querySelectorAll('.pp-chip-best');
      for (const chip of Array.from(bestChips)) {
        const card = chip.closest('.response-card');
        expect(card?.textContent).not.toContain('supp-mixed');
      }

      expect(component.splitEligibility().canSplit).toBeFalse();
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtn?.disabled).toBeTrue();

      const reason = compiled.querySelector('[data-testid="split-disabled-reason"]');
      expect(reason?.textContent).toContain(
        translate.instant('rfq.compare.replyMixedCurrency'),
      );
    });
  });

  describe('PPS-123 & PPS-124: RFQ line minima, split hint, and converted state', () => {
    const createD8f7fb0cFixtures = () => {
      const rfqLines = [
        {
          id: 'line-flour',
          tenant_id: 'tenant-1',
          rfq_id: 'rfq-1',
          workspace_product_id: 'prod-flour',
          quantity: '10',
          created_at: '2026-09-25T09:00:00Z',
        },
        {
          id: 'line-oil',
          tenant_id: 'tenant-1',
          rfq_id: 'rfq-1',
          workspace_product_id: 'prod-oil',
          quantity: '10',
          created_at: '2026-09-25T09:00:00Z',
        },
        {
          id: 'line-sugar',
          tenant_id: 'tenant-1',
          rfq_id: 'rfq-1',
          workspace_product_id: 'prod-sugar',
          quantity: '10',
          created_at: '2026-09-25T09:00:00Z',
        },
        {
          id: 'line-rice',
          tenant_id: 'tenant-1',
          rfq_id: 'rfq-1',
          workspace_product_id: 'prod-rice',
          quantity: '10',
          created_at: '2026-09-25T09:00:00Z',
        },
      ];

      const respDahabi: RfqResponseComparison = {
        id: 'resp-dahabi',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-dahabi',
        quotation_id: 'quote-dahabi',
        quotation_status: 'reviewed',
        submitted_at: '2026-10-25T10:00:00Z',
        lines: [
          {
            workspace_product_id: 'prod-oil',
            original_text: 'Oil 10L',
            quoted_quantity: '10',
            quoted_unit_price_amount: '150.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-sugar',
            original_text: 'Sugar 50kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '38.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-rice',
            original_text: 'Rice 20kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '150.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-flour',
            original_text: 'Flour 25kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '145.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
        ],
        rfq_landed_costs: [
          { workspace_product_id: 'prod-flour', total_amount: '1230', total_currency: 'SAR' },
          { workspace_product_id: 'prod-oil', total_amount: '1500', total_currency: 'SAR' },
          { workspace_product_id: 'prod-sugar', total_amount: '380', total_currency: 'SAR' },
          { workspace_product_id: 'prod-rice', total_amount: '1720', total_currency: 'SAR' },
        ],
        guardrail_evaluations: [
          {
            guardrail_id: 'g-1',
            fired: true,
            reason: 'fired',
            purchase_request_id: '34049121-0000-0000-0000-000000000000',
          },
        ],
      };

      const respWafra: RfqResponseComparison = {
        id: 'resp-wafra',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-wafra',
        quotation_id: 'quote-wafra',
        quotation_status: 'reviewed',
        submitted_at: '2026-10-25T10:30:00Z',
        lines: [
          {
            workspace_product_id: 'prod-oil',
            original_text: 'Oil 10L',
            quoted_quantity: '10',
            quoted_unit_price_amount: '146.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-sugar',
            original_text: 'Sugar 50kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '36.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-rice',
            original_text: 'Rice 20kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '155.00',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-flour',
            original_text: 'Flour 25kg',
            quoted_quantity: '10',
            quoted_unit_price_amount: '148.50',
            quoted_unit_price_currency: 'SAR',
            pending_match: false,
          },
        ],
        rfq_landed_costs: [
          { workspace_product_id: 'prod-flour', total_amount: '1275', total_currency: 'SAR' },
          { workspace_product_id: 'prod-oil', total_amount: '1460', total_currency: 'SAR' },
          { workspace_product_id: 'prod-sugar', total_amount: '360', total_currency: 'SAR' },
          { workspace_product_id: 'prod-rice', total_amount: '1760', total_currency: 'SAR' },
        ],
        guardrail_evaluations: [
          {
            guardrail_id: 'g-1',
            fired: false,
            reason: 'not_lowest_price',
          },
        ],
      };

      return { respDahabi, respWafra, rfqLines };
    };

    const applyD8f7fb0cDetail = (rfqLines: RfqDetail['lines'], status: RfqDetail['rfq']['status'] = 'responded') => {
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status },
        lines: rfqLines,
      });
    };

    it('per-line minima: oil and sugar lines of الوفرة carry lowest-line-price, rice and flour of الذهبي do', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      expect(component.isLowestLinePrice(respWafra, respWafra.lines[0])).toBeTrue();
      expect(component.isLowestLinePrice(respWafra, respWafra.lines[1])).toBeTrue();
      expect(component.isLowestLinePrice(respWafra, respWafra.lines[2])).toBeFalse();
      expect(component.isLowestLinePrice(respWafra, respWafra.lines[3])).toBeFalse();

      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[0])).toBeFalse();
      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[1])).toBeFalse();
      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[2])).toBeTrue();
      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[3])).toBeTrue();

      const compiled = fixture.nativeElement as HTMLElement;
      const cards = compiled.querySelectorAll('.response-card');
      expect(cards.length).toBe(2);

      const dahabiRows = cards[0].querySelectorAll('tbody tr');
      expect(dahabiRows.length).toBe(4);
      expect(dahabiRows[0].querySelector('[data-testid="lowest-line-price"]')).toBeNull();
      expect(dahabiRows[1].querySelector('[data-testid="lowest-line-price"]')).toBeNull();
      expect(dahabiRows[2].querySelector('[data-testid="lowest-line-price"]')).not.toBeNull();
      expect(dahabiRows[3].querySelector('[data-testid="lowest-line-price"]')).not.toBeNull();
      expect(dahabiRows[2].classList.contains('best')).toBeTrue();
      expect(dahabiRows[3].classList.contains('best')).toBeTrue();

      const wafraRows = cards[1].querySelectorAll('tbody tr');
      expect(wafraRows.length).toBe(4);
      expect(wafraRows[0].querySelector('[data-testid="lowest-line-price"]')).not.toBeNull();
      expect(wafraRows[1].querySelector('[data-testid="lowest-line-price"]')).not.toBeNull();
      expect(wafraRows[2].querySelector('[data-testid="lowest-line-price"]')).toBeNull();
      expect(wafraRows[3].querySelector('[data-testid="lowest-line-price"]')).toBeNull();
      expect(wafraRows[0].classList.contains('best')).toBeTrue();
      expect(wafraRows[1].classList.contains('best')).toBeTrue();
    });

    it('per-line minima: a product with the same landed cost by both is marked on neither', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Make rice identical landed cost on both
      respWafra.rfq_landed_costs = respWafra.rfq_landed_costs!.map((c) =>
        c.workspace_product_id === 'prod-rice' ? { ...c, total_amount: '1720' } : c,
      );
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[2])).toBeFalse();
      expect(component.isLowestLinePrice(respWafra, respWafra.lines[2])).toBeFalse();

      const compiled = fixture.nativeElement as HTMLElement;
      const cards = compiled.querySelectorAll('.response-card');
      const dahabiRiceRow = cards[0].querySelectorAll('tbody tr')[2];
      const wafraRiceRow = cards[1].querySelectorAll('tbody tr')[2];
      expect(dahabiRiceRow.querySelector('[data-testid="lowest-line-price"]')).toBeNull();
      expect(wafraRiceRow.querySelector('[data-testid="lowest-line-price"]')).toBeNull();
    });

    it('per-line minima: quoted quantity differences do not block marks; a pending line still does', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Different quoted quantities — marks still follow landed costs
      const wafraDiffQty = {
        ...respWafra,
        lines: [
          ...respWafra.lines.slice(0, 3),
          { ...respWafra.lines[3], quoted_quantity: '20' },
        ],
      };
      component.responses.set([respDahabi, wafraDiffQty]);
      fixture.detectChanges();

      let compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(4);

      // Pending line — not eligible → no marks
      const wafraPending = {
        ...respWafra,
        lines: [
          ...respWafra.lines.slice(0, 3),
          { ...respWafra.lines[3], pending_match: true },
        ],
      };
      component.responses.set([respDahabi, wafraPending]);
      fixture.detectChanges();

      compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(0);
    });

    // Review: the saving is only a missed one when no split was taken and none is possible now.
    it('words the split saving by what the RFQ can still do', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines, 'responded');
      component.responses.set([respDahabi, respWafra]);
      const compiled = fixture.nativeElement as HTMLElement;
      const hintText = () => compiled.querySelector('[data-testid="split-saving-hint"]')?.textContent ?? null;
      const withStatus = (status: string, extra: object = {}) => {
        component.rfqDetail.set({
          ...sentDetail,
          rfq: { ...sentDetail.rfq, status } as RfqDetail['rfq'],
          lines: rfqLines,
          ...extra,
        });
        fixture.detectChanges();
      };

      withStatus('responded');
      expect(hintText()).toContain('could save');

      for (const status of ['cancelled', 'expired']) {
        withStatus(status);
        expect(hintText()).toContain('would have saved');
        expect(hintText()).not.toContain('could save');
      }

      withStatus('converted', { converted_purchase_request_ids: ['pr-single'] }); // one supplier took it all
      expect(hintText()).toContain('would have saved');

      // The split itself converted this RFQ: the saving was taken, so it is not shown as missed.
      withStatus('converted', { request_group_id: 'group-1', converted_purchase_request_ids: ['a', 'b'] });
      expect(hintText()).toBeNull();
    });

    it('split hint: shows SAR 60, sits right above the one Split action (splitRfq) on an open RFQ, keeps the text when converted, and has no bare route link', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines, 'responded');
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const hint = compiled.querySelector('[data-testid="split-saving-hint"]');
      expect(hint).not.toBeNull();
      expect(hint?.textContent).toContain('60');
      expect(hint?.textContent).toContain('could save'); // still open: an offer worth taking

      // (a) open RFQ, writer, eligible -> the hint has no Split button of its own; the RFQ's one Split
      // action follows it directly and calls rfqApi.splitRfq with the RFQ id
      mockRfqApi.splitRfq.calls.reset();
      mockRfqApi.splitRfq.and.returnValue(
        of({ id: 'job-split-hint', rfq_id: 'rfq-1' } as unknown as BasketSplitJob),
      );
      expect(hint?.querySelector('button')).toBeNull();
      const splitButtons = compiled.querySelectorAll<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitButtons.length).toBe(1);
      const actionBtn = splitButtons[0];
      expect(hint?.nextElementSibling?.contains(actionBtn)).toBeTrue();
      expect(actionBtn.disabled).toBeFalse();
      actionBtn.click();
      expect(mockRfqApi.splitRfq).toHaveBeenCalledWith('rfq-1', jasmine.any(String));

      // (b) converted RFQ -> the hint text with SAR 60 is shown and the action is absent
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'converted' },
        lines: rfqLines,
        converted_purchase_request_ids: ['pr-single-34049121'],
      });
      fixture.detectChanges();

      const convertedHint = compiled.querySelector('[data-testid="split-saving-hint"]');
      expect(convertedHint).not.toBeNull();
      expect(convertedHint?.textContent).toContain('60');
      // PPS-208: on a converted RFQ it is a record of what was left on the table, not an offer.
      expect(convertedHint?.textContent).toContain('would have saved');
      expect(convertedHint?.textContent).not.toContain('could save');
      expect(convertedHint?.querySelector('button')).toBeNull();
      expect(compiled.querySelector('[data-testid="rfq-compare-split-button"]')).toBeNull();

      // (c) no element in the hint has an href ending in /offers/basket-split
      const anyHintLinks = Array.from(convertedHint?.querySelectorAll<HTMLAnchorElement>('a') ?? []);
      for (const link of anyHintLinks) {
        expect(link.getAttribute('href') ?? '').not.toMatch(/\/offers\/basket-split$/);
      }
    });

    it('split hint: absent when per-line minimum equals the lowest total (one supplier cheapest everywhere)', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Make الذهبي cheaper on all landed costs
      const wafraExpensive = {
        ...respWafra,
        rfq_landed_costs: respWafra.rfq_landed_costs!.map((c) => ({
          ...c,
          total_amount: String(Number(c.total_amount) + 500),
        })),
      };
      component.responses.set([respDahabi, wafraExpensive]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
    });

    it('split hint: absent when not comparable', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Mixed landed-cost currencies
      const wafraUsd = {
        ...respWafra,
        rfq_landed_costs: respWafra.rfq_landed_costs!.map((c) => ({
          ...c,
          total_currency: 'USD',
        })),
      };
      component.responses.set([respDahabi, wafraUsd]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
    });

    it('landed costs: marks and hint follow RFQ landed costs even when quoted quantity differs', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Quoted qty differs from RFQ, but landed costs make الذهبي cheapest on all four → no hint, all marks on الذهبي
      const dahabiDiffQty = {
        ...respDahabi,
        lines: respDahabi.lines.map((l) => ({ ...l, quoted_quantity: '7' })),
        rfq_landed_costs: [
          { workspace_product_id: 'prod-flour', total_amount: '1000', total_currency: 'SAR' },
          { workspace_product_id: 'prod-oil', total_amount: '1000', total_currency: 'SAR' },
          { workspace_product_id: 'prod-sugar', total_amount: '1000', total_currency: 'SAR' },
          { workspace_product_id: 'prod-rice', total_amount: '1000', total_currency: 'SAR' },
        ],
      };
      const wafraDiffQty = {
        ...respWafra,
        lines: respWafra.lines.map((l) => ({ ...l, quoted_quantity: '12' })),
        rfq_landed_costs: [
          { workspace_product_id: 'prod-flour', total_amount: '1100', total_currency: 'SAR' },
          { workspace_product_id: 'prod-oil', total_amount: '1100', total_currency: 'SAR' },
          { workspace_product_id: 'prod-sugar', total_amount: '1100', total_currency: 'SAR' },
          { workspace_product_id: 'prod-rice', total_amount: '1100', total_currency: 'SAR' },
        ],
      };
      component.responses.set([dahabiDiffQty, wafraDiffQty]);
      fixture.detectChanges();

      expect(component.splitSaving()).toBeNull();
      expect(component.isLowestLinePrice(dahabiDiffQty, dahabiDiffQty.lines[0])).toBeTrue();
      expect(component.isLowestLinePrice(dahabiDiffQty, dahabiDiffQty.lines[1])).toBeTrue();
      expect(component.isLowestLinePrice(dahabiDiffQty, dahabiDiffQty.lines[2])).toBeTrue();
      expect(component.isLowestLinePrice(dahabiDiffQty, dahabiDiffQty.lines[3])).toBeTrue();
      expect(component.isLowestLinePrice(wafraDiffQty, wafraDiffQty.lines[0])).toBeFalse();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
      const cards = compiled.querySelectorAll('.response-card');
      expect(cards[0].querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(4);
      expect(cards[1].querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(0);
    });

    it('landed costs: a delivery charge that flips the cheapest supplier moves the mark', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      // Base: oil mark is on الوفرة (1460 < 1500). Delivery charge on wafra oil flips it.
      const wafraWithDelivery = {
        ...respWafra,
        rfq_landed_costs: respWafra.rfq_landed_costs!.map((c) =>
          c.workspace_product_id === 'prod-oil' ? { ...c, total_amount: '1550' } : c,
        ),
      };
      component.responses.set([respDahabi, wafraWithDelivery]);
      fixture.detectChanges();

      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[0])).toBeTrue();
      expect(component.isLowestLinePrice(wafraWithDelivery, wafraWithDelivery.lines[0])).toBeFalse();

      const compiled = fixture.nativeElement as HTMLElement;
      const cards = compiled.querySelectorAll('.response-card');
      expect(cards[0].querySelectorAll('tbody tr')[0].querySelector('[data-testid="lowest-line-price"]')).not.toBeNull();
      expect(cards[1].querySelectorAll('tbody tr')[0].querySelector('[data-testid="lowest-line-price"]')).toBeNull();
    });

    it('landed costs: missing a landed cost for one RFQ product → no marks, no hint', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      const wafraMissing = {
        ...respWafra,
        rfq_landed_costs: respWafra.rfq_landed_costs!.filter((c) => c.workspace_product_id !== 'prod-rice'),
      };
      component.responses.set([respDahabi, wafraMissing]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(0);
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
      expect(component.splitSaving()).toBeNull();
    });

    it('landed costs: supplier_terms_apply true keeps marks but hides the hint', () => {
      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      const wafraWithTerms = { ...respWafra, supplier_terms_apply: true };
      component.responses.set([respDahabi, wafraWithTerms]);
      fixture.detectChanges();

      expect(component.isLowestLinePrice(wafraWithTerms, wafraWithTerms.lines[0])).toBeTrue();
      expect(component.isLowestLinePrice(wafraWithTerms, wafraWithTerms.lines[1])).toBeTrue();
      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[2])).toBeTrue();
      expect(component.isLowestLinePrice(respDahabi, respDahabi.lines[3])).toBeTrue();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(4);
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
      expect(component.splitSaving()).toBeNull();
    });

    it('landed costs: absent entirely (older API) → no marks, no hint; Lowest total chip unchanged', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const { respDahabi, respWafra, rfqLines } = createD8f7fb0cFixtures();
      applyD8f7fb0cDetail(rfqLines);
      const { rfq_landed_costs: _d, ...dahabiLegacy } = respDahabi;
      const { rfq_landed_costs: _w, ...wafraLegacy } = respWafra;
      void _d;
      void _w;
      component.responses.set([dahabiLegacy, wafraLegacy]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(0);
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();

      // Quoted totals still comparable → Lowest total chip on الذهبي (4830 < 4855)
      expect(component.lowestTotalResponseIds()).toEqual(new Set(['resp-dahabi']));
      const chips = compiled.querySelectorAll('.pp-chip-best');
      expect(chips.length).toBe(1);
      expect(chips[0].textContent?.trim()).toBe('Lowest total');
    });

    it('fired state: fired outcome has the fired class, the draft link points to /requests/<purchase_request_id>; no link when purchase_request_id is null', () => {
      const { respDahabi } = createD8f7fb0cFixtures();
      component.responses.set([respDahabi]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const firedReason = compiled.querySelector('.outcome-reason.fired');
      expect(firedReason).not.toBeNull();

      const draftLink = compiled.querySelector<HTMLAnchorElement>('[data-testid="guardrail-draft-link"]');
      expect(draftLink).not.toBeNull();
      expect(draftLink?.getAttribute('href')).toBe('/requests/34049121-0000-0000-0000-000000000000');

      // When purchase_request_id is null
      const respNoDraft = {
        ...respDahabi,
        guardrail_evaluations: [
          {
            guardrail_id: 'g-1',
            fired: true,
            reason: 'fired',
            purchase_request_id: null,
          },
        ],
      };
      component.responses.set([respNoDraft]);
      fixture.detectChanges();

      expect(compiled.querySelector('[data-testid="guardrail-draft-link"]')).toBeNull();
    });

    it('converted with one request: no enabled Prepare Request on any card; «Open request» links to /requests/<id>', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'converted' },
        converted_purchase_request_ids: ['pr-single-34049121'],
      });
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      // Prepare Request button should be replaced
      const openReqLinks = compiled.querySelectorAll<HTMLAnchorElement>('[data-testid="rfq-compare-open-request"]');
      expect(openReqLinks.length).toBe(2);
      expect(openReqLinks[0].getAttribute('href')).toBe('/requests/pr-single-34049121');
      expect(openReqLinks[1].getAttribute('href')).toBe('/requests/pr-single-34049121');

      // Calling prepareRequest returns early
      mockRfqApi.prepareRequest.calls.reset();
      component.prepareRequest(respDahabi);
      expect(mockRfqApi.prepareRequest).not.toHaveBeenCalled();
    });

    it('converted with two requests: Prepare Request disabled on every card and converted-reason shown', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'converted' },
        converted_purchase_request_ids: ['pr-1', 'pr-2'],
      });
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="rfq-compare-open-request"]')).toBeNull();

      const reasons = compiled.querySelectorAll('[data-testid="converted-reason"]');
      expect(reasons.length).toBe(2);
      expect(reasons[0].textContent).toContain('rfq.compare.convertedReason');

      // Buttons are disabled
      const cards = compiled.querySelectorAll('.response-card');
      const btn0 = cards[0].querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(btn0?.disabled).toBeTrue();
    });

    it('open (status responded): Prepare Request enabled as today; no open-request link; no converted reason', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      component.rfqDetail.set({
        ...sentDetail,
        // Still ahead, so the date does not date this test (a past date disables Prepare).
        rfq: { ...sentDetail.rfq, status: 'responded', needed_by_date: '2099-12-31' },
      });
      component.responses.set([respDahabi, respWafra]);
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="rfq-compare-open-request"]')).toBeNull();
      expect(compiled.querySelector('[data-testid="converted-reason"]')).toBeNull();

      const cards = compiled.querySelectorAll('.response-card');
      const btn0 = cards[0].querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(btn0?.disabled).toBeFalse();
    });

    it('rfq_converted reason renders its translation key', () => {
      const { respDahabi } = createD8f7fb0cFixtures();
      const respConverted = {
        ...respDahabi,
        guardrail_evaluations: [
          {
            guardrail_id: 'g-1',
            fired: false,
            reason: 'rfq_converted',
          },
        ],
      };
      component.responses.set([respConverted]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('rfq.guardrails.reasons.rfq_converted');
    });

    it('handles 409 rfq_already_converted in prepareRequest by showing alreadyConverted and reloading data', () => {
      const { respDahabi } = createD8f7fb0cFixtures();
      component.rfqDetail.set(sentDetail);
      component.responses.set([respDahabi]);
      component.selectedBranchId.set('branch-1');

      mockRfqApi.prepareRequest.and.returnValue(
        throwError(() => new HttpErrorResponse({
          status: 409,
          error: { details: { reason: 'rfq_already_converted' } },
        })),
      );
      spyOn(component, 'loadData');

      component.prepareRequest(respDahabi);

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        'rfq.compare.alreadyConverted',
        'rfq.history.dismiss',
        { duration: 5000 },
      );
      expect(component.loadData).toHaveBeenCalledWith('rfq-1');
    });
  });

  describe('landed totals, coverage and the converted hint (P-155, PPS-199)', () => {
    const el = (): HTMLElement => fixture.nativeElement as HTMLElement;
    const rfqLine = (product: string) => ({
      id: `line-${product}`,
      tenant_id: 'tenant-1',
      rfq_id: 'rfq-1',
      workspace_product_id: product,
      quantity: '10',
      created_at: '2026-09-25T09:00:00Z',
    });
    const reply = (id: string, supplier: string, products: string[], price: string, landed: string) => ({
      id,
      rfq_id: 'rfq-1',
      supplier_id: supplier,
      quotation_id: `quote-${id}`,
      quotation_status: 'reviewed' as const,
      submitted_at: '2026-09-25T10:00:00Z',
      lines: products.map((product) => ({
        workspace_product_id: product,
        original_text: product,
        quoted_quantity: '10',
        quoted_unit_price_amount: price,
        quoted_unit_price_currency: 'SAR',
        pending_match: false,
      })),
      rfq_landed_costs: products.map((product) => ({
        workspace_product_id: product,
        total_amount: landed,
        total_currency: 'SAR',
      })),
    });
    const load = (replies: ReturnType<typeof reply>[], products: string[], status = 'sent'): void => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      mockRfqApi.getRfq.and.returnValue(
        of({
          ...sentDetail,
          rfq: { ...sentDetail.rfq, status: status as RfqDetail['rfq']['status'] },
          lines: products.map(rfqLine),
        } as RfqDetail),
      );
      mockRfqApi.listResponses.and.returnValue(of({ items: replies }));
      component.loadData('rfq-1');
      fixture.detectChanges();
    };

    it('marks «Lowest total» on landed totals, not on printed prices, and shows both', () => {
      // A prints cheaper (2,000 vs 2,100) but its quote excludes VAT: landed 2,300 vs 2,100.
      load(
        [
          reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1150'),
          reply('b', 'supp-b', ['p1', 'p2'], '105.00', '1050'),
        ],
        ['p1', 'p2'],
      );

      const cards = Array.from(el().querySelectorAll('.response-card')) as HTMLElement[];
      expect(cards.length).toBe(2);
      expect(cards[0].querySelector('.lowest-total-chip')).withContext('A is not the lowest').toBeNull();
      expect(cards[1].querySelector('.lowest-total-chip')).withContext('B is the lowest').toBeTruthy();
      expect(cards[0].querySelector('[data-testid="landed-total"]')?.textContent).toContain('2,300');
      expect(cards[1].querySelector('[data-testid="landed-total"]')?.textContent).toContain('2,100');
      // The chip sits next to the landed figure that earned it, not next to the printed total.
      expect(cards[1].querySelector('[data-testid="landed-total"] .lowest-total-chip')).toBeTruthy();
      expect(cards[1].querySelector('tr.total-row .lowest-total-chip')).toBeNull();
    });

    it('says how many of the RFQ products a reply covers when it misses some', () => {
      load(
        [
          reply('partial', 'supp-a', ['p1', 'p2'], '100.00', '1000'),
          reply('full', 'supp-b', ['p1', 'p2', 'p3'], '100.00', '1000'),
        ],
        ['p1', 'p2', 'p3'],
      );

      const cards = Array.from(el().querySelectorAll('.response-card')) as HTMLElement[];
      expect(cards[0].querySelector('[data-testid="coverage-badge"]')?.textContent).toContain('Covers 2 of 3');
      expect(cards[1].querySelector('[data-testid="coverage-badge"]')).toBeNull();
    });

    it('awards no «Lowest total» when a reply has incomplete landed costs, even if printed totals point one way', () => {
      // A prints cheaper (2,000 vs 2,100) and has full landed costs; B is missing p2's landed cost.
      const incomplete = reply('b', 'supp-b', ['p1', 'p2'], '105.00', '1050');
      incomplete.rfq_landed_costs = incomplete.rfq_landed_costs.slice(0, 1);
      load([reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1150'), incomplete], ['p1', 'p2']);

      expect(el().querySelector('.lowest-total-chip')).toBeNull();
    });

    it('keeps ranking on printed totals when no reply has any landed cost at all', () => {
      const noCosts = (id: string, supplier: string, price: string) => ({
        ...reply(id, supplier, ['p1', 'p2'], price, '0'),
        rfq_landed_costs: [],
      });
      load([noCosts('a', 'supp-a', '100.00'), noCosts('b', 'supp-b', '105.00')], ['p1', 'p2']);

      const cards = Array.from(el().querySelectorAll('.response-card')) as HTMLElement[];
      expect(cards[0].querySelector('.lowest-total-chip')).toBeTruthy();
      expect(cards[1].querySelector('.lowest-total-chip')).toBeNull();
    });

    it('awards no «Lowest total» when a supplier has delivery or minimum-order terms the totals cannot price', () => {
      const withTerms = { ...reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000'), supplier_terms_apply: true };
      load([withTerms, reply('b', 'supp-b', ['p1', 'p2'], '105.00', '1050')], ['p1', 'p2']);

      expect(el().querySelector('.lowest-total-chip')).toBeNull();
    });

    it('disables Prepare with a reason when a responded RFQ\'s needed-by date has passed', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      mockRfqApi.getRfq.and.returnValue(
        of({
          ...sentDetail,
          rfq: { ...sentDetail.rfq, status: 'responded', needed_by_date: '2020-01-01' },
          lines: ['p1', 'p2'].map(rfqLine),
        } as RfqDetail),
      );
      mockRfqApi.listResponses.and.returnValue(of({ items: [reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000')] }));
      component.loadData('rfq-1');
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const button = el().querySelector('.prepare-buttons-row button') as HTMLButtonElement;
      expect(button.disabled).toBeTrue();
      expect(el().querySelector('[data-testid="needed-by-past-reason"]')?.textContent).toContain(
        enCatalog.rfq.compare.neededByPast,
      );
    });

    it('keeps Prepare available when a responded RFQ\'s needed-by date is still ahead', () => {
      mockRfqApi.getRfq.and.returnValue(
        of({
          ...sentDetail,
          rfq: { ...sentDetail.rfq, status: 'responded', needed_by_date: '2099-12-31' },
          lines: ['p1', 'p2'].map(rfqLine),
        } as RfqDetail),
      );
      mockRfqApi.listResponses.and.returnValue(of({ items: [reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000')] }));
      component.loadData('rfq-1');
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const button = el().querySelector('.prepare-buttons-row button') as HTMLButtonElement;
      expect(button.disabled).toBeFalse();
      expect(el().querySelector('[data-testid="needed-by-past-reason"]')).toBeNull();
    });

    it('shows no coverage badge for a reply that is still being read or not matched yet', () => {
      const reading = { ...reply('read', 'supp-a', [], '0', '0'), rfq_landed_costs: [] };
      const unmatched = reply('un', 'supp-b', ['p1', 'p2'], '100.00', '1000');
      unmatched.lines[1] = { ...unmatched.lines[1], workspace_product_id: null as never, pending_match: true };
      load([reading, unmatched], ['p1', 'p2']);

      expect(el().querySelector('[data-testid="coverage-badge"]')).toBeNull();
    });

    it('tells the buyer when the RFQ date is already in the past instead of blaming unmatched lines', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      load([reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000')], ['p1', 'p2']);
      mockRfqApi.prepareRequest.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 422,
              error: { code: 'unprocessable', details: { reason: 'required_by_in_the_past' } },
            }),
        ),
      );
      component.selectedBranchId.set('branch-1');
      mockSnackBar.open.calls.reset();

      component.prepareRequest(component.responses()[0]);

      expect(mockSnackBar.open.calls.mostRecent().args[0]).toBe(enCatalog.requests.errors.required_by_in_the_past);
    });

    it('shows the RFQ\'s needed-by date read-only: the draft follows it, so there is nothing to edit', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
      load([reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000')], ['p1', 'p2']);

      const neededBy = el().querySelector('[data-testid="needed-by"]');
      expect(neededBy).withContext('needed-by block').toBeTruthy();
      expect(neededBy?.textContent).toContain(enCatalog.rfq.compare.neededByLabel);
      expect(neededBy?.textContent).toContain('2026');
      expect(el().querySelector('input.mat-datepicker-input')).withContext('no editable date').toBeNull();
    });

    it('words the saving hint on a converted RFQ as a missed saving and names its basis', () => {
      load(
        [
          { ...reply('a', 'supp-a', ['p1', 'p2'], '100.00', '1000'), rfq_landed_costs: [
              { workspace_product_id: 'p1', total_amount: '1000', total_currency: 'SAR' },
              { workspace_product_id: 'p2', total_amount: '1200', total_currency: 'SAR' },
            ] },
          { ...reply('b', 'supp-b', ['p1', 'p2'], '100.00', '1100'), rfq_landed_costs: [
              { workspace_product_id: 'p1', total_amount: '1100', total_currency: 'SAR' },
              { workspace_product_id: 'p2', total_amount: '1000', total_currency: 'SAR' },
            ] },
        ],
        ['p1', 'p2'],
        'converted',
      );

      const hint = el().querySelector('[data-testid="split-saving-hint"]');
      expect(hint?.textContent).toContain('would have saved');
      expect(hint?.textContent).toContain('landed cost');
    });
  });

  describe('page robustness (P-156, PPS-200)', () => {
    const matchedReply = (id: string, supplierId: string, productId: string): RfqResponseComparisonList['items'][number] => ({
      id,
      rfq_id: 'rfq-1',
      supplier_id: supplierId,
      quotation_id: `quote-${id}`,
      quotation_status: 'reviewed',
      submitted_at: '2026-09-25T10:00:00Z',
      lines: [
        {
          workspace_product_id: productId,
          original_text: 'x',
          quoted_quantity: '10',
          quoted_unit_price_amount: '5.00',
          quoted_unit_price_currency: 'USD',
          pending_match: false,
        },
      ],
    });
    const recreate = (): void => {
      fixture = TestBed.createComponent(CompareComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    };
    const el = (): HTMLElement => fixture.nativeElement as HTMLElement;

    it('shows product and supplier names that are not on the first page of the lists', () => {
      mockRfqApi.listResponses.and.returnValue(
        of({ items: [matchedReply('r-far', 'supp-999', 'prod-999')] }),
      );
      mockApiService.product.and.returnValue(of({ id: 'prod-999', tenant_name: 'Far Product' } as Product));
      mockApiService.supplier.and.returnValue(of({ id: 'supp-999', name: 'Far Supplier' } as Supplier));

      component.loadData('rfq-1');
      fixture.detectChanges();

      expect(mockApiService.product).toHaveBeenCalledTimes(1);
      expect(mockApiService.product).toHaveBeenCalledWith('prod-999');
      expect(mockApiService.supplier).toHaveBeenCalledWith('supp-999');
      expect(el().textContent).toContain('Far Product');
      expect(el().textContent).toContain('Far Supplier');
      expect(el().textContent).not.toContain('prod-999');
    });

    it('does not offer Prepare request to roles that cannot prepare', () => {
      mockSession.hasRole.and.returnValue(false);
      recreate();

      expect(el().querySelector('.prepare-buttons-row button')).toBeNull();
    });

    it('does not enable the split for two replies from the same supplier', () => {
      mockRfqApi.listResponses.and.returnValue(
        of({ items: [matchedReply('a', 'supp-1', 'prod-1'), matchedReply('b', 'supp-1', 'prod-1')] }),
      );
      component.loadData('rfq-1');
      fixture.detectChanges();

      expect(component.splitEligibility().canSplit).toBeFalse();
      const split = el().querySelector('[data-testid="rfq-compare-split-button"]') as HTMLButtonElement | null;
      expect(split?.disabled).toBeTrue();
    });

    it('retries a name lookup that failed the first time on the next load', () => {
      mockRfqApi.listResponses.and.returnValue(
        of({ items: [matchedReply('r-far', 'supp-1', 'prod-999')] }),
      );
      mockApiService.product.and.returnValues(
        throwError(() => new Error('busy')),
        of({ id: 'prod-999', tenant_name: 'Far Product' } as Product),
      );

      component.loadData('rfq-1');
      component.loadData('rfq-1');
      fixture.detectChanges();

      expect(mockApiService.product).toHaveBeenCalledTimes(2);
      expect(component.productNames()['prod-999']).toBe('Far Product');
    });

    it('shows no split saving for replies from one supplier only', () => {
      const costs = (a: string, b: string) => [
        { workspace_product_id: 'p1', total_amount: a, total_currency: 'USD' },
        { workspace_product_id: 'p2', total_amount: b, total_currency: 'USD' },
      ];
      const reply = (id: string, a: string, b: string) => ({
        ...matchedReply(id, 'supp-1', 'p1'),
        rfq_landed_costs: costs(a, b),
      });
      mockRfqApi.getRfq.and.returnValue(
        of({
          ...sentDetail,
          lines: ['p1', 'p2'].map((product) => ({
            id: `line-${product}`,
            tenant_id: 'tenant-1',
            rfq_id: 'rfq-1',
            workspace_product_id: product,
            quantity: '10',
            created_at: '2026-09-25T09:00:00Z',
          })),
        }),
      );
      mockRfqApi.listResponses.and.returnValue(
        of({ items: [reply('a', '100', '200'), reply('b', '150', '120')] }),
      );

      component.loadData('rfq-1');
      fixture.detectChanges();

      expect(component.splitSaving()).toBeNull();
      expect(el().querySelector('[data-testid="split-saving-hint"]')).toBeNull();
    });

    it('shows no split saving when a supplier has more than one reply, since the split prices them by recorded cost', () => {
      const reply = (id: string, supplier: string, a: string, b: string, at: string) => ({
        ...matchedReply(id, supplier, 'p1'),
        submitted_at: at,
        rfq_landed_costs: [
          { workspace_product_id: 'p1', total_amount: a, total_currency: 'USD' },
          { workspace_product_id: 'p2', total_amount: b, total_currency: 'USD' },
        ],
      });
      mockRfqApi.getRfq.and.returnValue(
        of({
          ...sentDetail,
          lines: ['p1', 'p2'].map((product) => ({
            id: `line-${product}`,
            tenant_id: 'tenant-1',
            rfq_id: 'rfq-1',
            workspace_product_id: product,
            quantity: '10',
            created_at: '2026-09-25T09:00:00Z',
          })),
        }),
      );
      // Two suppliers; supp-1 sent an older and a newer reply. Without the second reply the split would save money.
      mockRfqApi.listResponses.and.returnValue(
        of({
          items: [
            reply('old', 'supp-1', '100', '200', '2026-09-25T10:00:00Z'),
            reply('new', 'supp-1', '110', '210', '2026-09-26T10:00:00Z'),
            reply('other', 'supp-2', '150', '120', '2026-09-25T11:00:00Z'),
          ],
        }),
      );

      component.loadData('rfq-1');
      fixture.detectChanges();

      expect(component.splitEligibility().canSplit).toBeTrue();
      expect(component.splitSaving()).toBeNull();
      expect(el().querySelector('[data-testid="split-saving-hint"]')).toBeNull();
    });

    it('shows no Prepare prerequisites to roles that cannot prepare', () => {
      mockSession.hasRole.and.returnValue(false);
      recreate();

      expect(el().querySelector('.prepare-actions .disabled-reason')).toBeNull();
    });

    it('offers Retry when the responses cannot be loaded', () => {
      mockRfqApi.listResponses.and.returnValue(throwError(() => new Error('boom')));
      component.loadData('rfq-1');
      fixture.detectChanges();

      const retry = el().querySelector('[data-testid="rfq-compare-retry"]') as HTMLButtonElement | null;
      expect(retry).toBeTruthy();
      mockRfqApi.listResponses.calls.reset();
      mockRfqApi.listResponses.and.returnValue(of(dummyResponses));
      retry!.click();
      expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-1');
    });

    it('prepares a request once when Prepare is clicked twice', () => {
      const pending$ = new Subject<PrepareRequestResponse>();
      mockRfqApi.prepareRequest.and.returnValue(pending$);
      const reply = matchedReply('solo', 'supp-1', 'prod-1');
      component.responses.set([reply]);

      component.prepareRequest(reply);
      component.prepareRequest(reply);
      component.prepareRequest(reply);

      expect(mockRfqApi.prepareRequest).toHaveBeenCalledTimes(1);
      expect(mockRfqApi.prepareRequest).toHaveBeenCalledWith(
        'rfq-1',
        jasmine.objectContaining({ rfq_response_id: 'solo' }), jasmine.any(String));
    });
  });

  describe('screen-reader states (P-159, PPS-203)', () => {
    const el = (): HTMLElement => fixture.nativeElement as HTMLElement;

    it('announces loading with a labelled spinner', () => {
      component.isLoading.set(true);
      fixture.detectChanges();

      const loading = el().querySelector('.loading-state');
      expect(loading?.getAttribute('role')).toBe('status');
      expect(loading?.querySelector('mat-spinner')?.getAttribute('aria-label')).toBeTruthy();
    });

    it('announces a load error as an alert', () => {
      component.isLoading.set(false);
      component.errorMessage.set('Could not load');
      fixture.detectChanges();

      expect(el().querySelector('.error-state')?.getAttribute('role')).toBe('alert');
    });

    it('announces the empty state as a status', () => {
      component.isLoading.set(false);
      component.errorMessage.set(null);
      component.responses.set([]);
      fixture.detectChanges();

      expect(el().querySelector('.empty-state')?.getAttribute('role')).toBe('status');
    });
  });

  describe('PPS-175: RFQ Compare Prepare Eligibility and Error Handling', () => {
    it('empty-lines reply is not eligible and shows "still being read" reason', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const emptyLinesReply: RfqResponseComparison = {
        ...dummyResponses.items[0],
        id: 'resp-empty',
        quotation_status: 'reviewed',
        lines: [],
      };

      expect(component.isEligible(emptyLinesReply)).toBeFalse();
      expect(component.ineligibilityReason(emptyLinesReply)).toBe('rfq.compare.stillBeingRead');

      component.responses.set([emptyLinesReply]);
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const card = compiled.querySelector('.response-card');
      const prepareBtn = card?.querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(prepareBtn?.disabled).toBeTrue();
      expect(card?.querySelector('.prepare-actions')?.textContent).toContain(
        enCatalog.rfq.compare.stillBeingRead,
      );
    });

    it('unreviewed reply is not eligible and shows awaiting review reason', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const unreviewedReply: RfqResponseComparison = {
        ...dummyResponses.items[0],
        id: 'resp-unreviewed',
        quotation_status: 'extracted',
      };

      expect(component.isEligible(unreviewedReply)).toBeFalse();
      expect(component.ineligibilityReason(unreviewedReply)).toBe('rfq.compare.awaitingReview');

      component.responses.set([unreviewedReply]);
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const card = compiled.querySelector('.response-card');
      const prepareBtn = card?.querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(prepareBtn?.disabled).toBeTrue();
      expect(card?.querySelector('.prepare-actions')?.textContent).toContain(
        enCatalog.rfq.compare.awaitingReview,
      );
    });

    it('mixed-currency reply shows notice, no single total, and button is disabled', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const mixedReply: RfqResponseComparison = {
        ...dummyResponses.items[0],
        id: 'resp-mixed',
        quotation_status: 'reviewed',
        lines: [
          {
            workspace_product_id: 'prod-1',
            original_text: 'Item 1 USD',
            quoted_quantity: '2',
            quoted_unit_price_amount: '10.00',
            quoted_unit_price_currency: 'USD',
            pending_match: false,
          },
          {
            workspace_product_id: 'prod-2',
            original_text: 'Item 2 EUR',
            quoted_quantity: '1',
            quoted_unit_price_amount: '20.00',
            quoted_unit_price_currency: 'EUR',
            pending_match: false,
          },
        ],
      };

      expect(component.hasMixedCurrencies(mixedReply)).toBeTrue();
      expect(component.canPrepare(mixedReply)).toBeFalse();
      expect(component.responseTotal(mixedReply)).toBeNull();

      component.responses.set([mixedReply]);
      component.selectedBranchId.set('branch-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const card = compiled.querySelector('.response-card');
      const prepareBtn = card?.querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(prepareBtn?.disabled).toBeTrue();

      const expectedNotice = enCatalog.rfq.compare.mixedCurrenciesNotice;
      expect(card?.textContent).toContain(expectedNotice);

      const totalCell = card?.querySelector('.total-value-cell');
      expect(totalCell?.textContent).not.toContain('40');
      expect(totalCell?.textContent).not.toContain('USD');
      expect(totalCell?.textContent).not.toContain('EUR');
    });

    it('each mapped API reason shows its translated message', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const testReasons: { reason: string; fallbackText: string }[] = [
        { reason: 'mixed_currencies', fallbackText: enCatalog.rfq.compare.prepareErrorMixedCurrencies },
        { reason: 'no_quotation_lines', fallbackText: enCatalog.rfq.compare.prepareErrorNoQuotationLines },
        { reason: 'pending_matches', fallbackText: enCatalog.rfq.compare.prepareErrorPendingMatches },
        { reason: 'no_matched_lines', fallbackText: enCatalog.rfq.compare.prepareErrorNoMatchedLines },
        { reason: 'no_pricing_for_rfq_products', fallbackText: enCatalog.rfq.compare.prepareErrorNoPricingForRfqProducts },
        { reason: 'quotation_archived', fallbackText: enCatalog.rfq.compare.prepareErrorQuotationArchived },
        { reason: 'quotation_refused', fallbackText: enCatalog.rfq.compare.prepareErrorQuotationRefused },
      ];

      component.rfqDetail.set(sentDetail);
      component.selectedBranchId.set('branch-1');

      for (const { reason, fallbackText } of testReasons) {
        mockSnackBar.open.calls.reset();
        mockRfqApi.prepareRequest.and.returnValue(
          throwError(
            () =>
              new HttpErrorResponse({
                status: 422,
                error: {
                  message: 'Backend raw message should never be printed',
                  details: { reason },
                },
              }),
          ),
        );

        component.prepareRequest(dummyResponses.items[0]);

        expect(mockSnackBar.open).toHaveBeenCalledWith(
          fallbackText,
          enCatalog.rfq.history.dismiss,
          { duration: 5000 },
        );
      }
    });

    it('double click on an eligible reply calls rfqApi.prepareRequest exactly once', () => {
      component.rfqDetail.set(sentDetail);
      component.selectedBranchId.set('branch-1');

      const pendingSubject = new Subject<PrepareRequestResponse>();
      mockRfqApi.prepareRequest.and.returnValue(pendingSubject.asObservable());

      // First click
      component.prepareRequest(dummyResponses.items[0]);
      // Second click while in-flight
      component.prepareRequest(dummyResponses.items[0]);

      expect(mockRfqApi.prepareRequest).toHaveBeenCalledTimes(1);

      // Verify preparing state clears on completion
      pendingSubject.next({ purchase_request_id: 'pr-1' } as PrepareRequestResponse);
      pendingSubject.complete();
      expect(component.preparing()).toBeNull();
    });

    it('an unknown error shows the generic message, not err.error.message', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      component.rfqDetail.set(sentDetail);
      component.selectedBranchId.set('branch-1');

      mockRfqApi.prepareRequest.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 500,
              error: {
                message: 'Fatal Postgres connection error',
                details: { reason: 'unknown_database_failure' },
              },
            }),
        ),
      );

      component.prepareRequest(dummyResponses.items[0]);

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        enCatalog.rfq.compare.prepareError,
        enCatalog.rfq.history.dismiss,
        { duration: 5000 },
      );
      expect(mockSnackBar.open).not.toHaveBeenCalledWith(
        jasmine.stringMatching(/Fatal Postgres connection error/),
        jasmine.any(String),
        jasmine.any(Object),
      );
    });
  });

  describe('PPS-180: Resilient and honest RFQ Compare', () => {
    beforeEach(() => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');
    });

    it('stale response for an old id is ignored', fakeAsync(() => {
      const responsesA$ = new Subject<RfqResponseComparisonList>();
      const responsesB$ = new Subject<RfqResponseComparisonList>();

      mockRfqApi.listResponses.and.callFake((id: string) => {
        if (id === 'rfq-A') return responsesA$;
        if (id === 'rfq-B') return responsesB$;
        return of(dummyResponses);
      });

      component.loadData('rfq-A');
      fixture.detectChanges();

      component.loadData('rfq-B');
      fixture.detectChanges();

      const responsesBData: RfqResponseComparisonList = {
        items: [{ ...dummyResponses.items[0], id: 'resp-B' }],
      };
      responsesB$.next(responsesBData);
      responsesB$.complete();
      fixture.detectChanges();

      expect(component.responses()[0].id).toBe('resp-B');

      // Now stale responses for A arrive
      const responsesAData: RfqResponseComparisonList = {
        items: [{ ...dummyResponses.items[0], id: 'resp-A' }],
      };
      responsesA$.next(responsesAData);
      responsesA$.complete();
      fixture.detectChanges();

      expect(component.responses()[0].id).toBe('resp-B');
    }));

    it('detail Retry pending, id changes to B, A retry resolves -> B detail and requiredByDate are unchanged', fakeAsync(() => {
      const detailARetry$ = new Subject<RfqDetail>();
      const detailB: RfqDetail = {
        rfq: {
          ...sentDetail.rfq,
          id: 'rfq-B',
          needed_by_date: '2026-11-15',
        },
        lines: [],
        recipients: [],
      };
      const detailA: RfqDetail = {
        rfq: {
          ...sentDetail.rfq,
          id: 'rfq-A',
          needed_by_date: '2026-10-20',
        },
        lines: [],
        recipients: [],
      };

      mockRfqApi.getRfq.and.callFake((id: string) => {
        if (id === 'rfq-A') return detailARetry$;
        if (id === 'rfq-B') return of(detailB);
        return of(sentDetail);
      });
      mockRfqApi.listResponses.and.returnValue(of({ items: [] }));

      component.rfqId.set('rfq-A');
      component.rfqDetailError.set(true);

      component.reloadRfqDetail();

      component.loadData('rfq-B');
      fixture.detectChanges();

      const dateB = parseIsoDateLocal('2026-11-15')!;
      expect(component.rfqDetail()).toEqual(detailB);
      expect(component.requiredByDate()).toEqual(dateB);

      detailARetry$.next(detailA);
      detailARetry$.complete();
      fixture.detectChanges();

      expect(component.rfqDetail()).toEqual(detailB);
      expect(component.requiredByDate()).toEqual(dateB);
    }));

    it('branches failure shows the warning with Retry and Prepare disabled', fakeAsync(() => {
      mockApiService.listBranches.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
      component.loadBranches();
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const branchWarning = compiled.querySelector('[data-testid="branches-load-error"]');
      expect(branchWarning).not.toBeNull();
      expect(branchWarning?.textContent).toContain('Failed to load branches.');

      const retryBtn = branchWarning?.querySelector<HTMLButtonElement>('[data-testid="retry-branches-button"]');
      expect(retryBtn).not.toBeNull();
      expect(retryBtn?.textContent?.trim()).toBe('Retry');

      // Prepare must be disabled
      expect(component.canPrepare(dummyResponses.items[0])).toBeFalse();
      const reasonEl = compiled.querySelector('[data-testid="branches-error-reason"]');
      expect(reasonEl).not.toBeNull();
      expect(reasonEl?.textContent).toContain('Failed to load branches.');

      // Retrying reloads branches
      mockApiService.listBranches.and.returnValue(of({
        items: [{ id: 'branch-1', name: 'Main Branch' }],
        next_cursor: null,
      } as unknown as { items: Branch[]; next_cursor: string | null }));
      retryBtn?.click();
      fixture.detectChanges();

      expect(compiled.querySelector('[data-testid="branches-load-error"]')).toBeNull();
      expect(component.branches().length).toBe(1);
      expect(component.canPrepare(dummyResponses.items[0])).toBeTrue();
    }));

    it('expired RFQ shows the notice and disables Prepare and Split', fakeAsync(() => {
      const expiredDetail: RfqDetail = {
        ...sentDetail,
        rfq: {
          ...sentDetail.rfq,
          status: 'expired',
        },
      };
      mockRfqApi.getRfq.and.returnValue(of(expiredDetail));
      component.loadData('rfq-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const expiredNotice = compiled.querySelector('[data-testid="rfq-compare-expired-notice"]');
      expect(expiredNotice).not.toBeNull();
      expect(expiredNotice?.textContent).toContain('This RFQ has expired — requests can no longer be prepared from it');

      // Prepare is disabled
      expect(component.canPrepare(dummyResponses.items[0])).toBeFalse();
      const prepareBtn = compiled.querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(prepareBtn?.disabled).toBeTrue();
      const expiredReason = compiled.querySelector('[data-testid="expired-reason"]');
      expect(expiredReason).not.toBeNull();
      expect(expiredReason?.textContent).toContain('This RFQ has expired');

      // Split is disabled
      expect(component.splitEligibility().canSplit).toBeFalse();
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtn?.disabled).toBeTrue();
    }));

    it('API reason rfq_expired shows the translated message for prepare and split', fakeAsync(() => {
      const expiredHttpError = new HttpErrorResponse({
        status: 422,
        error: { details: { reason: 'rfq_expired' } },
      });

      mockRfqApi.prepareRequest.and.returnValue(throwError(() => expiredHttpError));
      component.prepareRequest(dummyResponses.items[0]);

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        translate.instant('rfq.compare.prepareErrorRfqExpired'),
        translate.instant('rfq.history.dismiss'),
        jasmine.objectContaining({ duration: 5000 }),
      );

      // Now split with rfq_expired
      const resp1 = dummyResponses.items[0];
      const resp2 = { ...dummyResponses.items[0], id: 'resp-usd-2', supplier_id: 'supp-2', quotation_id: 'quote-2' };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      mockSnackBar.open.calls.reset();
      mockRfqApi.splitRfq.and.returnValue(throwError(() => expiredHttpError));
      component.splitRfq();

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        translate.instant('rfq.compare.prepareErrorRfqExpired'),
        translate.instant('rfq.history.dismiss'),
        jasmine.objectContaining({ duration: 5000 }),
      );
    }));
    it('cancelled RFQ shows the notice and disables Prepare and Split', fakeAsync(() => {
      const cancelledDetail: RfqDetail = {
        ...sentDetail,
        rfq: {
          ...sentDetail.rfq,
          status: 'cancelled',
        },
      };
      mockRfqApi.getRfq.and.returnValue(of(cancelledDetail));
      component.loadData('rfq-1');
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const cancelledNotice = compiled.querySelector('[data-testid="rfq-compare-cancelled-notice"]');
      expect(cancelledNotice).not.toBeNull();
      expect(cancelledNotice?.textContent).toContain('This RFQ was cancelled — requests can no longer be prepared from it');

      // Prepare is disabled
      expect(component.canPrepare(dummyResponses.items[0])).toBeFalse();
      const prepareBtn = compiled.querySelector<HTMLButtonElement>('.prepare-buttons-row button');
      expect(prepareBtn?.disabled).toBeTrue();
      const cancelledReason = compiled.querySelector('[data-testid="cancelled-reason"]');
      expect(cancelledReason).not.toBeNull();
      expect(cancelledReason?.textContent).toContain('This RFQ was cancelled');

      // Split is disabled
      expect(component.splitEligibility().canSplit).toBeFalse();
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtn?.disabled).toBeTrue();
      component.prepareRequest(dummyResponses.items[0]);
      component.splitRfq();
      expect(mockRfqApi.prepareRequest).not.toHaveBeenCalled();
      expect(mockRfqApi.splitRfq).not.toHaveBeenCalled();
    }));

    it('API reason rfq_cancelled shows the translated message for prepare and split', fakeAsync(() => {
      const cancelledHttpError = new HttpErrorResponse({
        status: 422,
        error: { details: { reason: 'rfq_cancelled' } },
      });

      mockRfqApi.prepareRequest.and.returnValue(throwError(() => cancelledHttpError));
      component.prepareRequest(dummyResponses.items[0]);

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        translate.instant('rfq.compare.rfqCancelled'),
        translate.instant('rfq.history.dismiss'),
        jasmine.objectContaining({ duration: 5000 }),
      );

      // Now split with rfq_cancelled
      const resp1 = dummyResponses.items[0];
      const resp2 = { ...dummyResponses.items[0], id: 'resp-usd-2', supplier_id: 'supp-2', quotation_id: 'quote-2' };
      component.responses.set([resp1, resp2]);
      fixture.detectChanges();

      mockSnackBar.open.calls.reset();
      mockRfqApi.splitRfq.and.returnValue(throwError(() => cancelledHttpError));
      component.splitRfq();

      expect(mockSnackBar.open).toHaveBeenCalledWith(
        translate.instant('rfq.compare.rfqCancelled'),
        translate.instant('rfq.history.dismiss'),
        jasmine.objectContaining({ duration: 5000 }),
      );
    }));
  });
  it('renders API names for entities absent from lookups, including variants and landed cost names', () => {
    const reply = {
      ...dummyResponses.items[0], supplier_id: 'missing-supplier', supplier_name: 'Archived supplier',
      lines: [{ ...dummyResponses.items[0].lines[0], workspace_product_id: 'missing-product', product_name: 'Archived product', product_variant: 'Large' }],
    };
    component.supplierNames.set({});
    component.productNames.set({});
    component.responses.set([reply]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Archived supplier');
    expect(fixture.nativeElement.textContent).toContain('Archived product (Large)');
    expect(fixture.nativeElement.textContent).not.toContain('missing-supplier');
    expect(fixture.nativeElement.textContent).not.toContain('missing-product');
    expect(component.productName({ ...reply, rfq_landed_costs: [{ workspace_product_id: 'missing-product', product_name: 'Cost product', product_variant: 'Small', total_amount: '1', total_currency: 'USD' }] }, { ...reply.lines[0], product_name: null, product_variant: null })).toBe('Cost product (Small)');
  });

  it('renders translated unknown names instead of entity IDs when names are unavailable', () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    component.supplierNames.set({});
    component.productNames.set({});
    component.responses.set([{
      ...dummyResponses.items[0], supplier_id: 'unknown-supplier-uuid', supplier_name: null,
      lines: [{ ...dummyResponses.items[0].lines[0], workspace_product_id: 'unknown-product-uuid', product_name: null }],
      rfq_landed_costs: [],
    }]);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Unknown supplier');
    expect(fixture.nativeElement.textContent).toContain('Unknown product');
    expect(fixture.nativeElement.textContent).not.toContain('unknown-supplier-uuid');
    expect(fixture.nativeElement.textContent).not.toContain('unknown-product-uuid');
  });

  it('reuses prepare keys on ambiguous failure and drops them on success or definitive rejection', () => {
    const reply = dummyResponses.items[0];
    component.selectedBranchId.set('branch-1');
    component.requiredByDate.set(new Date(2026, 11, 1));
    mockRfqApi.prepareRequest.and.returnValue(throwError(() => new HttpErrorResponse({ status: 503 })));
    component.prepareRequest(reply);
    const first = mockRfqApi.prepareRequest.calls.mostRecent().args[2];
    mockRfqApi.prepareRequest.and.returnValue(of({ purchase_request_id: 'pr-1' }));
    component.prepareRequest(reply);
    expect(mockRfqApi.prepareRequest.calls.mostRecent().args[2]).toBe(first);
    mockRfqApi.prepareRequest.and.returnValue(throwError(() => new HttpErrorResponse({ status: 422 })));
    component.prepareRequest(reply);
    const rejected = mockRfqApi.prepareRequest.calls.mostRecent().args[2];
    expect(rejected).not.toBe(first);
    component.prepareRequest(reply);
    expect(mockRfqApi.prepareRequest.calls.mostRecent().args[2]).not.toBe(rejected);
  });

});

describe('RFQ quantity display', () => {
  it('formats decimal quantities without trailing zeroes', () => {
    expect(formatLocaleNumber('50.000000', 'en')).toBe('50');
    expect(formatLocaleNumber('12.500000', 'en')).toBe('12.5');
  });

  it('formats 6-decimal precision quantities without truncation', () => {
    expect(formatExactQuantity('0.000001', 'en')).toBe('0.000001');
    expect(formatExactQuantity('1.234567', 'en')).toBe('1.234567');
    expect(formatExactQuantity('50.000000', 'en')).toBe('50');
  });

});
