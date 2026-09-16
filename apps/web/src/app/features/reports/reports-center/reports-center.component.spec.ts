import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import type { ReportArtifact, ReportSchedule } from './reports-api';
import { ReportsCenterComponent } from './reports-center.component';

describe('ReportsCenterComponent', () => {
  let component: ReportsCenterComponent;
  let fixture: ComponentFixture<ReportsCenterComponent>;
  let httpTestingController: HttpTestingController;

  const mockArtifacts: ReportArtifact[] = [
    {
      id: 'art-001',
      schedule_id: 'sch-001',
      kind: 'savings_ledger',
      format: 'csv',
      status: 'completed',
      filters: {
        period_start: '2026-08-01',
        period_end: '2026-08-31',
        supplier_id: null,
        branch_id: null,
      },
      locale: 'en',
      row_count: 142,
      rule_version: 'v1.2.0',
      download_url: 'https://storage.example.com/art-001.csv',
      expires_at: '2026-09-30T23:59:59Z',
      error: null,
      created_at: '2026-09-01T02:00:00Z',
      started_at: '2026-09-01T02:00:01Z',
      completed_at: '2026-09-01T02:00:08Z',
    },
    {
      id: 'art-002',
      schedule_id: null,
      kind: 'spend_by_supplier',
      format: 'xlsx',
      status: 'failed',
      filters: {
        period_start: '2026-07-01',
        period_end: '2026-07-31',
        supplier_id: 'supp-123',
        branch_id: null,
      },
      locale: 'ar',
      row_count: null,
      rule_version: 'v1.2.0',
      download_url: null,
      expires_at: null,
      error: 'Data export worker failed due to timeout',
      created_at: '2026-09-02T10:15:00Z',
      started_at: '2026-09-02T10:15:01Z',
      completed_at: null,
    },
    {
      id: 'art-003',
      schedule_id: null,
      kind: 'alerts_summary',
      format: 'pdf',
      status: 'queued',
      filters: {
        period_start: '2026-08-15',
        period_end: '2026-08-22',
        supplier_id: null,
        branch_id: null,
      },
      locale: 'en',
      row_count: null,
      rule_version: 'v1.2.0',
      download_url: null,
      expires_at: null,
      error: null,
      created_at: '2026-09-03T08:00:00Z',
      started_at: null,
      completed_at: null,
    },
  ];

  const mockSchedules: ReportSchedule[] = [
    {
      id: 'sch-001',
      kind: 'savings_ledger',
      format: 'csv',
      weekday: 1,
      filters: {
        supplier_id: null,
        branch_id: null,
      },
      locale: 'en',
      status: 'active',
      is_active: true,
      next_run_at: '2026-09-15T02:00:00Z',
      last_run_at: '2026-09-08T02:00:00Z',
      rule_version: 'v1.2.0',
      created_at: '2026-08-01T10:00:00Z',
      updated_at: '2026-08-01T12:00:00Z',
    },
    {
      id: 'sch-002',
      kind: 'alerts_summary',
      format: 'pdf',
      weekday: 4,
      filters: {
        supplier_id: null,
        branch_id: 'branch-456',
      },
      locale: 'ar',
      status: 'paused',
      is_active: false,
      next_run_at: '2026-09-18T05:00:00Z',
      last_run_at: null,
      rule_version: '',
      created_at: '2026-08-15T09:30:00Z',
      updated_at: '2026-09-01T14:00:00Z',
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ReportsCenterComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
      ],
    }).compileComponents();

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ReportsCenterComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should load artifacts and schedules on init', () => {
    fixture.detectChanges();

    const artifactsReq = httpTestingController.expectOne('/api/v1/reports/artifacts?limit=50');
    expect(artifactsReq.request.method).toBe('GET');
    artifactsReq.flush({ items: mockArtifacts, next_cursor: 'art-cursor-1' });

    const schedulesReq = httpTestingController.expectOne('/api/v1/reports/schedules?limit=50');
    expect(schedulesReq.request.method).toBe('GET');
    schedulesReq.flush({ items: mockSchedules, next_cursor: 'sch-cursor-1' });

    expect(component.isLoadingArtifacts()).toBeFalse();
    expect(component.artifacts().length).toBe(3);
    expect(component.artifactsNextCursor()).toBe('art-cursor-1');

    expect(component.isLoadingSchedules()).toBeFalse();
    expect(component.schedules().length).toBe(2);
    expect(component.schedulesNextCursor()).toBe('sch-cursor-1');
  });

  it('should handle cursor pagination for artifacts', () => {
    fixture.detectChanges();

    httpTestingController
      .expectOne('/api/v1/reports/artifacts?limit=50')
      .flush({ items: mockArtifacts, next_cursor: 'art-cursor-1' });
    httpTestingController
      .expectOne('/api/v1/reports/schedules?limit=50')
      .flush({ items: mockSchedules, next_cursor: null });

    const nextArtifact: ReportArtifact = {
      ...mockArtifacts[0],
      id: 'art-004',
      created_at: '2026-08-25T00:00:00Z',
    };

    component.loadMoreArtifacts();
    expect(component.isLoadingMoreArtifacts()).toBeTrue();

    const loadMoreReq = httpTestingController.expectOne(
      '/api/v1/reports/artifacts?cursor=art-cursor-1&limit=50',
    );
    expect(loadMoreReq.request.method).toBe('GET');
    loadMoreReq.flush({ items: [nextArtifact], next_cursor: null });

    expect(component.isLoadingMoreArtifacts()).toBeFalse();
    expect(component.artifacts().length).toBe(4);
    expect(component.artifactsNextCursor()).toBeNull();
  });

  it('should handle cursor pagination for schedules', () => {
    fixture.detectChanges();

    httpTestingController
      .expectOne('/api/v1/reports/artifacts?limit=50')
      .flush({ items: mockArtifacts, next_cursor: null });
    httpTestingController
      .expectOne('/api/v1/reports/schedules?limit=50')
      .flush({ items: mockSchedules, next_cursor: 'sch-cursor-1' });

    const nextSchedule: ReportSchedule = {
      ...mockSchedules[0],
      id: 'sch-003',
      created_at: '2026-08-20T00:00:00Z',
    };

    component.loadMoreSchedules();
    expect(component.isLoadingMoreSchedules()).toBeTrue();

    const loadMoreReq = httpTestingController.expectOne(
      '/api/v1/reports/schedules?cursor=sch-cursor-1&limit=50',
    );
    expect(loadMoreReq.request.method).toBe('GET');
    loadMoreReq.flush({ items: [nextSchedule], next_cursor: null });

    expect(component.isLoadingMoreSchedules()).toBeFalse();
    expect(component.schedules().length).toBe(3);
    expect(component.schedulesNextCursor()).toBeNull();
  });

  it('should apply filters and reload artifacts', () => {
    fixture.detectChanges();

    httpTestingController
      .expectOne('/api/v1/reports/artifacts?limit=50')
      .flush({ items: mockArtifacts, next_cursor: null });
    httpTestingController
      .expectOne('/api/v1/reports/schedules?limit=50')
      .flush({ items: mockSchedules, next_cursor: null });

    component.selectedKind.set('savings_ledger');
    component.selectedStatus.set('completed');
    component.onFilterChange();

    const filteredReq = httpTestingController.expectOne(
      '/api/v1/reports/artifacts?limit=50&kind=savings_ledger&status=completed',
    );
    filteredReq.flush({ items: [mockArtifacts[0]], next_cursor: null });

    expect(component.artifacts().length).toBe(1);
    expect(component.artifacts()[0].id).toBe('art-001');

    component.clearFilters();
    expect(component.selectedKind()).toBe('all');
    expect(component.selectedStatus()).toBe('all');

    const resetReq = httpTestingController.expectOne('/api/v1/reports/artifacts?limit=50');
    resetReq.flush({ items: mockArtifacts, next_cursor: null });
    expect(component.artifacts().length).toBe(3);
  });

  it('should display error message and trace ID on artifact loading failure', () => {
    fixture.detectChanges();

    httpTestingController
      .expectOne('/api/v1/reports/artifacts?limit=50')
      .flush(
        { message: 'Tenant storage unavailable', trace_id: 'trace-xyz-123' },
        { status: 500, statusText: 'Internal Server Error' },
      );
    httpTestingController
      .expectOne('/api/v1/reports/schedules?limit=50')
      .flush({ items: mockSchedules, next_cursor: null });

    expect(component.isLoadingArtifacts()).toBeFalse();
    expect(component.artifactsErrorMessage()).toBe('Tenant storage unavailable');
    expect(component.artifactsErrorTraceId()).toBe('trace-xyz-123');
  });

  it('should display error message on schedule loading failure', () => {
    fixture.detectChanges();

    httpTestingController
      .expectOne('/api/v1/reports/artifacts?limit=50')
      .flush({ items: mockArtifacts, next_cursor: null });
    httpTestingController
      .expectOne('/api/v1/reports/schedules?limit=50')
      .flush(
        { message: 'Database query timeout', trace_id: 'trace-sch-999' },
        { status: 504, statusText: 'Gateway Timeout' },
      );

    expect(component.isLoadingSchedules()).toBeFalse();
    expect(component.schedulesErrorMessage()).toBe('Database query timeout');
    expect(component.schedulesErrorTraceId()).toBe('trace-sch-999');
  });

  it('should return correct CSS classes for artifact and schedule statuses', () => {
    expect(component.getArtifactStatusClass('completed')).toBe('status-completed');
    expect(component.getArtifactStatusClass('running')).toBe('status-running');
    expect(component.getArtifactStatusClass('queued')).toBe('status-queued');
    expect(component.getArtifactStatusClass('failed')).toBe('status-failed');
    expect(component.getArtifactStatusClass('expired')).toBe('status-expired');

    expect(component.getScheduleStatusClass(mockSchedules[0])).toBe('status-active');
    expect(component.getScheduleStatusKey(mockSchedules[0])).toBe('reports.statuses.active');

    expect(component.getScheduleStatusClass(mockSchedules[1])).toBe('status-paused');
    expect(component.getScheduleStatusKey(mockSchedules[1])).toBe('reports.statuses.paused');
  });

  it('should format period and weekday keys properly', () => {
    expect(component.formatPeriod({ period_start: '2026-01-01', period_end: '2026-01-31' })).toBe(
      '2026-01-01 → 2026-01-31',
    );
    expect(component.formatPeriod({ period_start: '2026-01-01', period_end: null })).toBe(
      '≥ 2026-01-01',
    );
    expect(component.formatPeriod({ period_start: null, period_end: '2026-01-31' })).toBe(
      '≤ 2026-01-31',
    );
    expect(component.formatPeriod({})).toBe('—');

    expect(component.getWeekdayKey(0)).toBe('reports.weekdays.0');
    expect(component.getWeekdayKey(6)).toBe('reports.weekdays.6');
  });
});
