import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { By } from '@angular/platform-browser';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { MatchTask, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ResolutionQueueComponent } from './resolution-queue.component';

describe('ResolutionQueueComponent', () => {
  let component: ResolutionQueueComponent;
  let fixture: ComponentFixture<ResolutionQueueComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockTasks: MatchTask[] = [
    {
      id: 'task-1',
      quotation_id: 'q-101',
      quotation_line: {
        id: 'line-101',
        line_number: 1,
        original_text: 'Organic Whole Milk 2L',
        quantity: '10',
        unit_price: { amount: '2.5000', currency: 'GBP' },
      },
      status: 'open',
      priority: 'high',
      reason: 'low_confidence',
      supplier_name: 'Fresh Farms Dairy',
      candidates: [
        {
          id: 'cand-1',
          quotation_line_id: 'line-101',
          candidate_product: {
            id: 'prod-1',
            tenant_name: 'Organic Whole Milk 2L',
            canonical_name: 'Organic Whole Milk',
            base_unit: 'litre',
            status: 'active',
          },
          confidence: '0.7800',
          reasons: {
            alias_hit: false,
            gtin_match: false,
            supplier_code_match: false,
            lexical_similarity: '0.8500',
            semantic_similarity: '0.7200',
            feature_score: {
              brand_match: '1.0000',
              variant_match: '1.0000',
              pack_unit_match: '1.0000',
              pack_size_plausibility: '1.0000',
              price_plausibility: '0.9000',
            },
          },
          rank: 1,
          scoring_version: 'v1.0',
          created_at: '2026-08-21T01:00:00Z',
        },
      ],
      created_at: '2026-08-21T01:00:00Z',
    },
    {
      id: 'task-2',
      quotation_id: 'q-102',
      quotation_line: {
        id: 'line-102',
        line_number: 2,
        original_text: 'Cheddar Cheese Block 500g',
        quantity: '5',
        unit_price: { amount: '4.0000', currency: 'GBP' },
      },
      status: 'open',
      priority: 'normal',
      reason: 'close_candidates',
      supplier_name: 'Somerset Cheese Co',
      candidates: [],
      created_at: '2026-08-21T01:30:00Z',
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['getMatchTasks']);
    apiService.getMatchTasks.and.returnValue(of({ items: mockTasks, next_cursor: 'cursor-123' }));

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    await TestBed.configureTestingModule({
      imports: [ResolutionQueueComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(ResolutionQueueComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load open match tasks on init with full query parity', () => {
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: 'open',
      priority: undefined,
      reason: undefined,
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
    expect(component.tasks().length).toBe(2);
    expect(component.nextCursor()).toBe('cursor-123');
    expect(component.isLoading()).toBeFalse();
  });

  it('should reload tasks when search query changes with debounce', fakeAsync(() => {
    component.onSearchChange('cheddar');
    expect(apiService.getMatchTasks).toHaveBeenCalledTimes(1); // not yet called

    tick(300);

    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        search: 'cheddar',
      }),
    );
  }));

  it('should reload tasks when date_from and date_to change', () => {
    component.onDateFromChange('2026-08-01');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        date_from: '2026-08-01',
      }),
    );

    component.onDateToChange('2026-08-31');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        date_to: '2026-08-31',
      }),
    );
  });

  it('should reload tasks on onSortChange', () => {
    component.onSortChange({ active: 'priority', direction: 'asc' });
    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        sort_by: 'priority',
        sort_order: 'asc',
      }),
    );
  });

  it('should load more tasks when loadMore is called', () => {
    const extraTask: MatchTask = {
      ...mockTasks[0],
      id: 'task-3',
      quotation_id: 'q-103',
      quotation_line: {
        ...mockTasks[0].quotation_line,
        id: 'line-103',
      },
    };
    apiService.getMatchTasks.and.returnValue(of({ items: [extraTask], next_cursor: null }));

    component.loadMore();

    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        cursor: 'cursor-123',
      }),
    );
    expect(component.tasks().length).toBe(3);
    expect(component.nextCursor()).toBeNull();
  });

  it('should detect active filters and clear them', () => {
    expect(component.hasActiveFilters()).toBeFalse();

    component.statusFilter.set('resolved');
    expect(component.hasActiveFilters()).toBeTrue();

    component.clearFilters();
    expect(component.statusFilter()).toBe('open');
    expect(component.priorityFilter()).toBe('all');
    expect(component.reasonFilter()).toBe('all');
    expect(component.searchQuery()).toBe('');
    expect(component.dateFrom()).toBeNull();
    expect(component.dateTo()).toBeNull();
    expect(component.hasActiveFilters()).toBeFalse();
  });

  it('should calculate relative age correctly', () => {
    const now = new Date();
    expect(component.ageLabel(now.toISOString())).toBe('just now');

    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);
    expect(component.ageLabel(twoHoursAgo.toISOString())).toBe('2h ago');

    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    expect(component.ageLabel(threeDaysAgo.toISOString())).toBe('3d ago');
  });

  it('should render supplier name, unit price, and clickable rows', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    // Check table headers
    const text = compiled.textContent || '';
    expect(text).toContain('Supplier');
    expect(text).toContain('Unit Price');
    expect(text).toContain('Age');

    // Check supplier name in table body
    expect(text).toContain('Fresh Farms Dairy');
    expect(text).toContain('Somerset Cheese Co');

    // Check clickable row
    const rows = compiled.querySelectorAll('tr.clickable-row');
    expect(rows.length).toBe(2);
  });

  it('should show filtered empty state with clear filters button', () => {
    component.tasks.set([]);
    component.statusFilter.set('resolved');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.clear-filters-btn')).toBeTruthy();
  });

  it('should handle error when loading tasks fails', () => {
    const errorResponse = new HttpErrorResponse({
      status: 500,
      error: { message: 'Failed to fetch tasks', trace_id: 'tr-err-1' },
    });
    apiService.getMatchTasks.and.returnValue(throwError(() => errorResponse));

    component.loadTasks();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBe('Failed to fetch tasks');
    expect(component.errorTraceId()).toBe('tr-err-1');
  });
});
