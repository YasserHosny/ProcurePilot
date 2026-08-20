import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

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
      imports: [ReviewQueueComponent, TranslateModule.forRoot()],
      providers: [
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
    });
    expect(component.tasks().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should reload tasks when filter changes', () => {
    component.onStatusChange('all');
    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      status: undefined,
      priority: undefined,
    });

    component.onPriorityChange('high');
    expect(apiService.getReviewTasks).toHaveBeenCalledWith({
      status: undefined,
      priority: 'high',
    });
  });
});
