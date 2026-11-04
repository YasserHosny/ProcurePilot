import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, type WritableSignal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router, type ParamMap, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Quotation, ReviewTask, ReviewTaskPriority, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ReviewQueueComponent } from './review-queue.component';

describe('ReviewQueueComponent (T052)', () => {
  let component: ReviewQueueComponent;
  let fixture: ComponentFixture<ReviewQueueComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let mockRole: WritableSignal<Role | null>;

  const mockQuotation: Quotation = {
    id: 'q-101',
    document_id: 'doc-1',
    status: 'reviewed',
    created_at: '2026-08-21T01:00:00Z',
  };

  const mockTasks: ReviewTask[] = [
    {
      id: 'task-1',
      quotation_id: 'q-101',
      status: 'open',
      priority: 'high',
      reason: 'arithmetic_mismatch',
      created_at: '2026-08-21T01:00:00Z',
    },
    {
      id: 'task-2',
      quotation_id: 'q-102',
      status: 'open',
      priority: 'normal',
      reason: 'low_confidence',
      created_at: '2026-08-21T01:30:00Z',
    },
  ];

  function createMockTasks(count: number, offset = 1): ReviewTask[] {
    return Array.from({ length: count }, (_, i) => {
      const num = offset + i;
      return {
        id: `task-${num}`,
        quotation_id: `q-${num}`,
        status: 'open' as const,
        priority: 'normal' as const,
        reason: 'arithmetic_mismatch' as const,
        created_at: `2026-08-21T01:${String(num % 60).padStart(2, '0')}:00Z`,
      };
    });
  }

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'getReviewTasks',
      'archiveQuotation',
      'refuseQuotation',
      'updateReviewTaskPriority',
    ]);
    apiService.getReviewTasks.and.returnValue(of({ items: mockTasks, next_cursor: null }));
    apiService.archiveQuotation.and.returnValue(of(mockQuotation));
    apiService.refuseQuotation.and.returnValue(of(mockQuotation));
    apiService.updateReviewTaskPriority.and.returnValue(of(mockTasks[0]));

    mockRole = signal<Role | null>('buyer');
    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.callFake((...roles: Role[]) => {
        const current = mockRole();
        return current !== null && roles.includes(current);
      }),
      role: mockRole,
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    await TestBed.configureTestingModule({
      imports: [ReviewQueueComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(ReviewQueueComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load open tasks on init', () => {
    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      status: 'open',
      priority: undefined,
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
    expect(component.tasks().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should reload tasks when filter changes', () => {
    component.onStatusChange('all');
    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      status: 'all',
      priority: undefined,
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });

    component.onPriorityChange('high');
    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      status: 'all',
      priority: 'high',
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
  });

  it('should load more tasks with status all and cursor', () => {
    apiService.getReviewTasks.and.returnValue(
      of({ items: mockTasks, next_cursor: 'cursor-123' }),
    );
    component.onStatusChange('all');

    component.loadMore();

    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      cursor: 'cursor-123',
      status: 'all',
      priority: undefined,
      search: undefined,
      date_from: undefined,
      date_to: undefined,
      sort_by: 'created_at',
      sort_order: 'desc',
    });
  });

  it('should treat resolved tasks as view-only queue history', () => {
    const resolvedTask: ReviewTask = {
      ...mockTasks[0],
      status: 'resolved',
    };

    expect(component.isResolvedTask(resolvedTask)).toBeTrue();
    expect(component.reviewActionIcon(resolvedTask)).toBe('visibility');
    expect(component.reviewActionLabelKey(resolvedTask)).toBe('quotations.queue.actions.viewReview');
    expect(component.reviewActionIcon(mockTasks[0])).toBe('fact_check');
    expect(component.reviewActionLabelKey(mockTasks[0])).toBe('quotations.queue.actions.review');
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

    const expectedDateFrom = new Date(2026, 9, 22, 0, 0, 0, 0).toISOString();
    expect(component.dateFrom()).toBe('2026-10-22');
    expect(dateFromInput.value).toBe('22/10/2026');
    expect(apiService.getReviewTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        date_from: expectedDateFrom,
      }),
    );
  });

  it('an inverted date range shows an error and does not query the API (PPS-163)', () => {
    apiService.getReviewTasks.calls.reset();
    component.onDateFromChange('2026-10-22');
    expect(apiService.getReviewTasks).toHaveBeenCalledTimes(1);
    apiService.getReviewTasks.calls.reset();

    component.onDateToChange('2026-10-01');
    fixture.detectChanges();

    expect(component.dateRangeInvalid()).toBeTrue();
    expect(apiService.getReviewTasks).not.toHaveBeenCalled();
    const error = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="date-range-error"]');
    expect(error).not.toBeNull();
    expect(error?.getAttribute('role')).toBe('alert');
    expect(component.tasks()).toEqual([]);
    expect(component.isLoading()).toBeFalse();
  });

  it('fixing an inverted date range clears the error and loads again (PPS-163)', () => {
    component.onDateFromChange('2026-10-22');
    component.onDateToChange('2026-10-01');
    fixture.detectChanges();
    apiService.getReviewTasks.calls.reset();

    component.onDateToChange('2026-10-30');
    fixture.detectChanges();

    expect(component.dateRangeInvalid()).toBeFalse();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="date-range-error"]'),
    ).toBeNull();
    expect(apiService.getReviewTasks).toHaveBeenCalledTimes(1);
  });

  it('discards older filter response when newer filter request responds first (a)', () => {
    const subjectA = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
    const subjectB = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
    const tasksA: ReviewTask[] = [{ ...mockTasks[0], id: 'task-a' }];
    const tasksB: ReviewTask[] = [{ ...mockTasks[1], id: 'task-b' }];

    apiService.getReviewTasks.and.returnValue(subjectA);
    component.onPriorityChange('high');
    expect(component.isLoading()).toBeTrue();

    apiService.getReviewTasks.and.returnValue(subjectB);
    component.onStatusChange('resolved');
    expect(component.isLoading()).toBeTrue();

    // Filter B responds first
    subjectB.next({ items: tasksB, next_cursor: null });
    subjectB.complete();

    expect(component.tasks()).toEqual(tasksB);
    expect(component.isLoading()).toBeFalse();

    // Filter A responds later
    subjectA.next({ items: tasksA, next_cursor: null });
    subjectA.complete();

    expect(component.tasks()).toEqual(tasksB);
    expect(component.isLoading()).toBeFalse();
  });

  it('cancels pending loadMore on status change so late loadMore response does not append (b)', () => {
    apiService.getReviewTasks.and.returnValue(
      of({ items: mockTasks, next_cursor: 'cursor-1' }),
    );
    component.loadTasks();

    const loadMoreSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
    apiService.getReviewTasks.and.returnValue(loadMoreSubject);
    component.loadMore();
    expect(component.isLoadingMore()).toBeTrue();

    const statusChangeSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
    apiService.getReviewTasks.and.returnValue(statusChangeSubject);
    component.onStatusChange('all');

    expect(component.isLoadingMore()).toBeFalse();

    // Late loadMore response arrives
    const lateTasks: ReviewTask[] = [{ ...mockTasks[0], id: 'task-late-loadmore' }];
    loadMoreSubject.next({ items: lateTasks, next_cursor: 'cursor-late' });
    loadMoreSubject.complete();

    expect(component.tasks().some((t) => t.id === 'task-late-loadmore')).toBeFalse();
    expect(component.isLoadingMore()).toBeFalse();

    // Winning status change response completes
    const statusTasks: ReviewTask[] = [{ ...mockTasks[1], id: 'task-status-b' }];
    statusChangeSubject.next({ items: statusTasks, next_cursor: null });
    statusChangeSubject.complete();

    expect(component.tasks()).toEqual(statusTasks);
    expect(component.isLoading()).toBeFalse();
    expect(component.isLoadingMore()).toBeFalse();
  });

  it('ignores loadMore while loadTasks is still pending (c)', () => {
    apiService.getReviewTasks.and.returnValue(
      of({ items: mockTasks, next_cursor: 'cursor-1' }),
    );
    component.loadTasks();
    expect(component.nextCursor()).toBe('cursor-1');

    const pendingSubject = new Subject<{ items: ReviewTask[]; next_cursor: string | null }>();
    apiService.getReviewTasks.and.returnValue(pendingSubject);
    component.onStatusChange('all');
    expect(component.isLoading()).toBeTrue();

    apiService.getReviewTasks.calls.reset();

    component.loadMore();

    expect(apiService.getReviewTasks).not.toHaveBeenCalled();
    expect(component.isLoadingMore()).toBeFalse();
  });

  it('carries the same date range conversion in loadMore request (d)', () => {
    apiService.getReviewTasks.and.returnValue(
      of({ items: mockTasks, next_cursor: 'cursor-123' }),
    );
    component.onDateFromChange('2026-10-22');
    component.onDateToChange('2026-10-25');

    apiService.getReviewTasks.calls.reset();

    component.loadMore();

    const expectedDateFrom = new Date(2026, 9, 22, 0, 0, 0, 0).toISOString();
    const expectedDateTo = new Date(2026, 9, 25, 23, 59, 59, 999).toISOString();

    expect(apiService.getReviewTasks).toHaveBeenCalledWith(
      jasmine.objectContaining({
        cursor: 'cursor-123',
        date_from: expectedDateFrom,
        date_to: expectedDateTo,
      }),
    );
  });

  describe('Bulk actions & queue failure handling (PPS-159 / P-127)', () => {
    it('partial failure: retains failed ids, reports counts, and reloads list', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');
      spyOn(window, 'confirm').and.returnValue(true);
      const task3: ReviewTask = {
        id: 'task-3',
        quotation_id: 'q-103',
        status: 'open',
        priority: 'low',
        reason: 'arithmetic_mismatch',
        created_at: '2026-08-21T02:00:00Z',
      };
      component.tasks.set([...mockTasks, task3]);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2', 'task-3']));

      apiService.archiveQuotation.and.callFake((qId: string) => {
        if (qId === 'q-101') {
          return of(mockQuotation);
        }
        return throwError(() => new Error('Archive failed for ' + qId));
      });

      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: [mockTasks[1], task3], next_cursor: null }),
      );

      component.bulkArchive();

      expect(apiService.archiveQuotation).toHaveBeenCalledTimes(3);
      expect(apiService.getReviewTasks).toHaveBeenCalled();
      expect(component.selectedTaskIds().has('task-1')).toBeFalse();
      expect(component.selectedTaskIds().has('task-2')).toBeTrue();
      expect(component.selectedTaskIds().has('task-3')).toBeTrue();
      expect(component.selectedTaskIds().size).toBe(2);
      expect(snackBar.open).toHaveBeenCalledWith(
        jasmine.stringMatching(/1.*updated.*2.*failed/),
        undefined,
        jasmine.any(Object),
      );
    });

    it('all fail: retains all failed ids and reports failure count', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');
      spyOn(window, 'confirm').and.returnValue(true);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2']));

      apiService.archiveQuotation.and.returnValue(
        throwError(() => new Error('Network failure')),
      );

      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: mockTasks, next_cursor: null }),
      );

      component.bulkArchive();

      expect(apiService.archiveQuotation).toHaveBeenCalledTimes(2);
      expect(apiService.getReviewTasks).toHaveBeenCalled();
      expect(component.selectedTaskIds().has('task-1')).toBeTrue();
      expect(component.selectedTaskIds().has('task-2')).toBeTrue();
      expect(component.selectedTaskIds().size).toBe(2);
      expect(snackBar.open).toHaveBeenCalledWith(
        jasmine.stringMatching(/No tasks were updated.*2.*failed/),
        undefined,
        jasmine.any(Object),
      );
    });

    it('all succeed: empties selection, reports updated count, and reloads list', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');
      spyOn(window, 'confirm').and.returnValue(true);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2']));

      apiService.archiveQuotation.and.returnValue(of(mockQuotation));
      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: [], next_cursor: null }),
      );

      component.bulkArchive();

      expect(apiService.archiveQuotation).toHaveBeenCalledTimes(2);
      expect(apiService.getReviewTasks).toHaveBeenCalled();
      expect(component.selectedTaskIds().size).toBe(0);
      expect(snackBar.open).toHaveBeenCalledWith(
        jasmine.stringMatching(/2.*tasks updated/),
        undefined,
        jasmine.any(Object),
      );
    });

    it('bulk refuse: skips resolved tasks without sending request and counts as skipped', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');
      spyOn(window, 'confirm').and.returnValue(true);
      const resolvedTask: ReviewTask = {
        ...mockTasks[1],
        id: 'task-resolved',
        quotation_id: 'q-resolved',
        status: 'resolved',
      };
      component.tasks.set([mockTasks[0], resolvedTask]);
      component.selectedTaskIds.set(new Set(['task-1', 'task-resolved']));

      apiService.refuseQuotation.and.returnValue(of(mockQuotation));
      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: [resolvedTask], next_cursor: null }),
      );

      component.bulkRefuse();

      expect(apiService.refuseQuotation).toHaveBeenCalledWith('q-101');
      expect(apiService.refuseQuotation).not.toHaveBeenCalledWith('q-resolved');
      expect(apiService.refuseQuotation).toHaveBeenCalledTimes(1);
      expect(component.selectedTaskIds().size).toBe(0);
      expect(snackBar.open).toHaveBeenCalledWith(
        jasmine.stringMatching(/1.*tasks updated.*1.*skipped.*resolved/),
        undefined,
        jasmine.any(Object),
      );
    });

    it('bulk archive: skips resolved tasks without sending request and counts as skipped', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      spyOn(snackBar, 'open');
      spyOn(window, 'confirm').and.returnValue(true);
      const resolvedTask: ReviewTask = {
        ...mockTasks[1],
        id: 'task-resolved',
        quotation_id: 'q-resolved',
        status: 'resolved',
      };
      component.tasks.set([mockTasks[0], mockTasks[1], resolvedTask]);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2', 'task-resolved']));

      apiService.archiveQuotation.and.returnValue(of(mockQuotation));
      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: [resolvedTask], next_cursor: null }),
      );

      component.bulkArchive();

      expect(apiService.archiveQuotation).toHaveBeenCalledWith('q-101');
      expect(apiService.archiveQuotation).toHaveBeenCalledWith('q-102');
      expect(apiService.archiveQuotation).not.toHaveBeenCalledWith('q-resolved');
      expect(apiService.archiveQuotation).toHaveBeenCalledTimes(2);
      expect(component.selectedTaskIds().size).toBe(0);
      expect(snackBar.open).toHaveBeenCalledWith(
        jasmine.stringMatching(/2.*tasks updated.*1.*skipped.*resolved/),
        undefined,
        jasmine.any(Object),
      );
    });

    it('bulk result translation: requests the exact combined key and params for each combination with no string concatenation', () => {
      const snackBar = (component as unknown as { snackBar: MatSnackBar }).snackBar;
      const snackBarSpy = spyOn(snackBar, 'open');
      const translate = TestBed.inject(TranslateService);
      const recordedCalls: { key: string; params: unknown }[] = [];
      spyOn(translate, 'instant').and.callFake((key: string, params?: unknown) => {
        recordedCalls.push({ key, params });
        return `TRANSLATED:${key}`;
      });

      interface BulkCaller {
        finishBulkAction: (
          action: 'archive' | 'refuse' | 'reprioritise',
          succeededIds: string[],
          failedTasks: ReviewTask[],
          skippedIds: string[],
        ) => void;
      }
      const caller = component as unknown as BulkCaller;

      const combinations: {
        name: string;
        succeededIds: string[];
        failedTasks: ReviewTask[];
        skippedIds: string[];
        expectedKey: string;
        expectedParams: Record<string, unknown>;
      }[] = [
        {
          name: 'all succeeded without skipped',
          succeededIds: ['task-1', 'task-2'],
          failedTasks: [],
          skippedIds: [],
          expectedKey: 'quotations.queue.bulk.result.allSucceeded',
          expectedParams: { count: 2, succeeded: 2 },
        },
        {
          name: 'all succeeded with skipped',
          succeededIds: ['task-1', 'task-2'],
          failedTasks: [],
          skippedIds: ['task-3'],
          expectedKey: 'quotations.queue.bulk.result.allSucceededSkipped',
          expectedParams: { count: 2, succeeded: 2, skipped: 1 },
        },
        {
          name: 'partial without skipped',
          succeededIds: ['task-1'],
          failedTasks: [mockTasks[1]],
          skippedIds: [],
          expectedKey: 'quotations.queue.bulk.result.partial',
          expectedParams: { succeeded: 1, failed: 1, count: 2 },
        },
        {
          name: 'partial with skipped',
          succeededIds: ['task-1'],
          failedTasks: [mockTasks[1]],
          skippedIds: ['task-3'],
          expectedKey: 'quotations.queue.bulk.result.partialSkipped',
          expectedParams: { succeeded: 1, failed: 1, count: 2, skipped: 1 },
        },
        {
          name: 'all failed without skipped',
          succeededIds: [],
          failedTasks: [mockTasks[0], mockTasks[1]],
          skippedIds: [],
          expectedKey: 'quotations.queue.bulk.result.allFailed',
          expectedParams: { failed: 2, count: 2 },
        },
        {
          name: 'all failed with skipped',
          succeededIds: [],
          failedTasks: [mockTasks[0]],
          skippedIds: ['task-3'],
          expectedKey: 'quotations.queue.bulk.result.allFailedSkipped',
          expectedParams: { failed: 1, count: 1, skipped: 1 },
        },
      ];

      for (const c of combinations) {
        recordedCalls.length = 0;
        snackBarSpy.calls.reset();

        caller.finishBulkAction('archive', c.succeededIds, c.failedTasks, c.skippedIds);

        expect(recordedCalls.length).withContext(`${c.name}: translate.instant call count`).toBe(1);
        expect(recordedCalls[0].key).withContext(`${c.name}: key`).toBe(c.expectedKey);
        expect(recordedCalls[0].params).withContext(`${c.name}: params`).toEqual(c.expectedParams);
        expect(snackBarSpy).toHaveBeenCalledWith(
          `TRANSLATED:${c.expectedKey}`,
          undefined,
          jasmine.any(Object),
        );
      }
    });

    it('non-writer: bulk controls and selection checkboxes are not rendered', () => {
      mockRole.set('viewer');
      component.selectedTaskIds.set(new Set(['task-1']));
      fixture.detectChanges();

      const el = fixture.nativeElement as HTMLElement;
      expect(component.isWriter()).toBeFalse();
      expect(el.querySelector('.bulk-actions-bar')).toBeNull();
      expect(el.querySelector('[data-testid="bulk-actions-bar"]')).toBeNull();
      expect(el.querySelectorAll('mat-checkbox').length).toBe(0);
      expect(el.querySelectorAll('.select-cell').length).toBe(0);
      expect(el.querySelector('.read-only-banner')).not.toBeNull();
    });

    it('single archive: removes the archived task id from selectedTaskIds', () => {
      spyOn(window, 'confirm').and.returnValue(true);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2']));
      apiService.archiveQuotation.and.returnValue(of(mockQuotation));

      component.archiveTask(mockTasks[0], new MouseEvent('click'));

      expect(apiService.archiveQuotation).toHaveBeenCalledWith('q-101');
      expect(component.selectedTaskIds().has('task-1')).toBeFalse();
      expect(component.selectedTaskIds().has('task-2')).toBeTrue();
      expect(component.tasks().some((t) => t.id === 'task-1')).toBeFalse();
    });

    it('prepends failed rows not in first refreshed page, keeps failed ids selected, and prevents loadMore duplicates', () => {
      const tasks1To50 = createMockTasks(50, 1);
      const tasks51To100 = createMockTasks(50, 51);
      const all100Tasks = [...tasks1To50, ...tasks51To100];

      component.tasks.set(all100Tasks);
      component.selectedTaskIds.set(new Set(all100Tasks.map((t) => t.id)));

      apiService.updateReviewTaskPriority.and.callFake((taskId: string, priority: ReviewTaskPriority) => {
        const match = taskId.match(/task-(\d+)/);
        const index = match ? parseInt(match[1], 10) : 0;
        if (index <= 50) {
          return of({
            ...tasks1To50[index - 1],
            priority,
          });
        }
        return throwError(() => new Error(`Priority update failed for ${taskId}`));
      });

      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: tasks1To50, next_cursor: 'cursor-page-2' }),
      );

      component.bulkReprioritise('high');

      expect(component.selectedTaskIds().size).toBe(50);
      for (const failedTask of tasks51To100) {
        expect(component.selectedTaskIds().has(failedTask.id)).toBeTrue();
      }

      expect(component.tasks().length).toBe(100);
      for (const failedTask of tasks51To100) {
        expect(component.tasks().some((t) => t.id === failedTask.id)).toBeTrue();
      }

      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: tasks51To100, next_cursor: null }),
      );

      component.loadMore();

      expect(component.tasks().length).toBe(100);
      expect(component.nextCursor()).toBeNull();
    });

    it('normal bulk success path leaves the refreshed list exactly as returned with empty selection', () => {
      const refreshedTasks = [mockTasks[0]];
      component.tasks.set(mockTasks);
      component.selectedTaskIds.set(new Set(['task-1', 'task-2']));

      apiService.updateReviewTaskPriority.and.returnValue(
        of({ ...mockTasks[0], priority: 'high' }),
      );
      apiService.getReviewTasks.calls.reset();
      apiService.getReviewTasks.and.returnValue(
        of({ items: refreshedTasks, next_cursor: null }),
      );

      component.bulkReprioritise('high');

      expect(component.selectedTaskIds().size).toBe(0);
      expect(component.tasks()).toEqual(refreshedTasks);
    });
  });

  describe('URL query parameter synchronization & filters (PPS-163 / P-131)', () => {
    let router: Router;

    beforeEach(() => {
      router = TestBed.inject(Router);
      spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    });

    describe('URL restore on init', () => {
      it('restores filters, search, sort, and date range from query params on load', async () => {
        const queryParams = {
          status: 'resolved',
          priority: 'high',
          search: 'Acme',
          date_from: '2026-08-01',
          date_to: '2026-08-31',
          sort: 'stated_total',
          order: 'asc',
        };
        const mockActivatedRoute = {
          snapshot: {
            queryParamMap: convertToParamMap(queryParams),
          },
          queryParamMap: of(convertToParamMap(queryParams)),
        };

        const initFixture = TestBed.createComponent(ReviewQueueComponent);
        // Replace injected route before ngOnInit
        (initFixture.componentInstance as unknown as { route: typeof mockActivatedRoute }).route = mockActivatedRoute;
        apiService.getReviewTasks.calls.reset();
        initFixture.componentInstance.ngOnInit();
        initFixture.detectChanges();

        const comp = initFixture.componentInstance;
        expect(comp.statusFilter()).toBe('resolved');
        expect(comp.priorityFilter()).toBe('high');
        expect(comp.searchQuery()).toBe('Acme');
        expect(comp.dateFrom()).toBe('2026-08-01');
        expect(comp.dateTo()).toBe('2026-08-31');
        expect(comp.sortBy()).toBe('stated_total');
        expect(comp.sortOrder()).toBe('asc');

        const expectedDateFrom = new Date(2026, 7, 1, 0, 0, 0, 0).toISOString();
        const expectedDateTo = new Date(2026, 7, 31, 23, 59, 59, 999).toISOString();
        expect(apiService.getReviewTasks).toHaveBeenCalledWith({
          status: 'resolved',
          priority: 'high',
          search: 'Acme',
          date_from: expectedDateFrom,
          date_to: expectedDateTo,
          sort_by: 'stated_total',
          sort_order: 'asc',
        });
      });

      it('falls back to defaults when query params contain invalid values', () => {
        const invalidParams = {
          status: 'unknown_status',
          priority: 'urgent',
          search: '   ',
          date_from: 'invalid-date',
          date_to: '2026-13-45',
          sort: 'unsupported_column',
          order: 'sideways',
        };
        const mockActivatedRoute = {
          snapshot: {
            queryParamMap: convertToParamMap(invalidParams),
          },
          queryParamMap: of(convertToParamMap(invalidParams)),
        };

        const initFixture = TestBed.createComponent(ReviewQueueComponent);
        (initFixture.componentInstance as unknown as { route: typeof mockActivatedRoute }).route = mockActivatedRoute;
        apiService.getReviewTasks.calls.reset();
        initFixture.componentInstance.ngOnInit();
        initFixture.detectChanges();

        const comp = initFixture.componentInstance;
        expect(comp.statusFilter()).toBe('open');
        expect(comp.priorityFilter()).toBe('all');
        expect(comp.searchQuery()).toBe('');
        expect(comp.dateFrom()).toBeNull();
        expect(comp.dateTo()).toBeNull();
        expect(comp.sortBy()).toBe('created_at');
        expect(comp.sortOrder()).toBe('desc');

        expect(apiService.getReviewTasks).toHaveBeenCalledWith({
          status: 'open',
          priority: undefined,
          search: undefined,
          date_from: undefined,
          date_to: undefined,
          sort_by: 'created_at',
          sort_order: 'desc',
        });
      });
    });

    describe('URL queryParamMap reactive subscription', () => {
      it('loads tasks exactly once on init', () => {
        const queryParamMap$ = new BehaviorSubject<ParamMap>(
          convertToParamMap({ status: 'in_progress', priority: 'high' }),
        );
        const stubRoute = {
          snapshot: { queryParamMap: queryParamMap$.value },
          queryParamMap: queryParamMap$,
        };

        const testFixture = TestBed.createComponent(ReviewQueueComponent);
        (testFixture.componentInstance as unknown as { route: typeof stubRoute }).route = stubRoute;
        apiService.getReviewTasks.calls.reset();

        testFixture.detectChanges();

        expect(apiService.getReviewTasks).toHaveBeenCalledTimes(1);
        expect(testFixture.componentInstance.statusFilter()).toBe('in_progress');
        expect(testFixture.componentInstance.priorityFilter()).toBe('high');
      });

      it('does not reload when emitted params are equal to current state', () => {
        const queryParamMap$ = new BehaviorSubject<ParamMap>(
          convertToParamMap({ status: 'resolved', priority: 'low' }),
        );
        const stubRoute = {
          snapshot: { queryParamMap: queryParamMap$.value },
          queryParamMap: queryParamMap$,
        };

        const testFixture = TestBed.createComponent(ReviewQueueComponent);
        (testFixture.componentInstance as unknown as { route: typeof stubRoute }).route = stubRoute;
        testFixture.detectChanges();

        expect(testFixture.componentInstance.statusFilter()).toBe('resolved');
        expect(testFixture.componentInstance.priorityFilter()).toBe('low');

        apiService.getReviewTasks.calls.reset();
        queryParamMap$.next(convertToParamMap({ status: 'resolved', priority: 'low' }));

        expect(apiService.getReviewTasks).not.toHaveBeenCalled();
      });

      it('restores state and reloads once when different params are emitted (e.g. browser back)', () => {
        const queryParamMap$ = new BehaviorSubject<ParamMap>(
          convertToParamMap({ status: 'resolved', priority: 'high' }),
        );
        const stubRoute = {
          snapshot: { queryParamMap: queryParamMap$.value },
          queryParamMap: queryParamMap$,
        };

        const testFixture = TestBed.createComponent(ReviewQueueComponent);
        (testFixture.componentInstance as unknown as { route: typeof stubRoute }).route = stubRoute;
        testFixture.detectChanges();

        apiService.getReviewTasks.calls.reset();
        queryParamMap$.next(
          convertToParamMap({
            status: 'in_progress',
            priority: 'low',
            search: 'Widget',
            sort: 'stated_total',
            order: 'asc',
          }),
        );

        const comp = testFixture.componentInstance;
        expect(comp.statusFilter()).toBe('in_progress');
        expect(comp.priorityFilter()).toBe('low');
        expect(comp.searchQuery()).toBe('Widget');
        expect(comp.sortBy()).toBe('stated_total');
        expect(comp.sortOrder()).toBe('asc');
        expect(apiService.getReviewTasks).toHaveBeenCalledTimes(1);
        expect(apiService.getReviewTasks).toHaveBeenCalledWith(
          jasmine.objectContaining({
            status: 'in_progress',
            priority: 'low',
            search: 'Widget',
            sort_by: 'stated_total',
            sort_order: 'asc',
          }),
        );
      });

      it('resets filters to defaults and reloads once when params with no filters are emitted after filtered state', () => {
        const queryParamMap$ = new BehaviorSubject<ParamMap>(
          convertToParamMap({
            status: 'resolved',
            priority: 'high',
            search: 'Acme',
            date_from: '2026-08-01',
            date_to: '2026-08-31',
            sort: 'stated_total',
            order: 'asc',
          }),
        );
        const stubRoute = {
          snapshot: { queryParamMap: queryParamMap$.value },
          queryParamMap: queryParamMap$,
        };

        const testFixture = TestBed.createComponent(ReviewQueueComponent);
        (testFixture.componentInstance as unknown as { route: typeof stubRoute }).route = stubRoute;
        testFixture.detectChanges();

        const comp = testFixture.componentInstance;
        expect(comp.statusFilter()).toBe('resolved');
        expect(comp.priorityFilter()).toBe('high');

        apiService.getReviewTasks.calls.reset();
        queryParamMap$.next(convertToParamMap({}));

        expect(comp.statusFilter()).toBe('open');
        expect(comp.priorityFilter()).toBe('all');
        expect(comp.searchQuery()).toBe('');
        expect(comp.dateFrom()).toBeNull();
        expect(comp.dateTo()).toBeNull();
        expect(comp.sortBy()).toBe('created_at');
        expect(comp.sortOrder()).toBe('desc');
        expect(apiService.getReviewTasks).toHaveBeenCalledTimes(1);
        expect(apiService.getReviewTasks).toHaveBeenCalledWith(
          jasmine.objectContaining({
            status: 'open',
            priority: undefined,
            search: undefined,
            date_from: undefined,
            date_to: undefined,
            sort_by: 'created_at',
            sort_order: 'desc',
          }),
        );
      });
    });

    describe('URL update on change', () => {
      it('navigates with queryParams, queryParamsHandling: merge, and replaceUrl: true on status change', () => {
        component.onStatusChange('resolved');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: 'resolved',
            priority: null,
            search: null,
            date_from: null,
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });

        // Changing back to default 'open' omits status from URL (sets to null)
        (router.navigate as jasmine.Spy).calls.reset();
        component.onStatusChange('open');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: null,
            date_from: null,
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });

      it('navigates with updated queryParams on priority change', () => {
        component.onPriorityChange('high');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: 'high',
            search: null,
            date_from: null,
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });

      it('navigates with updated queryParams on search change', () => {
        component.onSearchChange('Supplier A');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: 'Supplier A',
            date_from: null,
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });

      it('navigates with updated queryParams on date range change', () => {
        component.onDateFromChange('2026-10-01');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: null,
            date_from: '2026-10-01',
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });

        (router.navigate as jasmine.Spy).calls.reset();
        component.onDateToChange('2026-10-15');

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: null,
            date_from: '2026-10-01',
            date_to: '2026-10-15',
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });

      it('navigates with sort and order queryParams on sort change', () => {
        component.onSortChange({ active: 'stated_total', direction: 'asc' });

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: null,
            date_from: null,
            date_to: null,
            sort: 'stated_total',
            order: 'asc',
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
      });
    });

    describe('Always-visible Clear filters control and active filter chips', () => {
      it('renders Clear filters button always, disabled when no filters active', () => {
        const el = fixture.nativeElement as HTMLElement;
        const clearBtn = el.querySelector<HTMLButtonElement>('[data-testid="clear-filters-btn"], .filter-row .clear-filters-btn');
        expect(clearBtn).not.toBeNull();
        expect(clearBtn?.disabled).toBeTrue();
        expect(component.hasActiveFilters()).toBeFalse();
      });

      it('enables Clear filters button when any filter is active and clears all on click', () => {
        component.onPriorityChange('high');
        component.onSearchChange('Widget');
        fixture.detectChanges();

        expect(component.hasActiveFilters()).toBeTrue();
        const el = fixture.nativeElement as HTMLElement;
        const clearBtn = el.querySelector<HTMLButtonElement>('[data-testid="clear-filters-btn"], .filter-row .clear-filters-btn');
        expect(clearBtn?.disabled).toBeFalse();

        (router.navigate as jasmine.Spy).calls.reset();
        apiService.getReviewTasks.calls.reset();

        clearBtn?.click();
        fixture.detectChanges();

        expect(component.statusFilter()).toBe('open');
        expect(component.priorityFilter()).toBe('all');
        expect(component.searchQuery()).toBe('');
        expect(component.dateFrom()).toBeNull();
        expect(component.dateTo()).toBeNull();
        expect(component.hasActiveFilters()).toBeFalse();
        expect(clearBtn?.disabled).toBeTrue();

        expect(router.navigate).toHaveBeenCalledWith([], {
          queryParams: {
            status: null,
            priority: null,
            search: null,
            date_from: null,
            date_to: null,
            sort: null,
            order: null,
          },
          queryParamsHandling: 'merge',
          replaceUrl: true,
        });
        expect(apiService.getReviewTasks).toHaveBeenCalled();
      });

      it('renders active filter chips and removing each reloads the list and updates URL', () => {
        component.onStatusChange('resolved');
        component.onPriorityChange('low');
        component.onSearchChange('Delta');
        component.onDateFromChange('2026-09-01');
        component.onDateToChange('2026-09-30');
        fixture.detectChanges();

        const el = fixture.nativeElement as HTMLElement;
        expect(el.querySelector('[data-testid="chip-status"]')).not.toBeNull();
        expect(el.querySelector('[data-testid="chip-priority"]')).not.toBeNull();
        expect(el.querySelector('[data-testid="chip-search"]')).not.toBeNull();
        expect(el.querySelector('[data-testid="chip-date-range"]')).not.toBeNull();

        // 1. Remove status chip
        (router.navigate as jasmine.Spy).calls.reset();
        apiService.getReviewTasks.calls.reset();
        el.querySelector<HTMLButtonElement>('[data-testid="remove-status-chip"]')!.click();
        fixture.detectChanges();

        expect(component.statusFilter()).toBe('open');
        expect(apiService.getReviewTasks).toHaveBeenCalled();
        expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
          queryParams: jasmine.objectContaining({ status: null }),
        }));
        expect(el.querySelector('[data-testid="chip-status"]')).toBeNull();

        // 2. Remove priority chip
        (router.navigate as jasmine.Spy).calls.reset();
        apiService.getReviewTasks.calls.reset();
        el.querySelector<HTMLButtonElement>('[data-testid="remove-priority-chip"]')!.click();
        fixture.detectChanges();

        expect(component.priorityFilter()).toBe('all');
        expect(apiService.getReviewTasks).toHaveBeenCalled();
        expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
          queryParams: jasmine.objectContaining({ priority: null }),
        }));
        expect(el.querySelector('[data-testid="chip-priority"]')).toBeNull();

        // 3. Remove search chip
        (router.navigate as jasmine.Spy).calls.reset();
        apiService.getReviewTasks.calls.reset();
        el.querySelector<HTMLButtonElement>('[data-testid="remove-search-chip"]')!.click();
        fixture.detectChanges();

        expect(component.searchQuery()).toBe('');
        expect(apiService.getReviewTasks).toHaveBeenCalled();
        expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
          queryParams: jasmine.objectContaining({ search: null }),
        }));
        expect(el.querySelector('[data-testid="chip-search"]')).toBeNull();

        // 4. Remove date range chip
        (router.navigate as jasmine.Spy).calls.reset();
        apiService.getReviewTasks.calls.reset();
        el.querySelector<HTMLButtonElement>('[data-testid="remove-date-range-chip"]')!.click();
        fixture.detectChanges();

        expect(component.dateFrom()).toBeNull();
        expect(component.dateTo()).toBeNull();
        expect(apiService.getReviewTasks).toHaveBeenCalled();
        expect(router.navigate).toHaveBeenCalledWith([], jasmine.objectContaining({
          queryParams: jasmine.objectContaining({ date_from: null, date_to: null }),
        }));
        expect(el.querySelector('[data-testid="chip-date-range"]')).toBeNull();
      });
    });

    describe('Result count text', () => {
      it('displays correct pluralized count when list is loaded', () => {
        component.tasks.set(mockTasks); // 2 tasks
        component.nextCursor.set(null);
        fixture.detectChanges();

        const el = fixture.nativeElement as HTMLElement;
        const countEl = el.querySelector('[data-testid="result-count"], .result-count');
        expect(countEl?.textContent?.trim()).toBe('2 results');
        expect(component.resultCountText()).toBe('2 results');
      });

      it('displays "1 result" for a single loaded item', () => {
        component.tasks.set([mockTasks[0]]);
        component.nextCursor.set(null);
        fixture.detectChanges();

        const el = fixture.nativeElement as HTMLElement;
        const countEl = el.querySelector('[data-testid="result-count"], .result-count');
        expect(countEl?.textContent?.trim()).toBe('1 result');
        expect(component.resultCountText()).toBe('1 result');
      });

      it('displays "N+" when more pages exist', () => {
        component.tasks.set(mockTasks); // 2 tasks
        component.nextCursor.set('next-cursor-xyz');
        fixture.detectChanges();

        const el = fixture.nativeElement as HTMLElement;
        const countEl = el.querySelector('[data-testid="result-count"], .result-count');
        expect(countEl?.textContent?.trim()).toBe('2+ results');
        expect(component.resultCountText()).toBe('2+ results');
      });

      it('displays "0 results" when empty list is loaded without more pages', () => {
        component.tasks.set([]);
        component.nextCursor.set(null);
        fixture.detectChanges();

        expect(component.resultCountText()).toBe('0 results');
      });
    });
  });
});
