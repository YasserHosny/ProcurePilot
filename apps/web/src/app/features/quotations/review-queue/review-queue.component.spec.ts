import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { Subject, of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { ReviewTask, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ReviewQueueComponent } from './review-queue.component';

describe('ReviewQueueComponent (T052)', () => {
  let component: ReviewQueueComponent;
  let fixture: ComponentFixture<ReviewQueueComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

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

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['getReviewTasks']);
    apiService.getReviewTasks.and.returnValue(of({ items: mockTasks, next_cursor: null }));

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
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
});
