import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import {
  ForecastingApiService,
  type ReorderProposal,
} from '../forecasting-api';
import { ReorderQueueComponent } from './reorder-queue.component';

describe('ReorderQueueComponent (R4.0)', () => {
  let component: ReorderQueueComponent;
  let fixture: ComponentFixture<ReorderQueueComponent>;
  let forecastingApi: jasmine.SpyObj<ForecastingApiService>;
  let api: jasmine.SpyObj<ApiService>;

  const proposal: ReorderProposal = {
    id: 'proposal-1',
    demand_forecast_id: 'forecast-1',
    workspace_product_id: 'product-1',
    product_name: 'A4 Copy Paper',
    status: 'open',
    horizon_days: 14,
    source_window_start: '2026-09-01',
    source_window_end: '2026-09-20',
    observed_history_days: 20,
    expected_daily_demand: '2.0000',
    expected_demand: '28.0000',
    uncertainty_lower: '18.2000',
    uncertainty_upper: '37.8000',
    stock_on_hand: '3.0000',
    suggested_quantity: '31.0000',
    confidence: 'low',
    state: 'provisional',
    release_posture: 'g3_unmet',
    valid_from: '2026-09-20T10:00:00Z',
    valid_until: '2026-10-04T10:00:00Z',
    purchase_request_id: null,
    prepared_branch_id: null,
    created_at: '2026-09-20T10:00:00Z',
  };

  beforeEach(async () => {
    forecastingApi = jasmine.createSpyObj<ForecastingApiService>('ForecastingApiService', [
      'recompute',
      'listProposals',
      'prepareRequest',
    ]);
    api = jasmine.createSpyObj<ApiService>('ApiService', ['listBranches']);
    forecastingApi.listProposals.and.returnValue(of({ items: [proposal], next_cursor: null }));
    forecastingApi.recompute.and.returnValue(
      of({ generated_forecasts: 1, open_proposals: 1, release_posture: 'g3_unmet' }),
    );
    forecastingApi.prepareRequest.and.returnValue(
      of({
        proposal: { ...proposal, status: 'prepared', purchase_request_id: 'request-1' },
        purchase_request_id: 'request-1',
      }),
    );
    api.listBranches.and.returnValue(
      of({
        items: [
          {
            id: 'branch-1',
            name: 'Main Branch',
            is_active: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );

    const session = {
      hasRole: (...roles: readonly Role[]) => roles.includes('owner'),
      isAuthenticated: signal(true),
      activeLocale: signal<'en' | 'ar'>('en'),
    };
    const snackBar = jasmine.createSpyObj<MatSnackBar>('MatSnackBar', ['open']);

    await TestBed.configureTestingModule({
      imports: [ReorderQueueComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        { provide: ForecastingApiService, useValue: forecastingApi },
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: session },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      common: { loading: 'Loading', retry: 'Retry', notAvailable: 'Not available' },
      forecasting: {
        title: 'Reorder Forecasts',
        subtitle: 'Review forecasts',
        listLabel: 'Proposals',
        g3: { title: 'G3 unmet', message: 'Preview' },
        actions: { refresh: 'Refresh', prepareRequest: 'Prepare request' },
        controls: { title: 'Draft request', description: 'Details', branch: 'Branch', requiredBy: 'Required by' },
        recompute: { success: 'Refreshed' },
        prepare: { success: 'Prepared' },
        errors: { load: 'Load failed', recompute: 'Refresh failed', prepare: 'Prepare failed' },
        empty: { title: 'Empty', message: 'No proposals' },
        status: { open: 'Open', prepared: 'Prepared', dismissed: 'Dismissed', expired: 'Expired' },
        state: { ready: 'Ready', provisional: 'Provisional', insufficient_data: 'Insufficient' },
        card: {
          product: 'Product',
          stock: 'Stock',
          expectedDemand: 'Expected',
          uncertainty: 'Uncertainty',
          suggestedQuantity: 'Suggested',
          history: 'History {{days}}',
          validUntil: 'Valid {{date}}',
          insufficientData: 'Insufficient',
          provisional: 'Provisional',
          prepared: 'Prepared',
        },
      },
    });
    translate.use('en');

    fixture = TestBed.createComponent(ReorderQueueComponent);
    component = fixture.componentInstance;
  });

  it('loads proposals and keeps the G3-unmet release posture visible in the data', () => {
    fixture.detectChanges();

    expect(forecastingApi.listProposals).toHaveBeenCalledWith({ limit: 100 });
    expect(component.proposals()).toEqual([proposal]);
    expect(component.proposals()[0].release_posture).toBe('g3_unmet');
    expect(component.proposals()[0].state).toBe('provisional');
  });

  it('prepares a draft request without changing the proposal into an automatic order', () => {
    fixture.detectChanges();

    component.prepareRequest(proposal);

    expect(forecastingApi.prepareRequest).toHaveBeenCalledWith(
      'proposal-1',
      jasmine.objectContaining({ branch_id: 'branch-1' }),
    );
    expect(component.proposals()[0].status).toBe('prepared');
    expect(component.proposals()[0].purchase_request_id).toBe('request-1');
  });
});
