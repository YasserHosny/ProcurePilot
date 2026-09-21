import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { Subject, of } from 'rxjs';

import type { SupplierScorecard } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { NegotiationBrief, SupplierRiskApiService } from '../supplier-risk-api';
import { ScorecardV2PanelComponent } from './scorecard-v2-panel.component';

describe('ScorecardV2PanelComponent', () => {
  let fixture: ComponentFixture<ScorecardV2PanelComponent>;
  let api: jasmine.SpyObj<SupplierRiskApiService>;
  let session: jasmine.SpyObj<SessionService>;
  let router: Router;

  const component = (
    risk: string,
    overrides: Record<string, unknown> = {},
  ) => ({
    value: risk,
    risk,
    sample_count: 8,
    product_count: 2,
    confidence: 'medium' as const,
    insufficient_evidence: false,
    excluded_counts: { cancelled: 1 },
    source_ids: ['order-001'],
    source_refs: [{ source_id: 'order-001', source_kind: 'purchase_order' as const }],
    window_start: '2026-03-24',
    split_date: '2026-06-22',
    window_end: '2026-09-20',
    calculation_version: 'supplier-risk-v2',
    currency_buckets: [],
    price_comparisons: [],
    baseline_count: 4,
    current_count: 4,
    baseline_reliability: null,
    current_reliability: null,
    numerator: '2.0000',
    denominator: '8.0000',
    ...overrides,
  });

  const scorecard = (overrides: Partial<SupplierScorecard> = {}): SupplierScorecard => ({
    supplier_id: 'supplier-001',
    window_start: '2026-03-24',
    window_end: '2026-09-20',
    metrics: {},
    risk_score: {
      total: '0.4200',
      confidence: 'medium',
      sub_scores: [],
      rule_version: 'supplier-risk-v1',
    },
    source_counts: {},
    confidence: 'medium',
    insufficient_evidence: false,
    computed_at: '2026-09-20T12:00:00Z',
    rule_version: 'supplier-scorecard-v1',
    snapshot_id: 'snapshot-001',
    state: 'provisional',
    risk_level: 'medium',
    release_posture: 'g3_unmet',
    valid_from: '2026-09-20T12:00:00Z',
    valid_until: '2099-09-21T12:00:00Z',
    observed_history_days: 180,
    v2_risk_score: '0.4200',
    v2_weights: {
      concentration: '0.3000',
      price_drift: '0.2500',
      reliability: '0.2500',
      single_source: '0.2000',
    },
    v2_components: {
      concentration: component('0.5000', {
        currency_buckets: [
          {
            currency: 'GBP',
            supplier_spend: '420.0000',
            tenant_spend: '1000.0000',
            sample_count: 3,
            share: '0.4200',
            source_ids: ['order-001'],
          },
          {
            currency: 'USD',
            supplier_spend: '200.0000',
            tenant_spend: '500.0000',
            sample_count: 5,
            share: '0.4000',
            source_ids: ['order-002'],
          },
        ],
      }),
      price_drift: component('0.3000'),
      reliability: component('0.2500'),
      single_source: component('0.6000', {
        source_refs: [
          { source_id: 'product-001', source_kind: 'workspace_product' as const },
        ],
      }),
    },
    source_fingerprint: 'fingerprint-001',
    ...overrides,
  });

  beforeEach(async () => {
    api = jasmine.createSpyObj<SupplierRiskApiService>('SupplierRiskApiService', [
      'prepareBrief',
    ]);
    api.prepareBrief.and.returnValue(
      of({
        id: 'brief-001',
        supplier_id: 'supplier-001',
        snapshot_id: 'snapshot-001',
        brief_version: 'negotiation-brief-v1',
        source_fingerprint: 'fingerprint-001',
        release_posture: 'g3_unmet',
        valid_from: '2026-09-20T12:00:00Z',
        valid_until: '2099-09-21T12:00:00Z',
        status: 'prepared',
        items: [],
      }),
    );
    session = jasmine.createSpyObj<SessionService>('SessionService', ['hasRole'], {
      isAuthenticated: signal(false),
      activeLocale: signal<'en' | 'ar'>('en'),
    });
    session.hasRole.and.returnValue(true);

    await TestBed.configureTestingModule({
      imports: [ScorecardV2PanelComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SupplierRiskApiService, useValue: api },
        { provide: SessionService, useValue: session },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ScorecardV2PanelComponent);
    fixture.componentRef.setInput('scorecard', scorecard());
    fixture.componentRef.setInput('supplierId', 'supplier-001');
    router = TestBed.inject(Router);
  });

  it('renders four components, currency buckets, calculations, exclusions, and source links', () => {
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;

    expect(fixture.nativeElement.querySelectorAll('[data-testid="risk-component-row"]').length).toBe(4);
    expect(text).toContain('supplierRisk.components.concentration');
    expect(text).toContain('supplierRisk.components.price_drift');
    expect(text).toContain('supplierRisk.components.reliability');
    expect(text).toContain('supplierRisk.components.single_source');
    expect(text).toContain('GBP');
    expect(text).toContain('USD');
    expect(text).toContain('cancelled');
    expect(fixture.nativeElement.querySelector('a[href="/orders/order-001"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('a[href="/products/product-001"]')).not.toBeNull();
  });

  it('keeps provisional, G3, and stale states visible', () => {
    fixture.componentRef.setInput(
      'scorecard',
      scorecard({ valid_until: '2020-01-01T00:00:00Z' }),
    );
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('supplierRisk.state.provisional');
    expect(text).toContain('supplierRisk.posture.g3_unmet');
    expect(text).toContain('supplierRisk.validity.stale');
    expect(fixture.nativeElement.querySelector('[data-testid="prepare-brief"]')).toBeNull();
  });

  it('suppresses preparation when evidence is insufficient', () => {
    fixture.componentRef.setInput(
      'scorecard',
      scorecard({ state: 'insufficient_data', v2_risk_score: null }),
    );
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('supplierRisk.state.insufficient_data');
    expect(fixture.nativeElement.querySelector('[data-testid="prepare-brief"]')).toBeNull();
  });

  it('prepares an eligible brief once and navigates to its detail', () => {
    spyOn(router, 'navigate').and.resolveTo(true);
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('[data-testid="prepare-brief"]');
    button.click();
    fixture.detectChanges();

    expect(api.prepareBrief).toHaveBeenCalledOnceWith('supplier-001');
    expect(router.navigate).toHaveBeenCalledOnceWith(['/negotiation-briefs', 'brief-001']);
  });

  it('keeps preparation visible and disabled while the request is in flight', () => {
    const pending = new Subject<NegotiationBrief>();
    api.prepareBrief.and.returnValue(pending);
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector(
      '[data-testid="prepare-brief"]',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    button.click();

    expect(button.disabled).toBeTrue();
    expect(api.prepareBrief).toHaveBeenCalledTimes(1);
  });

  it('keeps non-writers read-only', () => {
    session.hasRole.and.returnValue(false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="prepare-brief"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="scorecard-v2-readonly"]')).not.toBeNull();
  });
});
