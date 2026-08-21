import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { MatchTask, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ResolutionQueueComponent } from './resolution-queue.component';

describe('ResolutionQueueComponent (T038)', () => {
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
        unit_price: { amount: '2.50', currency: 'GBP' },
      },
      status: 'open',
      priority: 'high',
      reason: 'low_confidence',
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
        unit_price: { amount: '4.00', currency: 'GBP' },
      },
      status: 'open',
      priority: 'normal',
      reason: 'close_candidates',
      candidates: [],
      created_at: '2026-08-21T01:30:00Z',
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['getMatchTasks']);
    apiService.getMatchTasks.and.returnValue(of({ items: mockTasks, next_cursor: null }));

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

  it('should load open match tasks on init', () => {
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: 'open',
      priority: undefined,
      reason: undefined,
    });
    expect(component.tasks().length).toBe(2);
    expect(component.isLoading()).toBeFalse();
  });

  it('should reload tasks when filters change', () => {
    component.onStatusChange('all');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: undefined,
      priority: undefined,
      reason: undefined,
    });

    component.onPriorityChange('high');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: undefined,
      priority: 'high',
      reason: undefined,
    });

    component.onReasonChange('low_confidence');
    expect(apiService.getMatchTasks).toHaveBeenCalledWith({
      status: undefined,
      priority: 'high',
      reason: 'low_confidence',
    });
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
