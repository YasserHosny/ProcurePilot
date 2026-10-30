import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CompareComponent } from './compare.component';
import { formatExactQuantity, formatLocaleNumber } from '../../../core/format/format.service';
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
import { of, throwError } from 'rxjs';
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

    mockApiService = jasmine.createSpyObj('ApiService', ['listBranches', 'suppliers', 'products', 'members']);
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
    expect(mockRfqApi.sendRfq).toHaveBeenCalledWith('rfq-1');
    expect(mockSnackBar.open).toHaveBeenCalled();
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
    });

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
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
      expect(splitBtn).not.toBeNull();
      expect(splitBtn?.disabled).toBeTrue();

      const reason = compiled.querySelector('[data-testid="split-disabled-reason"]');
      expect(reason).not.toBeNull();
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
      const splitBtn = compiled.querySelector<HTMLButtonElement>('[data-testid="rfq-compare-split-button"]');
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
        expect(compare['alreadyConverted']).toBeTruthy();
        expect(compare['splitError']).toBeTruthy();
      }
    });
  });

  describe('PPS-123 & PPS-124: RFQ line minima, split hint, and converted state', () => {
    const createD8f7fb0cFixtures = () => {
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
        guardrail_evaluations: [
          {
            guardrail_id: 'g-1',
            fired: false,
            reason: 'not_lowest_price',
          },
        ],
      };

      return { respDahabi, respWafra };
    };

    it('per-line minima: oil and sugar lines of الوفرة carry lowest-line-price, rice and flour of الذهبي do', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
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

    it('per-line minima: a product quoted at the same price by both is marked on neither', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      // Make rice identical price (150) on both
      respWafra.lines[2] = { ...respWafra.lines[2], quoted_unit_price_amount: '150.00' };
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

    it('per-line minima: nothing is marked when quantities differ or a line is pending', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      // Different quantities
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
      expect(compiled.querySelectorAll('[data-testid="lowest-line-price"]').length).toBe(0);

      // Pending line
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

    it('split hint: shows SAR 60, triggers splitRfq when open/writer/eligible, hides action when converted, and has no bare route link', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog, true);
      translate.use('en');

      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'responded' },
      });
      component.responses.set([respDahabi, respWafra]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      const hint = compiled.querySelector('[data-testid="split-saving-hint"]');
      expect(hint).not.toBeNull();
      expect(hint?.textContent).toContain('60');

      // (a) open RFQ, writer, eligible -> the action exists and clicking it calls rfqApi.splitRfq with the RFQ id
      mockRfqApi.splitRfq.calls.reset();
      mockRfqApi.splitRfq.and.returnValue(
        of({ id: 'job-split-hint', rfq_id: 'rfq-1' } as unknown as BasketSplitJob),
      );
      const actionBtn = hint?.querySelector<HTMLButtonElement>('[data-testid="split-saving-hint-action"]');
      expect(actionBtn).not.toBeNull();
      actionBtn?.click();
      expect(mockRfqApi.splitRfq).toHaveBeenCalledWith('rfq-1', jasmine.any(String));

      // (b) converted RFQ -> the hint text with SAR 60 is shown and the action is absent
      component.rfqDetail.set({
        ...sentDetail,
        rfq: { ...sentDetail.rfq, status: 'converted' },
        converted_purchase_request_ids: ['pr-single-34049121'],
      });
      fixture.detectChanges();

      const convertedHint = compiled.querySelector('[data-testid="split-saving-hint"]');
      expect(convertedHint).not.toBeNull();
      expect(convertedHint?.textContent).toContain('60');
      expect(convertedHint?.querySelector('[data-testid="split-saving-hint-action"]')).toBeNull();

      // (c) no element in the hint has an href ending in /offers/basket-split
      const anyHintLinks = Array.from(convertedHint?.querySelectorAll<HTMLAnchorElement>('a') ?? []);
      for (const link of anyHintLinks) {
        expect(link.getAttribute('href') ?? '').not.toMatch(/\/offers\/basket-split$/);
      }
    });

    it('split hint: absent when per-line minimum equals the lowest total (one supplier cheapest everywhere)', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      // Make الذهبي cheaper on all lines
      const wafraExpensive = {
        ...respWafra,
        lines: respWafra.lines.map((l) => ({ ...l, quoted_unit_price_amount: '200.00' })),
      };
      component.responses.set([respDahabi, wafraExpensive]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
    });

    it('split hint: absent when not comparable', () => {
      const { respDahabi, respWafra } = createD8f7fb0cFixtures();
      // Mixed currencies
      const wafraUsd = {
        ...respWafra,
        lines: respWafra.lines.map((l) => ({ ...l, quoted_unit_price_currency: 'USD' })),
      };
      component.responses.set([respDahabi, wafraUsd]);
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="split-saving-hint"]')).toBeNull();
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
        rfq: { ...sentDetail.rfq, status: 'responded' },
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
