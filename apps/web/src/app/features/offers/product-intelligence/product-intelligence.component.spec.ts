import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { PriceHistoryResponse } from '../offers-api';
import { ProductIntelligenceComponent } from './product-intelligence.component';

describe('ProductIntelligenceComponent (US2, T034)', () => {
  let component: ProductIntelligenceComponent;
  let fixture: ComponentFixture<ProductIntelligenceComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockHistoryResponse: PriceHistoryResponse = {
    product: {
      id: '00000000-0000-4000-8000-000000000001',
      tenant_name: 'Semi-Skimmed Milk 2L',
    },
    window_months: 6,
    points: [
      {
        landed_cost_id: 'lc-1',
        workspace_product_id: '00000000-0000-4000-8000-000000000001',
        supplier_id: 'supp-1',
        supplier_name: 'Supplier Alpha',
        recorded_at: '2026-08-01T10:00:00Z',
        valid_from: '2026-08-01T00:00:00Z',
        valid_to: '2026-09-01T00:00:00Z',
        normalised_unit_price: { amount: '12.0000', currency: 'GBP' },
        landed_cost_total: { amount: '120.0000', currency: 'GBP' },
        quantity: '10.000000',
        base_unit: 'L',
      },
      {
        landed_cost_id: 'lc-2',
        workspace_product_id: '00000000-0000-4000-8000-000000000001',
        supplier_id: 'supp-2',
        supplier_name: 'Supplier Beta',
        recorded_at: '2026-07-15T10:00:00Z',
        valid_from: '2026-07-15T00:00:00Z',
        valid_to: '2026-08-15T00:00:00Z',
        normalised_unit_price: { amount: '13.5000', currency: 'GBP' },
        landed_cost_total: { amount: '135.0000', currency: 'GBP' },
        quantity: '10.000000',
        base_unit: 'L',
      },
    ],
    summary: {
      last_paid: {
        value: { amount: '12.0000', currency: 'GBP' },
        source_landed_cost_ids: ['lc-1'],
      },
      average_paid_rolling_window: {
        value: { amount: '12.7500', currency: 'GBP' },
        source_landed_cost_ids: ['lc-1', 'lc-2'],
      },
      best_price: {
        value: { amount: '12.0000', currency: 'GBP' },
        source_landed_cost_ids: ['lc-1'],
      },
    },
    next_cursor: null,
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'products',
      'suppliers',
      'getPriceHistory',
    ]);
    apiService.products.and.returnValue(
      of({
        items: [
          {
            id: '00000000-0000-4000-8000-000000000001',
            tenant_name: 'Semi-Skimmed Milk 2L',
            canonical_name: 'Semi-Skimmed Milk',
            base_unit: 'L',
            pack: { pack_count: 1, unit_size: '2.0' },
            status: 'active',
            created_at: '2026-08-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    apiService.suppliers.and.returnValue(
      of({
        items: [
          {
            id: 'supp-1',
            name: 'Supplier Alpha',
            status: 'active',
            created_at: '2026-08-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    apiService.getPriceHistory.and.returnValue(of(mockHistoryResponse));

    await TestBed.configureTestingModule({
      imports: [ProductIntelligenceComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductIntelligenceComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and load price history intelligence', () => {
    expect(component).toBeTruthy();
    expect(apiService.products).toHaveBeenCalled();
    expect(apiService.suppliers).toHaveBeenCalled();
    expect(apiService.getPriceHistory).toHaveBeenCalled();
    expect(component.history()).toEqual(mockHistoryResponse);
  });

  it('should display summary metrics with traceability records', () => {
    const hist = component.history();
    expect(hist?.summary.last_paid?.value.amount).toBe('12.0000');
    expect(hist?.summary.average_paid_rolling_window?.value.amount).toBe('12.7500');
    expect(hist?.summary.best_price?.value.amount).toBe('12.0000');
    expect(hist?.summary.last_paid?.source_landed_cost_ids).toContain('lc-1');
  });

  it('should re-fetch price history when supplier filter changes', () => {
    component.onSupplierChange('supp-1');
    expect(apiService.getPriceHistory).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-000000000001',
      { supplier_id: 'supp-1', window_months: 6 },
    );
  });

  it('should re-fetch price history when window months changes', () => {
    component.onWindowChange(12);
    expect(apiService.getPriceHistory).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-000000000001',
      { supplier_id: undefined, window_months: 12 },
    );
  });

  it('should render empty state gracefully when product has no purchase history', () => {
    const emptyResponse: PriceHistoryResponse = {
      product: { id: 'prod-empty', tenant_name: 'Empty Product' },
      window_months: 6,
      points: [],
      summary: {
        last_paid: null,
        average_paid_rolling_window: null,
        best_price: null,
      },
      next_cursor: null,
    };
    component.history.set(emptyResponse);
    fixture.detectChanges();

    expect(component.history()?.points.length).toBe(0);
  });
});
