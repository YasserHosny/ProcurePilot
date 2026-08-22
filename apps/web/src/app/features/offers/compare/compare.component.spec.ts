import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { OfferComparison } from '../offers-api';
import { CompareComponent } from './compare.component';

describe('CompareComponent (US1, SC-002, T020)', () => {
  let component: CompareComponent;
  let fixture: ComponentFixture<CompareComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockComparison: OfferComparison = {
    product: {
      id: '00000000-0000-4000-8000-000000000001',
      tenant_name: 'Semi-Skimmed Milk 2L',
    },
    requested_quantity: '10.000000',
    offers: [
      {
        id: 'offer-1',
        workspace_product_id: '00000000-0000-4000-8000-000000000001',
        supplier_id: 'supp-1',
        supplier_name: 'Supplier Alpha',
        quotation_line_id: 'ql-1',
        match_decision_id: 'md-1',
        landed_cost: { amount: '120.0000', currency: 'GBP' },
        normalised_unit_price: { amount: '12.0000', currency: 'GBP' },
        requested_quantity: '10.000000',
        base_unit: 'L',
        lead_time_days: 2,
        reliability_score: '0.950',
        stock_signal: null,
        match_confidence: '0.9800',
        valid_from: '2026-08-01T00:00:00Z',
        valid_to: '2026-09-01T00:00:00Z',
        is_expired: false,
        rule_version: '1.0',
        recorded_at: '2026-08-01T00:00:00Z',
      },
      {
        id: 'offer-2',
        workspace_product_id: '00000000-0000-4000-8000-000000000001',
        supplier_id: 'supp-2',
        supplier_name: 'Supplier Beta',
        quotation_line_id: 'ql-2',
        match_decision_id: 'md-2',
        landed_cost: { amount: '150.0000', currency: 'GBP' },
        normalised_unit_price: { amount: '15.0000', currency: 'GBP' },
        requested_quantity: '10.000000',
        base_unit: 'L',
        lead_time_days: 5,
        reliability_score: '0.850',
        stock_signal: null,
        match_confidence: '0.9000',
        valid_from: '2026-08-01T00:00:00Z',
        valid_to: '2026-09-01T00:00:00Z',
        is_expired: false,
        rule_version: '1.0',
        recorded_at: '2026-08-01T00:00:00Z',
      },
      {
        id: 'offer-expired',
        workspace_product_id: '00000000-0000-4000-8000-000000000001',
        supplier_id: 'supp-3',
        supplier_name: 'Supplier Gamma (Expired)',
        quotation_line_id: 'ql-3',
        match_decision_id: 'md-3',
        landed_cost: { amount: '90.0000', currency: 'GBP' },
        normalised_unit_price: { amount: '9.0000', currency: 'GBP' },
        requested_quantity: '10.000000',
        base_unit: 'L',
        lead_time_days: 1,
        reliability_score: '0.990',
        stock_signal: null,
        match_confidence: '0.9900',
        valid_from: '2026-07-01T00:00:00Z',
        valid_to: '2026-07-15T00:00:00Z',
        is_expired: true,
        rule_version: '1.0',
        recorded_at: '2026-07-01T00:00:00Z',
      },
    ],
    recommendation: {
      recommended_offer_id: 'offer-1',
      score: '0.9450',
      confidence: 'high',
      valid_from: '2026-08-01T00:00:00Z',
      valid_to: '2026-09-01T00:00:00Z',
      risk_notes: [],
      evidence: {
        weights: {
          cost: '0.55',
          match_confidence: '0.20',
          reliability: '0.15',
          lead_time: '0.10',
        },
        components: {
          cost: '1.0000',
          match_confidence: '0.9800',
          reliability: '0.9500',
          lead_time: '0.9333',
        },
        winning_margin: '0.1200',
        tie_break: {
          applied: false,
          rule: ['cheapest_cost', 'match_confidence', 'reliability', 'lead_time', 'validity_window', 'supplier_name', 'supplier_id'],
        },
      },
    },
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj<ApiService>('ApiService', ['products', 'compareOffers']);
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
    apiService.compareOffers.and.returnValue(of(mockComparison));

    await TestBed.configureTestingModule({
      imports: [CompareComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(CompareComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and load product comparison', () => {
    expect(component).toBeTruthy();
    expect(apiService.products).toHaveBeenCalled();
    expect(apiService.compareOffers).toHaveBeenCalled();
    expect(component.rawComparison()).toEqual(mockComparison);
    expect(component.recommendedOffer()?.id).toBe('offer-1');
  });

  it('should exclude expired offers from active visible offers by default', () => {
    const visible = component.visibleOffers();
    expect(visible.length).toBe(2);
    expect(visible.some((o) => o.is_expired)).toBeFalse();

    // Toggle includeExpired
    component.toggleIncludeExpired();
    fixture.detectChanges();
    expect(component.visibleOffers().length).toBe(3);
  });

  it('SC-002: should recalculate projected landed cost and recommendation client-side without network calls per keystroke in <150ms budget', () => {
    const initialNetworkCalls = component.networkCallCount;
    expect(initialNetworkCalls).toBe(1);

    const startTime = performance.now();

    // User changes quantity from 10 to 50
    component.onQuantityChange('50');
    fixture.detectChanges();

    const elapsed = performance.now() - startTime;

    // Must be well under 150ms (typically < 10ms for client arithmetic)
    expect(elapsed).toBeLessThan(150);

    // CRITICAL: Must NOT have initiated a new network request (SC-002 requirement)
    expect(component.networkCallCount).toBe(initialNetworkCalls);

    const proj = component.projected();
    expect(proj).toBeTruthy();
    expect(proj?.requested_quantity).toBe('50');

    // Offer 1 original total was 120 for 10 units -> for 50 units it should be 600.0000
    const offer1 = proj?.offers.find((o) => o.id === 'offer-1');
    expect(offer1?.projected_landed_cost.amount).toBe('600.0000');

    // Offer 2 original total was 150 for 10 units -> for 50 units it should be 750.0000
    const offer2 = proj?.offers.find((o) => o.id === 'offer-2');
    expect(offer2?.projected_landed_cost.amount).toBe('750.0000');

    // Recommendation re-evaluated client-side
    expect(proj?.recommendation?.recommended_offer_id).toBe('offer-1');
  });

  it('should render unknown stock signal correctly', () => {
    const proj = component.projected();
    expect(proj?.offers[0].stock_signal).toBeNull();
  });

  it('should handle empty offers state gracefully', () => {
    const emptyComp: OfferComparison = {
      product: { id: 'prod-empty', tenant_name: 'Empty Product' },
      requested_quantity: '10',
      offers: [],
      recommendation: null,
    };
    component.rawComparison.set(emptyComp);
    fixture.detectChanges();

    expect(component.visibleOffers().length).toBe(0);
    expect(component.recommendedOffer()).toBeNull();
  });

  it('should generate correct record purchase query params passing only product/evidence identifiers (T034)', () => {
    const offer = component.visibleOffers()[0];
    const params = component.getRecordPurchaseParams(offer);

    expect(params['product_id']).toBe('00000000-0000-4000-8000-000000000001');
    expect(params['supplier_id']).toBe('supp-1');
    expect(params['quotation_line_id']).toBe('ql-1');
    expect(params['match_decision_id']).toBe('md-1');
    expect(params['quantity']).toBe('10');
    expect(params['unit_price']).toBe('12.0000');
    expect(params['currency']).toBe('GBP');
    expect(params['tenant_id']).toBeUndefined(); // Never pass tenant id
  });
});

