import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { IngestionEmailLog, IngestionStats } from '../ingestion-api';
import { DashboardComponent } from './dashboard.component';

describe('DashboardComponent (T026)', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;
  let httpTestingController: HttpTestingController;
  let translate: TranslateService;

  const mockStats: IngestionStats = {
    emails_received_today: 12,
    emails_received_week: 48,
    emails_received_month: 156,
    capture_uploads_total: 25,
    catalogue_imports_total: 8,
    supplier_match_rate: 0.85,
    extraction_success_rate: 0.92,
    active_quotation_count: 40,
    integration_sourced_quotation_count: 12,
    integration_sourced_share: 0.3,
    purchase_history_days: 120,
    g3_history_ready: false,
    active_refresh_schedule_count: 3,
    linked_refresh_schedule_count: 0,
    refresh_pilot_ready: false,
  };

  const mockZeroStats: IngestionStats = {
    emails_received_today: 0,
    emails_received_week: 0,
    emails_received_month: 0,
    capture_uploads_total: 0,
    catalogue_imports_total: 0,
    supplier_match_rate: 0.0,
    extraction_success_rate: 0.0,
    active_quotation_count: 0,
    integration_sourced_quotation_count: 0,
    integration_sourced_share: 0.0,
    purchase_history_days: 0,
    g3_history_ready: false,
    active_refresh_schedule_count: 0,
    linked_refresh_schedule_count: 0,
    refresh_pilot_ready: false,
  };

  const mockRecentEmails: IngestionEmailLog[] = [
    {
      id: 'em-001',
      message_id: 'msg-001@supplier1.com',
      from_address: 'invoices@supplier1.com',
      from_domain: 'supplier1.com',
      subject: 'Quotation Q-2026-001',
      received_at: '2026-09-17T09:00:00Z',
      processed_at: '2026-09-17T09:01:00Z',
      status: 'completed',
      error_message: null,
      attachment_count: 1,
      quotation_id: 'quot-001',
      supplier_id: 'supp-001',
      match_method: 'domain',
      created_at: '2026-09-17T09:00:00Z',
    },
    {
      id: 'em-002',
      message_id: 'msg-002@supplier2.com',
      from_address: 'sales@supplier2.com',
      from_domain: 'supplier2.com',
      subject: 'Price List Update',
      received_at: '2026-09-17T08:30:00Z',
      processed_at: '2026-09-17T08:31:00Z',
      status: 'processing',
      error_message: null,
      attachment_count: 2,
      quotation_id: null,
      supplier_id: 'supp-002',
      match_method: 'address',
      created_at: '2026-09-17T08:30:00Z',
    },
    {
      id: 'em-003',
      message_id: 'msg-003@unknown.com',
      from_address: 'orders@unknown.com',
      from_domain: 'unknown.com',
      subject: 'RFQ Response',
      received_at: '2026-09-17T08:00:00Z',
      processed_at: '2026-09-17T08:02:00Z',
      status: 'received',
      error_message: null,
      attachment_count: 1,
      quotation_id: null,
      supplier_id: null,
      match_method: null,
      created_at: '2026-09-17T08:00:00Z',
    },
    {
      id: 'em-004',
      message_id: 'msg-004@supplier3.com',
      from_address: 'billing@supplier3.com',
      from_domain: 'supplier3.com',
      subject: null,
      received_at: '2026-09-17T07:15:00Z',
      processed_at: '2026-09-17T07:16:00Z',
      status: 'failed',
      error_message: 'Unparseable PDF attachment',
      attachment_count: 1,
      quotation_id: null,
      supplier_id: 'supp-003',
      match_method: 'thread',
      created_at: '2026-09-17T07:15:00Z',
    },
    {
      id: 'em-005',
      message_id: 'msg-005@spam.com',
      from_address: 'promo@spam.com',
      from_domain: 'spam.com',
      subject: 'Special offer',
      received_at: '2026-09-17T06:00:00Z',
      processed_at: '2026-09-17T06:01:00Z',
      status: 'rejected',
      error_message: 'Domain not in allowlist',
      attachment_count: 0,
      quotation_id: null,
      supplier_id: null,
      match_method: null,
      created_at: '2026-09-17T06:00:00Z',
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
      ],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should load and render stats correctly', () => {
    fixture.detectChanges();

    const statsReq = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq.request.method).toBe('GET');
    statsReq.flush(mockStats);

    const emailsReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq.request.method).toBe('GET');
    emailsReq.flush({ items: mockRecentEmails, next_cursor: null });

    fixture.detectChanges();

    expect(component.isLoading()).toBeFalse();
    expect(component.stats()).toEqual(mockStats);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('12');
    expect(compiled.textContent).toContain('25');
    expect(compiled.textContent).toContain('8');
    expect(compiled.textContent).toContain('85%');
    expect(compiled.textContent).toContain('92%');
  });

  it('should render zero-stats tenant with 0% and 0 values without crashing', () => {
    fixture.detectChanges();

    const statsReq = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq.request.method).toBe('GET');
    statsReq.flush(mockZeroStats);

    const emailsReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq.request.method).toBe('GET');
    emailsReq.flush({ items: [], next_cursor: null });

    fixture.detectChanges();

    expect(component.isLoading()).toBeFalse();
    expect(component.stats()).toEqual(mockZeroStats);
    expect(component.formatRate(0)).toBe('0%');
    expect(component.getRatePercent(0)).toBe(0);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('0%');
    expect(compiled.textContent).toContain(enCatalog.ingestion.dashboard.recentEmails.emptyTitle);
  });

  it('should display up to 5 recent email logs in the recent emails table', () => {
    fixture.detectChanges();

    const statsReq = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq.request.method).toBe('GET');
    statsReq.flush(mockStats);

    const emailsReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq.request.method).toBe('GET');
    emailsReq.flush({ items: mockRecentEmails, next_cursor: null });

    fixture.detectChanges();

    expect(component.recentEmails().length).toBe(5);

    const compiled = fixture.nativeElement as HTMLElement;
    const tableRows = compiled.querySelectorAll('tr[mat-row]');
    expect(tableRows.length).toBe(5);

    expect(compiled.textContent).toContain('invoices@supplier1.com');
    expect(compiled.textContent).toContain('Quotation Q-2026-001');
    expect(compiled.textContent).toContain('sales@supplier2.com');
    expect(compiled.textContent).toContain('orders@unknown.com');
    expect(compiled.textContent).toContain('billing@supplier3.com');
    expect(compiled.textContent).toContain('promo@spam.com');
  });

  it('should show a translated error state when loading stats fails', () => {
    fixture.detectChanges();

    const statsReq = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq.request.method).toBe('GET');
    statsReq.flush('Server Error', { status: 500, statusText: 'Internal Server Error' });

    const emailsReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq.request.method).toBe('GET');
    emailsReq.flush({ items: [], next_cursor: null });

    fixture.detectChanges();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBe(enCatalog.ingestion.dashboard.error.generic);

    const compiled = fixture.nativeElement as HTMLElement;
    const errorBanner = compiled.querySelector('.error-banner');
    expect(errorBanner).toBeTruthy();
    expect(compiled.textContent).toContain(enCatalog.ingestion.dashboard.error.title);
    expect(compiled.textContent).toContain(enCatalog.ingestion.dashboard.error.generic);
  });

  it('should retry loading data when the retry button is clicked', () => {
    fixture.detectChanges();

    const statsReq1 = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq1.request.method).toBe('GET');
    statsReq1.flush('Server Error', { status: 500, statusText: 'Internal Server Error' });

    const emailsReq1 = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq1.request.method).toBe('GET');
    emailsReq1.flush({ items: [], next_cursor: null });

    fixture.detectChanges();
    expect(component.errorMessage()).toBeTruthy();

    const retryBtn = fixture.nativeElement.querySelector('.retry-btn') as HTMLButtonElement;
    expect(retryBtn).toBeTruthy();
    retryBtn.click();

    const statsReq2 = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq2.request.method).toBe('GET');
    statsReq2.flush(mockStats);

    const emailsReq2 = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq2.request.method).toBe('GET');
    emailsReq2.flush({ items: mockRecentEmails, next_cursor: null });

    fixture.detectChanges();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBeNull();
    expect(component.stats()).toEqual(mockStats);
  });

  it('should contain links to all four sub-pages with correct routerLink values', () => {
    fixture.detectChanges();

    const statsReq = httpTestingController.expectOne('/api/v1/ingestion/stats');
    expect(statsReq.request.method).toBe('GET');
    statsReq.flush(mockStats);

    const emailsReq = httpTestingController.expectOne('/api/v1/ingestion/emails?limit=5');
    expect(emailsReq.request.method).toBe('GET');
    emailsReq.flush({ items: mockRecentEmails, next_cursor: null });

    fixture.detectChanges();

    const links = Array.from(
      fixture.nativeElement.querySelectorAll('a'),
    ) as HTMLAnchorElement[];
    const routerLinks = links.map(
      (a) => a.getAttribute('routerLink') ?? a.getAttribute('href'),
    );

    expect(routerLinks).toContain('/ingestion/email-config');
    expect(routerLinks).toContain('/ingestion/email-log');
    expect(routerLinks).toContain('/ingestion/capture');
    expect(routerLinks).toContain('/ingestion/catalogue-import');
  });

  it('should return correct CSS classes for email statuses', () => {
    expect(component.getEmailStatusClass('completed')).toBe('status-completed');
    expect(component.getEmailStatusClass('processing')).toBe('status-processing');
    expect(component.getEmailStatusClass('received')).toBe('status-received');
    expect(component.getEmailStatusClass('failed')).toBe('status-failed');
    expect(component.getEmailStatusClass('duplicate')).toBe('status-duplicate');
    expect(component.getEmailStatusClass('rejected')).toBe('status-rejected');
  });

  it('should format rate values and percentages correctly', () => {
    expect(component.formatRate(0.85)).toBe('85%');
    expect(component.formatRate(1.0)).toBe('100%');
    expect(component.formatRate(0.0)).toBe('0%');
    expect(component.formatRate(null)).toBe('0%');
    expect(component.formatRate(undefined)).toBe('0%');
    expect(component.formatRate(NaN)).toBe('0%');

    expect(component.getRatePercent(0.85)).toBe(85);
    expect(component.getRatePercent(1.5)).toBe(100);
    expect(component.getRatePercent(-0.2)).toBe(0);
    expect(component.getRatePercent(null)).toBe(0);
    expect(component.getRatePercent(undefined)).toBe(0);
    expect(component.getRatePercent(NaN)).toBe(0);
  });
});
