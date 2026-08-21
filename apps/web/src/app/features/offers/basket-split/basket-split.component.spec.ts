import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { BasketSplitJob } from '../offers-api';
import { BasketSplitComponent } from './basket-split.component';

describe('BasketSplitComponent (US3, T045)', () => {
  let component: BasketSplitComponent;
  let fixture: ComponentFixture<BasketSplitComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockFeasibleJob: BasketSplitJob = {
    id: 'job-1',
    supplier_ids: ['supp-1', 'supp-2'],
    items: [
      { workspace_product_id: 'prod-1', quantity: '10.000000' },
      { workspace_product_id: 'prod-2', quantity: '20.000000' },
    ],
    status: 'completed',
    result: {
      feasible: true,
      allocation: [
        {
          supplier_id: 'supp-1',
          lines: [
            {
              workspace_product_id: 'prod-1',
              quantity: '10.000000',
              offer_id: 'off-1',
              landed_cost: { amount: '100.0000', currency: 'GBP' },
            },
          ],
          total_landed_cost: { amount: '100.0000', currency: 'GBP' },
        },
        {
          supplier_id: 'supp-2',
          lines: [
            {
              workspace_product_id: 'prod-2',
              quantity: '20.000000',
              offer_id: 'off-2',
              landed_cost: { amount: '160.0000', currency: 'GBP' },
            },
          ],
          total_landed_cost: { amount: '160.0000', currency: 'GBP' },
        },
      ],
      total_landed_cost: { amount: '260.0000', currency: 'GBP' },
      single_supplier_baselines: [
        {
          supplier_id: 'supp-1',
          feasible: true,
          total_landed_cost: { amount: '300.0000', currency: 'GBP' },
        },
        {
          supplier_id: 'supp-2',
          feasible: true,
          total_landed_cost: { amount: '280.0000', currency: 'GBP' },
        },
      ],
      infeasible_items: [],
      solver_version: '1.0.0',
      computed_at: '2026-08-21T10:00:00Z',
    },
    error: null,
    result_url: '/api/v1/baskets/job-1',
    created_at: '2026-08-21T10:00:00Z',
  };

  const mockInfeasibleJob: BasketSplitJob = {
    id: 'job-infeasible',
    supplier_ids: ['supp-1', 'supp-2'],
    items: [{ workspace_product_id: 'prod-missing', quantity: '5.000000' }],
    status: 'completed',
    result: {
      feasible: false,
      allocation: [],
      total_landed_cost: null,
      single_supplier_baselines: [],
      infeasible_items: [
        {
          workspace_product_id: 'prod-missing',
          requested_quantity: '5.000000',
          reason: 'no_offer_from_named_suppliers',
          missing_supplier_ids: ['supp-1', 'supp-2'],
        },
      ],
      solver_version: '1.0.0',
      computed_at: '2026-08-21T10:00:00Z',
    },
    error: null,
    result_url: '/api/v1/baskets/job-infeasible',
    created_at: '2026-08-21T10:00:00Z',
  };

  const mockFailedJob: BasketSplitJob = {
    id: 'job-failed',
    supplier_ids: ['supp-1', 'supp-2'],
    items: [{ workspace_product_id: 'prod-1', quantity: '5.000000' }],
    status: 'failed',
    result: null,
    error: { message: 'Optimizer worker timeout' },
    result_url: '/api/v1/baskets/job-failed',
    created_at: '2026-08-21T10:00:00Z',
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'suppliers',
      'products',
      'optimiseBasket',
      'getBasketSplitJob',
    ]);

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    apiService.suppliers.and.returnValue(
      of({
        items: [
          { id: 'supp-1', name: 'Supplier Alpha', status: 'active', created_at: '2026-08-01T00:00:00Z' },
          { id: 'supp-2', name: 'Supplier Beta', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        ],
        next_cursor: null,
      }),
    );
    apiService.products.and.returnValue(
      of({
        items: [
          {
            id: 'prod-1',
            tenant_name: 'Product 1',
            canonical_name: 'P1',
            base_unit: 'EA',
            pack: { pack_count: 1, unit_size: '1' },
            status: 'active',
            created_at: '2026-08-01T00:00:00Z',
          },
          {
            id: 'prod-2',
            tenant_name: 'Product 2',
            canonical_name: 'P2',
            base_unit: 'EA',
            pack: { pack_count: 1, unit_size: '1' },
            status: 'active',
            created_at: '2026-08-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [BasketSplitComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(BasketSplitComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and populate suppliers and products', () => {
    expect(component).toBeTruthy();
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(apiService.products).toHaveBeenCalled();
    expect(component.supplierId1()).toBe('supp-1');
    expect(component.supplierId2()).toBe('supp-2');
  });

  it('should validate form and prevent submission with same supplier or invalid quantities', () => {
    expect(component.isFormValid()).toBeTrue();

    // Select same supplier
    component.supplierId2.set('supp-1');
    expect(component.isFormValid()).toBeFalse();

    component.supplierId2.set('supp-2');
    expect(component.isFormValid()).toBeTrue();

    // Invalid quantity
    component.onQuantityChange(0, '0');
    expect(component.isFormValid()).toBeFalse();
  });

  it('should submit basket and handle queued to feasible completed job', () => {
    const queuedJob: BasketSplitJob = {
      ...mockFeasibleJob,
      status: 'queued',
      result: null,
    };
    apiService.optimiseBasket.and.returnValue(of(queuedJob));
    apiService.getBasketSplitJob.and.returnValue(of(mockFeasibleJob));

    component.submitBasket();
    expect(apiService.optimiseBasket).toHaveBeenCalled();
    expect(component.currentJob()?.id).toBe('job-1');
  });

  it('should distinguish and render a feasible completed result with baseline savings', () => {
    component.currentJob.set(mockFeasibleJob);
    fixture.detectChanges();

    expect(component.uiState()).toBe('completed_feasible');
    const savings = component.getSingleSupplierSavings();
    expect(savings.type).toBe('split_saves');
    expect(savings.savingsAmount).toBe('20.00'); // 280 - 260 = 20
    expect(savings.cheaperSupplierName).toBe('Supplier Beta');
  });

  it('should distinguish and render an infeasible completed result distinctly from failed job', () => {
    component.currentJob.set(mockInfeasibleJob);
    fixture.detectChanges();

    // Must be completed_infeasible, NOT failed
    expect(component.uiState()).toBe('completed_infeasible');
    expect(component.currentJob()?.result?.feasible).toBeFalse();
    expect(component.currentJob()?.result?.infeasible_items.length).toBe(1);
  });

  it('should distinguish and render a failed job as system failure', () => {
    component.currentJob.set(mockFailedJob);
    fixture.detectChanges();

    expect(component.uiState()).toBe('failed');
  });
});
