import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { Subject, firstValueFrom, of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { CatalogueRefreshReview, MatchQueueItem, MatchTask, MatchTaskReason, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ResolutionQueueComponent } from './resolution-queue.component';

describe('ResolutionQueueComponent', () => {
  let component: ResolutionQueueComponent;
  let fixture: ComponentFixture<ResolutionQueueComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let mockSession: {
    hasRole: jasmine.Spy;
    role: ReturnType<typeof signal<Role | null>>;
    currentMember: ReturnType<typeof signal<unknown>>;
    isAuthenticated: ReturnType<typeof signal<boolean>>;
    tenant: ReturnType<typeof signal<unknown>>;
    activeLocale: ReturnType<typeof signal<string>>;
  };

  const mockTasks: MatchTask[] = [
    {
      id: 'task-1',
      quotation_id: 'q-101',
      quotation: {
        id: 'q-101',
        status: 'reviewed',
        source_filename: 'fresh-farms.pdf',
        reviewed_by_email: 'buyer@example.com',
        reviewed_at: '2026-08-21T00:30:00Z',
        issue_date: '2026-08-20',
        line_count: 2,
        open_match_task_count: 2,
        supplier_name: 'Fresh Farms Dairy',
      },
      quotation_line: {
        id: 'line-101',
        line_number: 1,
        original_text: 'Organic Whole Milk 2L',
        quantity: '10',
        unit_price: { amount: '2.5000', currency: 'GBP' },
        quoted_line_total: { amount: '30.0000', currency: 'GBP' },
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
      quotation: {
        id: 'q-102',
        status: 'reviewed',
        source_filename: 'somerset.pdf',
        line_count: 1,
        open_match_task_count: 1,
        supplier_name: 'Somerset Cheese Co',
      },
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

  const mockRefreshReview: CatalogueRefreshReview = {
    id: 'refresh-1',
    refresh_schedule_id: 'schedule-1',
    source_import_id: 'import-1',
    supplier_id: 'supplier-1',
    status: 'pending_review',
    normalized_rows: [
      {
        product_name: 'A4 paper',
        unit_price_amount: '12.5000',
        unit_price_currency: 'GBP',
        base_unit: 'box',
      },
    ],
    errors: [],
    row_count: 1,
    error_count: 0,
    created_at: '2026-08-21T01:00:00Z',
    source_file_name: 'prices.csv',
    source_file_format: 'csv',
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'getMatchTasks',
      'getMatchTaskForLine',
      'correctMatch',
      'getExactMatchCount',
      'confirmExactMatches',
      'listCatalogueRefreshReviews',
      'approveCatalogueRefreshReview',
      'rejectCatalogueRefreshReview',
      'baseUnits',
    ]);
    apiService.baseUnits.and.returnValue(
      of({ items: [{ code: 'litre', label_en: 'Litre', label_ar: 'لتر', dimension: 'volume' }] }),
    );
    apiService.getMatchTasks.and.returnValue(of({ items: mockTasks, next_cursor: 'cursor-123' }));
    apiService.listCatalogueRefreshReviews.and.returnValue(of({ items: [], next_cursor: null }));
    apiService.getExactMatchCount.and.returnValue(of({ count: 3 }));
    apiService.confirmExactMatches.and.returnValue(of({ confirmed: 3, skipped: 0 }));

    mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    await TestBed.configureTestingModule({
      imports: [ResolutionQueueComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    await firstValueFrom(translate.use('en'));

    fixture = TestBed.createComponent(ResolutionQueueComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load open match tasks on init with full query parity', () => {
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: 'open',
      priority: undefined,
      reason: undefined,
      quotation_id: undefined,
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
    expect(component.tasks().length).toBe(2);
    expect(component.nextCursor()).toBe('cursor-123');
    expect(component.isLoading()).toBeFalse();
    expect(component.groups().length).toBe(2);
  });

  it('should remove an approved catalogue refresh review from the pending section', () => {
    apiService.approveCatalogueRefreshReview.and.returnValue(
      of({ review_id: mockRefreshReview.id, status: 'approved', imported_rows: 1, error_rows: 0 }),
    );
    component.refreshReviews.set([mockRefreshReview]);

    component.decideRefreshReview(mockRefreshReview, 'approve');

    expect(apiService.approveCatalogueRefreshReview).toHaveBeenCalledWith(mockRefreshReview.id);
    expect(component.refreshReviews()).toEqual([]);
  });

  it('offers a one-click bulk confirm for exact name matches and reloads afterwards', () => {
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-testid="exact-match-banner"]')?.textContent).toContain(
      '3 exact name matches',
    );
    apiService.getExactMatchCount.and.returnValue(of({ count: 0 }));
    (el.querySelector('[data-testid="confirm-exact-btn"]') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(apiService.confirmExactMatches).toHaveBeenCalledTimes(1);
    expect(apiService.confirmExactMatches).toHaveBeenCalledWith(jasmine.stringMatching(/^[0-9a-f-]{36}$/));
    expect(apiService.getMatchTasks).toHaveBeenCalledTimes(2);
    expect(el.querySelector('[data-testid="exact-match-banner"]')).toBeNull();
    expect(el.querySelector('[data-testid="exact-match-result"]')?.textContent).toContain(
      '3 matches confirmed',
    );
  });

  it('tells the buyer when exact matches were skipped instead of hiding it', () => {
    apiService.confirmExactMatches.and.returnValue(of({ confirmed: 1, skipped: 2 }));
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    (el.querySelector('[data-testid="confirm-exact-btn"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(el.querySelector('[data-testid="exact-match-skipped"]')?.textContent).toContain(
      '2 could not be confirmed',
    );
  });

  it('should send all status explicitly so auto-matched rows stay in quotation groups', () => {
    component.onStatusChange('all');

    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({ status: 'all' }),
    );
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

  it('should ignore stale loadTasks responses when filters change quickly', () => {
    const openTask = mockTasks[0];
    const resolvedTask: MatchTask = {
      ...mockTasks[1],
      id: 'task-resolved',
      status: 'resolved',
    };
    const openResponse = new Subject<{ items: MatchTask[]; next_cursor: string | null }>();
    const resolvedResponse = new Subject<{ items: MatchTask[]; next_cursor: string | null }>();
    apiService.getMatchTasks.and.returnValues(
      openResponse.asObservable(),
      resolvedResponse.asObservable(),
    );

    component.loadTasks();
    component.onStatusChange('resolved');

    resolvedResponse.next({ items: [resolvedTask], next_cursor: null });
    resolvedResponse.complete();
    openResponse.next({ items: [openTask], next_cursor: 'open-cursor' });
    openResponse.complete();

    expect(component.statusFilter()).toBe('resolved');
    expect(component.tasks()).toEqual([resolvedTask]);
    expect(component.nextCursor()).toBeNull();
    expect(component.isLoading()).toBeFalse();
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

  it('should ignore stale loadMore responses after filters change', () => {
    const extraTask: MatchTask = {
      ...mockTasks[0],
      id: 'task-extra-open',
      quotation_id: 'q-extra-open',
      quotation_line: {
        ...mockTasks[0].quotation_line,
        id: 'line-extra-open',
      },
    };
    const resolvedTask: MatchTask = {
      ...mockTasks[1],
      id: 'task-resolved',
      status: 'resolved',
    };
    const loadMoreResponse = new Subject<{ items: MatchTask[]; next_cursor: string | null }>();
    const resolvedResponse = new Subject<{ items: MatchTask[]; next_cursor: string | null }>();
    apiService.getMatchTasks.and.returnValues(
      loadMoreResponse.asObservable(),
      resolvedResponse.asObservable(),
    );

    component.loadMore();
    component.onStatusChange('resolved');

    resolvedResponse.next({ items: [resolvedTask], next_cursor: null });
    resolvedResponse.complete();
    loadMoreResponse.next({ items: [extraTask], next_cursor: 'stale-cursor' });
    loadMoreResponse.complete();

    expect(component.statusFilter()).toBe('resolved');
    expect(component.tasks()).toEqual([resolvedTask]);
    expect(component.nextCursor()).toBeNull();
    expect(component.isLoadingMore()).toBeFalse();
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

  it('accepts a typed day-first date, shows day-first format, and produces ISO date in filter query', () => {
    const inputs = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLInputElement>('.date-field input[matinput]');
    expect(inputs.length).toBe(2);
    const dateFromInput = inputs[0];

    dateFromInput.value = '';
    for (const char of '22/10/2026') {
      dateFromInput.value += char;
      dateFromInput.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    dateFromInput.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    expect(component.dateFrom()).toBe('2026-10-22');
    expect(dateFromInput.value).toBe('22/10/2026');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        date_from: '2026-10-22',
      }),
    );
  });

  it('should calculate relative age correctly', () => {
    const now = new Date();
    expect(component.ageLabel(now.toISOString())).toBe('just now');

    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);
    expect(component.ageLabel(twoHoursAgo.toISOString())).toBe('2h ago');

    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    expect(component.ageLabel(threeDaysAgo.toISOString())).toBe('3d ago');
  });

  it('should render grouped quotation evidence and explicit line actions', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const text = compiled.textContent || '';
    expect(text).toContain('Fresh Farms Dairy');
    expect(text).toContain('Somerset Cheese Co');
    expect(text).toContain('fresh-farms.pdf');
    expect(text).toContain('buyer@example.com');
    expect(text).toContain('Quoted exposure');
    expect(text).toContain('GBP 30');

    expect(compiled.querySelectorAll('article.match-line').length).toBe(2);
    expect(compiled.querySelectorAll('a.action-btn').length).toBe(2);
    expect(compiled.querySelectorAll('tr.clickable-row').length).toBe(0);
  });

  it('should collapse and expand a quotation group from its header toggle', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const group = compiled.querySelector('.quotation-group') as HTMLElement;
    const toggle = group.querySelector('.group-toggle') as HTMLButtonElement;

    expect(toggle).toBeTruthy();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(group.querySelectorAll('article.match-line').length).toBe(1);

    toggle.click();
    fixture.detectChanges();

    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(group.querySelectorAll('article.match-line').length).toBe(0);

    toggle.click();
    fixture.detectChanges();

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(group.querySelectorAll('article.match-line').length).toBe(1);
  });

  it('should show filtered empty state with clear filters button', () => {
    component.tasks.set([]);
    component.statusFilter.set('resolved');
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.clear-filters-btn')).toBeTruthy();
  });

  it('shows "All lines of this quote are matched" empty state with a compare link to its RFQ and a clear filters link when filtered by quotation_id', () => {
    apiService.getMatchTasks.and.returnValue(of({ items: [], next_cursor: null, rfq_id: 'rfq-7' }));
    component.quotationId.set('q-101');
    component.loadTasks();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const emptyTitle = compiled.querySelector('.empty-title')?.textContent?.trim();
    expect(emptyTitle).toBe(enCatalog.matching.queue.allLinesMatchedTitle);

    const compareBtn = compiled.querySelector('a.compare-responses-btn') as HTMLAnchorElement | null;
    expect(compareBtn).toBeTruthy();
    expect(compareBtn?.textContent?.trim()).toContain(enCatalog.matching.queue.compareResponses);
    expect(compareBtn?.getAttribute('href')).toBe('/rfq/compare/rfq-7');

    const clearBtn = compiled.querySelector('.clear-filters-btn') as HTMLButtonElement | null;
    expect(clearBtn).toBeTruthy();

    clearBtn?.click();
    expect(component.quotationId()).toBeNull();
  });

  it('offers no compare link when the quotation did not answer an RFQ', () => {
    apiService.getMatchTasks.and.returnValue(of({ items: [], next_cursor: null, rfq_id: null }));
    component.quotationId.set('q-101');
    component.loadTasks();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="quotation-all-matched"]')).toBeTruthy();
    expect(compiled.querySelector('a.compare-responses-btn')).toBeNull();
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

  describe('failed loads (P-153, PPS-197)', () => {
    const failLoad = (): void => {
      apiService.getMatchTasks.and.returnValue(
        throwError(
          () => new HttpErrorResponse({ status: 503, error: { message: 'busy', trace_id: 'tr-1' } }),
        ),
      );
      component.loadTasks();
      fixture.detectChanges();
    };

    it('does not claim every line is matched when the load failed for a quotation', () => {
      component.quotationId.set('q-101');
      component.tasks.set([]);
      failLoad();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('[data-testid="quotation-all-matched"]')).toBeNull();
      expect(compiled.querySelector('.error-banner')?.textContent).toContain('busy');
    });

    it('drops the previous rows instead of showing them under the error', () => {
      expect(component.tasks().length).toBe(2);
      failLoad();

      expect(component.tasks().length).toBe(0);
      expect((fixture.nativeElement as HTMLElement).querySelector('.match-line')).toBeNull();
    });

    it('does not offer the task Retry for an unrelated loader error', () => {
      apiService.listCatalogueRefreshReviews.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 503, error: { message: 'reviews down' } })),
      );
      component.loadRefreshReviews();
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.querySelector('.error-banner')?.textContent).toContain('reviews down');
      expect(compiled.querySelector('[data-testid="queue-retry"]')).toBeNull();
    });

    it('still says every line is matched when only the refresh-review load failed', () => {
      component.quotationId.set('q-101');
      component.tasks.set([]);
      apiService.listCatalogueRefreshReviews.and.returnValue(
        throwError(() => new HttpErrorResponse({ status: 503, error: { message: 'reviews down' } })),
      );
      component.loadRefreshReviews();
      fixture.detectChanges();

      expect(
        (fixture.nativeElement as HTMLElement).querySelector('[data-testid="quotation-all-matched"]'),
      ).toBeTruthy();
    });

    it('offers a Retry in the error banner that reloads and clears the error', () => {
      failLoad();
      const retry = (fixture.nativeElement as HTMLElement).querySelector(
        '[data-testid="queue-retry"]',
      ) as HTMLButtonElement | null;
      expect(retry).withContext('retry button').toBeTruthy();

      apiService.getMatchTasks.and.returnValue(of({ items: mockTasks, next_cursor: null }));
      apiService.getMatchTasks.calls.reset();
      retry!.click();
      fixture.detectChanges();

      expect(apiService.getMatchTasks).toHaveBeenCalledTimes(1);
      expect(component.errorMessage()).toBeNull();
      expect(component.tasks().length).toBe(2);
    });
  });

  describe('screen-reader states (P-159, PPS-203)', () => {
    it('announces loading as a status', () => {
      component.isLoading.set(true);
      fixture.detectChanges();

      expect(
        (fixture.nativeElement as HTMLElement).querySelector('.loading-state')?.getAttribute('role'),
      ).toBe('status');
    });

    it('announces how many lines and quotations are shown', () => {
      const summary = (fixture.nativeElement as HTMLElement).querySelector(
        '[data-testid="queue-result-summary"]',
      );
      expect(summary?.getAttribute('role')).toBe('status');
      expect(summary?.textContent).toContain('Lines shown: 2');
      expect(summary?.textContent).toContain('Quotations: 2');
    });

    it('keeps one summary live region in the page across loads and reports zero results', () => {
      const summary = (): HTMLElement | null =>
        (fixture.nativeElement as HTMLElement).querySelector('[data-testid="queue-result-summary"]');
      const first = summary();
      expect(first).withContext('present with results').toBeTruthy();

      component.isLoading.set(true);
      fixture.detectChanges();
      expect(summary()).withContext('same element while loading').toBe(first);
      expect(summary()?.textContent?.trim()).withContext('silent while loading').toBe('');

      component.tasks.set([]);
      component.isLoading.set(false);
      fixture.detectChanges();
      expect(summary()).withContext('same element at zero results').toBe(first);
      expect(summary()?.textContent).toContain('Lines shown: 0');
    });

    it('makes the full quotation id reachable without a mouse', () => {
      const badge = (fixture.nativeElement as HTMLElement).querySelector('.quotation-badge')!;
      expect(badge.getAttribute('tabindex')).toBe('0');
      expect(badge.getAttribute('aria-label')).toContain('q-101');
    });
  });

  describe('sorting, count and reasons (P-153, PPS-197)', () => {
    const el = (): HTMLElement => fixture.nativeElement as HTMLElement;
    const openSelect = (testId: string): string[] => {
      const trigger = el().querySelector(`[data-testid="${testId}"] .mat-mdc-select-trigger`) as HTMLElement;
      expect(trigger).withContext(testId).toBeTruthy();
      trigger.click();
      fixture.detectChanges();
      return Array.from(document.querySelectorAll('.mat-mdc-option')).map((o) => o.textContent!.trim());
    };
    const pick = (label: string): void => {
      const option = Array.from(document.querySelectorAll('.mat-mdc-option')).find(
        (o) => o.textContent!.trim() === label,
      ) as HTMLElement;
      expect(option).withContext(label).toBeTruthy();
      option.click();
      fixture.detectChanges();
    };

    it('lets the buyer sort the queue and reloads with the chosen order', () => {
      const labels = openSelect('queue-sort');
      expect(labels).toContain(enCatalog.matching.queue.sort.priorityDesc);
      expect(labels).toContain(enCatalog.matching.queue.sort.createdAsc);

      apiService.getMatchTasks.calls.reset();
      pick(enCatalog.matching.queue.sort.priorityDesc);

      expect(apiService.getMatchTasks).toHaveBeenCalledWith(
        jasmine.objectContaining({ sort_by: 'priority', sort_order: 'desc' }),
      );
    });

    it('shows each line number with Arabic-Indic digits in Arabic (P-159)', () => {
      const badges = Array.from(el().querySelectorAll('.line-number-badge'));
      expect(badges.length).toBeGreaterThan(0);
      expect(badges[0].textContent).toMatch(/#[0-9]/);
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', arCatalog);
      translate.use('ar');
      fixture.detectChanges();
      for (const badge of Array.from(el().querySelectorAll('.line-number-badge'))) {
        expect(badge.textContent).toMatch(/#[٠-٩]/);
        expect(badge.textContent).not.toMatch(/[0-9]/);
      }
    });

    it('shows how many lines and quotations are listed, and that more can be loaded', () => {
      const count = el().querySelector('[data-testid="queue-result-summary"]') as HTMLElement;
      expect(count.classList.contains('visually-hidden')).withContext('visible to everyone').toBeFalse();
      expect(count.textContent).toContain('Lines shown: 2');
      expect(count.textContent).toContain(enCatalog.matching.queue.moreAvailable);

      component.nextCursor.set(null);
      fixture.detectChanges();
      expect(count.textContent).not.toContain(enCatalog.matching.queue.moreAvailable);
    });

    it('offers the routing reasons the queue can return, and not one it never returns', () => {
      const labels = openSelect('queue-reason-filter');
      expect(labels).toContain(enCatalog.matching.queue.reason.auto_accepted);
      expect(labels).toContain(enCatalog.matching.queue.reason.corrected);
      // No queue query yields «human_decided» rows, so offering it would always show an empty list.
      expect(labels).not.toContain(enCatalog.matching.queue.reason.human_decided);
    });

    it('widens the status to All when a reason that only resolved lines have is chosen under Open', () => {
      expect(component.statusFilter()).toBe('open');
      apiService.getMatchTasks.calls.reset();

      component.onReasonChange('corrected');

      expect(component.statusFilter()).toBe('all');
      expect(apiService.getMatchTasks).toHaveBeenCalledWith(
        jasmine.objectContaining({ status: 'all', reason: 'corrected' }),
      );
    });

    it('leaves the status alone for reasons that open lines have', () => {
      component.onReasonChange('low_confidence');
      expect(component.statusFilter()).toBe('open');
    });

    it('does not say every line of the quote is matched when another filter is hiding lines', () => {
      component.quotationId.set('q-101');
      component.reasonFilter.set('low_confidence');
      component.tasks.set([]);
      fixture.detectChanges();

      expect(el().querySelector('[data-testid="quotation-all-matched"]')).toBeNull();
      expect(el().querySelector('.clear-filters-btn')).toBeTruthy();
    });

    it('treats a non-default sort as an active filter and Clear restores the default order', () => {
      component.sortBy.set('priority');
      component.sortOrder.set('asc');
      expect(component.hasActiveFilters()).toBeTrue();

      component.clearFilters();

      expect(component.sortBy()).toBe('created_at');
      expect(component.sortOrder()).toBe('desc');
      expect(component.hasActiveFilters()).toBeFalse();
    });
  });

  describe('paging and refresh (P-153, PPS-197)', () => {
    it('does not list a task twice when Load more brings back one that moved between pages', () => {
      const dup = mockTasks[0] as unknown as MatchQueueItem;
      expect(component.tasks().length).toBe(2);
      apiService.getMatchTasks.and.returnValue(
        of({ items: [dup, { ...(mockTasks[1] as unknown as MatchQueueItem), id: 'task-new' }], next_cursor: null }),
      );

      component.loadMore();

      const ids = component.tasks().map((t) => t.id);
      expect(new Set(ids).size).withContext(ids.join(',')).toBe(ids.length);
      expect(ids).toContain('task-new');
    });

    it('lets the buyer refresh the list in place', () => {
      const refresh = (fixture.nativeElement as HTMLElement).querySelector(
        '[data-testid="queue-refresh"]',
      ) as HTMLButtonElement | null;
      expect(refresh).withContext('refresh button').toBeTruthy();

      apiService.getMatchTasks.calls.reset();
      refresh!.click();

      expect(apiService.getMatchTasks).toHaveBeenCalledTimes(1);
    });
  });

  describe('RFQ-aware matching in queue (spec 023 US1)', () => {
    it('shows "Correct match" button for auto-accepted line when isWriter, and hides it for non-writer', () => {
      const autoTask: MatchTask = {
        ...mockTasks[0],
        id: 'task-auto-1',
        status: 'auto_accepted',
      };
      component.tasks.set([autoTask]);
      fixture.detectChanges();

      let correctBtn = fixture.nativeElement.querySelector('.correct-match-btn') as HTMLButtonElement | null;
      expect(correctBtn).toBeTruthy();
      expect(correctBtn?.textContent).toContain('Correct match');

      mockSession.hasRole.and.returnValue(false);
      fixture.detectChanges();

      correctBtn = fixture.nativeElement.querySelector('.correct-match-btn') as HTMLButtonElement | null;
      expect(correctBtn).toBeNull();
    });

    it('displays "From your RFQ line {n}" when task has RFQ matched candidate', () => {
      const rfqTask: MatchQueueItem = {
        ...mockTasks[0],
        id: 'task-auto-rfq',
        status: 'auto_accepted',
        candidates: undefined,
        top_candidate: {
          product_name: 'Organic Whole Milk 2L',
          confidence: '0.8500',
          rfq_position: 2,
        },
      };
      component.tasks.set([rfqTask]);
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('From your RFQ line 2');
    });

    it('does not display RFQ chip when rfq_position is null', () => {
      const nonRfqTask: MatchQueueItem = {
        ...mockTasks[0],
        id: 'task-non-rfq',
        status: 'auto_accepted',
        candidates: undefined,
        top_candidate: {
          product_name: 'Organic Whole Milk 2L',
          confidence: '0.8500',
          rfq_position: null,
        },
      };
      component.tasks.set([nonRfqTask]);
      fixture.detectChanges();

      const chip = fixture.nativeElement.querySelector('.reason-chip.rfq-chip');
      expect(chip).toBeNull();
      const text = fixture.nativeElement.textContent as string;
      expect(text).not.toContain('From your RFQ line');
    });

    it('opens dialog and submits correction when Correct match is clicked', () => {
      const autoTask: MatchTask = {
        ...mockTasks[0],
        id: 'task-auto-1',
        status: 'auto_accepted',
        decision: {
          id: 'dec-1',
          quotation_line_id: 'line-101',
          matched_product: mockTasks[0].candidates[0].candidate_product,
          outcome: 'same_product',
          selected_match_candidate_id: 'cand-1',
          decided_at: '2026-08-21T01:00:00Z',
          decided_by: 'buyer@example.com',
          is_automatic: true,
          confidence: '0.8500',
        },
      };
      apiService.getMatchTaskForLine.and.returnValue(of(autoTask));
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...autoTask.decision!, id: 'dec-2' },
          superseded_decision_id: 'dec-1',
          lines_matched_through_old_wording: [],
        }),
      );

      component.tasks.set([autoTask]);
      fixture.detectChanges();

      const dialogSpy = spyOn((component as unknown as { dialog: { open: jasmine.Spy } }).dialog, 'open').and.returnValue({
        afterClosed: () => of({
          expected_current_decision_id: 'dec-1',
          outcome: 'same_product',
          selected_match_candidate_id: 'cand-2',
          learn_alias: true,
        }),
      } as never);

      component.openCorrectMatchDialog(autoTask);

      expect(apiService.getMatchTaskForLine).toHaveBeenCalledWith('line-101');
      expect(dialogSpy).toHaveBeenCalled();
      expect(apiService.correctMatch).toHaveBeenCalledWith(
        'line-101',
        jasmine.objectContaining({
          expected_current_decision_id: 'dec-1',
          selected_match_candidate_id: 'cand-2',
        }),
        jasmine.stringMatching(/^[0-9a-f-]{36}$/),
      );
    });

    describe('correction retries, notices and double clicks (P-154, PPS-198)', () => {
      let autoTask: MatchTask;
      const requestA = {
        expected_current_decision_id: 'dec-1',
        outcome: 'same_product' as const,
        selected_match_candidate_id: 'cand-2',
        new_product: null,
        learn_alias: true,
      };
      const done = (extra: Record<string, unknown> = {}) =>
        of({
          decision: { ...autoTask.decision!, id: 'dec-2' },
          superseded_decision_id: 'dec-1',
          lines_matched_through_old_wording: [],
          ...extra,
        });
      const lost = () => throwError(() => new HttpErrorResponse({ status: 503, error: { message: 'busy' } }));
      const closeWith = (request: unknown): void => {
        const dialog = (component as unknown as { dialog: { open: jasmine.Spy } }).dialog;
        dialog.open.and.returnValue({ afterClosed: () => of(request) });
      };

      beforeEach(() => {
        autoTask = {
          ...mockTasks[0],
          id: 'task-auto-1',
          status: 'auto_accepted',
          decision: {
            id: 'dec-1',
            quotation_line_id: 'line-101',
            matched_product: mockTasks[0].candidates[0].candidate_product,
            outcome: 'same_product',
            selected_match_candidate_id: 'cand-1',
            decided_at: '2026-08-21T01:00:00Z',
            decided_by: 'buyer@example.com',
            is_automatic: true,
            confidence: '0.8500',
          },
        };
        apiService.getMatchTaskForLine.and.returnValue(of(autoTask));
        spyOn((component as unknown as { dialog: { open: () => unknown } }).dialog, 'open');
      });

      it('replays the same Idempotency-Key when the same correction is retried after a failure', () => {
        apiService.correctMatch.and.returnValues(lost(), done());
        closeWith(requestA);

        component.openCorrectMatchDialog(autoTask);
        component.openCorrectMatchDialog(autoTask);

        const [first, retry] = apiService.correctMatch.calls.allArgs();
        expect(retry[2]).withContext('retry replays the key').toBe(first[2]);
      });

      it('uses a new key for a different correction', () => {
        apiService.correctMatch.and.returnValues(lost(), done());
        closeWith(requestA);
        component.openCorrectMatchDialog(autoTask);
        closeWith({ ...requestA, selected_match_candidate_id: 'cand-1' });
        component.openCorrectMatchDialog(autoTask);

        const [first, second] = apiService.correctMatch.calls.allArgs();
        expect(second[2]).not.toBe(first[2]);
      });

      it('tells the buyer about lines still matched through the old wording and about a kept alias', () => {
        apiService.correctMatch.and.returnValue(
          done({ lines_matched_through_old_wording: ['l-1', 'l-2'], alias_conflict_product_id: 'prod-9' }),
        );
        closeWith(requestA);

        component.openCorrectMatchDialog(autoTask);
        fixture.detectChanges();

        const el = fixture.nativeElement as HTMLElement;
        expect(el.querySelector('[data-testid="queue-dependent-lines-notice"]')?.textContent).toContain(
          '2 other lines were matched through the old wording',
        );
        expect(el.querySelector('[data-testid="queue-alias-conflict-notice"]')?.textContent).toContain(
          enCatalog.matching.resolution.correction.aliasConflictNotice,
        );
      });

      it('opens the dependent lines in the queue itself, not through a link that leaves the list unchanged', () => {
        apiService.correctMatch.and.returnValue(
          done({ lines_matched_through_old_wording: ['l-1'] }),
        );
        closeWith(requestA);
        component.openCorrectMatchDialog(autoTask);
        fixture.detectChanges();

        const review = (fixture.nativeElement as HTMLElement).querySelector(
          '[data-testid="queue-dependent-lines-review"]',
        ) as HTMLElement | null;
        expect(review?.tagName).toBe('BUTTON');

        apiService.getMatchTasks.calls.reset();
        review!.click();

        expect(apiService.getMatchTasks).toHaveBeenCalledWith(
          jasmine.objectContaining({ quotation_id: autoTask.quotation.id, status: 'all' }),
        );
      });

      it('ignores a second click on «Correct match» while the first is still loading', () => {
        const pending$ = new Subject<MatchTask>();
        apiService.getMatchTaskForLine.and.returnValue(pending$);

        component.openCorrectMatchDialog(autoTask);
        component.openCorrectMatchDialog(autoTask);

        expect(apiService.getMatchTaskForLine).toHaveBeenCalledTimes(1);
      });
    });

    it('passes quotationSupplierId equal to quotation.supplier_id and non-empty baseUnits when opening Correct dialog', () => {
      const autoTask: MatchTask = {
        ...mockTasks[0],
        id: 'task-auto-1',
        status: 'auto_accepted',
        quotation: {
          ...mockTasks[0].quotation,
          supplier_id: 'supplier-xyz-123',
          supplier_name: 'Fresh Farms Dairy',
        },
        decision: {
          id: 'dec-1',
          quotation_line_id: 'line-101',
          matched_product: mockTasks[0].candidates[0].candidate_product,
          outcome: 'same_product',
          selected_match_candidate_id: 'cand-1',
          decided_at: '2026-08-21T01:00:00Z',
          decided_by: 'buyer@example.com',
          is_automatic: true,
          confidence: '0.8500',
        },
      };
      apiService.getMatchTaskForLine.and.returnValue(of(autoTask));

      component.tasks.set([autoTask]);
      fixture.detectChanges();

      const dialogSpy = spyOn((component as unknown as { dialog: { open: jasmine.Spy } }).dialog, 'open').and.returnValue({
        afterClosed: () => of(null),
      } as never);

      component.openCorrectMatchDialog(autoTask);

      expect(dialogSpy).toHaveBeenCalled();
      const openArgs = dialogSpy.calls.mostRecent().args;
      const dialogData = openArgs[1]?.data;
      expect(dialogData?.quotationSupplierId).toBe('supplier-xyz-123');
      expect(dialogData?.quotationSupplierId).not.toBe('Fresh Farms Dairy');
      expect(dialogData?.baseUnits).toBeDefined();
      expect(dialogData?.baseUnits?.length).toBeGreaterThan(0);
    });

    it('renders "Corrected" and not raw translation key for task with reason corrected', () => {
      const correctedTask: MatchTask = {
        ...mockTasks[0],
        id: 'task-corrected-1',
        status: 'resolved',
        reason: 'corrected' as MatchTaskReason,
      };
      component.tasks.set([correctedTask]);
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Corrected');
      expect(text).not.toContain('matching.queue.reason.corrected');
    });

    it('handles 409 conflict when correcting match in queue', () => {
      const autoTask: MatchTask = {
        ...mockTasks[0],
        id: 'task-auto-1',
        status: 'auto_accepted',
        decision: {
          id: 'dec-1',
          quotation_line_id: 'line-101',
          matched_product: mockTasks[0].candidates[0].candidate_product,
          outcome: 'same_product',
          selected_match_candidate_id: 'cand-1',
          decided_at: '2026-08-21T01:00:00Z',
          decided_by: 'buyer@example.com',
          is_automatic: true,
          confidence: '0.8500',
        },
      };
      const errorResponse = new HttpErrorResponse({
        status: 409,
        error: {
          code: 'conflict',
          message: 'Line is on a live purchase request',
          details: {
            reason: 'line_on_purchase_request',
            purchase_request_id: '12345678-abcd-ef01-2345-6789abcdef01',
          },
        },
      });

      apiService.getMatchTaskForLine.and.returnValue(of(autoTask));
      apiService.correctMatch.and.returnValue(throwError(() => errorResponse));

      spyOn((component as unknown as { dialog: { open: jasmine.Spy } }).dialog, 'open').and.returnValue({
        afterClosed: () => of({
          expected_current_decision_id: 'dec-1',
          outcome: 'same_product',
          selected_match_candidate_id: 'cand-2',
          learn_alias: true,
        }),
      } as never);

      component.openCorrectMatchDialog(autoTask);

      expect(component.errorMessage()).toContain('12345678');
    });
  });

  describe('bulk confirm alias sweep feedback notices (US3 / T026)', () => {
    let snackSpy: jasmine.Spy;

    beforeEach(() => {
      const snackBar = (component as unknown as { snackBar: { open: jasmine.Spy } }).snackBar;
      snackSpy = spyOn(snackBar, 'open');
      fixture.detectChanges();
    });

    it('bulk confirm with 3 swept lines adds "Also matched 3 more lines with the same wording"', () => {
      apiService.confirmExactMatches.and.returnValue(
        of({
          confirmed: 3,
          skipped: 0,
          lines_matched_by_same_wording: ['swept-1', 'swept-2', 'swept-3'],
        }),
      );

      component.confirmAllExact();

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 3 more lines/),
        undefined,
        { duration: 4000 },
      );
    });

    it('bulk confirm with 1 swept line uses singular "Also matched 1 more line"', () => {
      apiService.confirmExactMatches.and.returnValue(
        of({
          confirmed: 1,
          skipped: 0,
          lines_matched_by_same_wording: ['swept-1'],
        }),
      );

      component.confirmAllExact();

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 1 more line/),
        undefined,
        { duration: 4000 },
      );
    });

    it('bulk confirm with null/empty swept lines leaves snackbar text unchanged from today', () => {
      apiService.confirmExactMatches.and.returnValue(
        of({
          confirmed: 3,
          skipped: 0,
          lines_matched_by_same_wording: null,
        }),
      );

      component.confirmAllExact();

      expect(snackSpy).toHaveBeenCalledWith(
        '3 matches confirmed.',
        undefined,
        { duration: 4000 },
      );
    });
  });
});
