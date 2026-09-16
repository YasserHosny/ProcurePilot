import { signal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ExportSavingsComponent } from './export-savings.component';
import { type ExportJob, ExportsApiService } from '../exports-api';

describe('ExportSavingsComponent (T040)', () => {
  let component: ExportSavingsComponent;
  let fixture: ComponentFixture<ExportSavingsComponent>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockExportsApiService: jasmine.SpyObj<ExportsApiService>;
  let mockSessionService: Record<string, unknown>;

  const queuedJob: ExportJob = {
    id: 'job-1',
    kind: 'savings_ledger',
    format: 'xlsx',
    filters: {
      period_start: '2026-01-01',
      period_end: '2026-08-21',
      supplier_id: null,
    },
    status: 'queued',
    created_at: '2026-08-21T12:00:00Z',
  };

  const runningJob: ExportJob = {
    ...queuedJob,
    status: 'running',
    started_at: '2026-08-21T12:00:01Z',
  };

  const completedJob: ExportJob = {
    ...queuedJob,
    status: 'completed',
    row_count: 5,
    download_url: 'https://storage.supabase.co/exports/tenant/savings/job-1.xlsx',
    started_at: '2026-08-21T12:00:01Z',
    completed_at: '2026-08-21T12:00:05Z',
  };

  const completedEmptyJob: ExportJob = {
    ...queuedJob,
    status: 'completed',
    row_count: 0,
    download_url: 'https://storage.supabase.co/exports/tenant/savings/job-1.xlsx',
    started_at: '2026-08-21T12:00:01Z',
    completed_at: '2026-08-21T12:00:05Z',
  };

  beforeEach(async () => {
    mockApiService = jasmine.createSpyObj<ApiService>('ApiService', ['suppliers', 'listBranches']);
    mockExportsApiService = jasmine.createSpyObj<ExportsApiService>('ExportsApiService', [
      'createExport',
      'getExportJob',
    ]);
    mockSessionService = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    mockApiService.suppliers.and.returnValue(
      of({ items: [{ id: 'supp-1', name: 'Supplier A', status: 'active' as const, created_at: '' }], next_cursor: null }),
    );
    mockApiService.listBranches.and.returnValue(
      of({ items: [], total: 0, next_cursor: null }),
    );

    await TestBed.configureTestingModule({
      imports: [ExportSavingsComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideRouter([
          { path: 'savings/export/:id', component: ExportSavingsComponent },
          { path: 'savings/export', component: ExportSavingsComponent },
        ]),
        { provide: ApiService, useValue: mockApiService },
        { provide: ExportsApiService, useValue: mockExportsApiService },
        { provide: SessionService, useValue: mockSessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of(convertToParamMap({})),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ExportSavingsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and initialize in idle state with format and date defaults', () => {
    expect(component).toBeTruthy();
    expect(component.uiState()).toBe('idle');
    expect(component.form.get('format')?.value).toBe('xlsx');
    expect(component.form.get('period_start')?.value).toBeTruthy();
    expect(component.form.get('period_end')?.value).toBeTruthy();
  });

  it('should validate invalid date range (start > end)', () => {
    component.form.patchValue({
      period_start: new Date('2026-12-31'),
      period_end: new Date('2026-01-01'),
    });

    component.submitExport();

    expect(component.errorMessage()).toBeTruthy();
    expect(mockExportsApiService.createExport).not.toHaveBeenCalled();
  });

  it('should submit export request, transition to queued state and poll to completion', fakeAsync(() => {
    mockExportsApiService.createExport.and.returnValue(of(queuedJob));
    mockExportsApiService.getExportJob.and.returnValues(
      of(runningJob),
      of(completedJob),
    );

    component.form.patchValue({
      format: 'xlsx',
      period_start: new Date('2026-01-01'),
      period_end: new Date('2026-08-21'),
    });

    component.submitExport();

    expect(mockExportsApiService.createExport).toHaveBeenCalledWith({
      kind: 'savings_ledger',
      format: 'xlsx',
      filters: {
        period_start: '2026-01-01',
        period_end: '2026-08-21',
        supplier_id: null,
      },
    });

    expect(component.uiState()).toBe('queued');

    // Advance 1500ms for first poll -> running
    tick(1500);
    expect(component.uiState()).toBe('running');

    // Advance 1500ms for second poll -> completed
    tick(1500);
    expect(component.uiState()).toBe('completed');
    expect(component.currentJob()?.download_url).toBe(completedJob.download_url);
    expect(component.currentJob()?.row_count).toBe(5);
  }));

  it('should handle completed empty result with row_count = 0', fakeAsync(() => {
    mockExportsApiService.createExport.and.returnValue(of(queuedJob));
    mockExportsApiService.getExportJob.and.returnValue(of(completedEmptyJob));

    component.submitExport();
    tick(1500);

    expect(component.uiState()).toBe('completed_empty');
  }));

  it('should handle failed job state', fakeAsync(() => {
    const failedJob: ExportJob = {
      ...queuedJob,
      status: 'failed',
      error: { message: 'Render failed' },
    };

    mockExportsApiService.createExport.and.returnValue(of(queuedJob));
    mockExportsApiService.getExportJob.and.returnValue(of(failedJob));

    component.submitExport();
    tick(1500);

    expect(component.uiState()).toBe('failed');
  }));

  it('should reset export back to idle form', () => {
    component.currentJob.set(completedJob);
    expect(component.uiState()).toBe('completed');

    component.resetExport();
    expect(component.uiState()).toBe('idle');
    expect(component.currentJob()).toBeNull();
  });
});
