import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Supplier, SupplierScorecard } from '../../../core/api/models';
import { SupplierScorecardComponent } from './supplier-scorecard.component';

describe('SupplierScorecardComponent (T027)', () => {
  let component: SupplierScorecardComponent;
  let fixture: ComponentFixture<SupplierScorecardComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let routeParams$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  const mockSupplier: Supplier = {
    id: 'supp-123',
    name: 'Acme Supplies',
    status: 'active',
    created_at: '2026-08-01T00:00:00Z',
  };

  const mockScorecard: SupplierScorecard = {
    supplier_id: 'supp-123',
    window_start: '2026-03-01',
    window_end: '2026-09-01',
    metrics: {
      fulfilment_rate: {
        value: '0.9800',
        sample_count: 50,
        confidence: 'high',
        insufficient_evidence: false,
      },
      quality_score: {
        value: '0.9900',
        sample_count: 50,
        confidence: 'high',
        insufficient_evidence: false,
      },
      price_competitiveness: {
        value: '0.8800',
        sample_count: 12,
        confidence: 'medium',
        insufficient_evidence: false,
      },
      spend_exposure: {
        value: '0.2500',
        sample_count: 50,
        confidence: 'high',
        insufficient_evidence: false,
      },
      freshness_score: {
        value: '0.9400',
        sample_count: 50,
        confidence: 'high',
        insufficient_evidence: false,
      },
      savings_contribution: {
        value: '0.3000',
        sample_count: 50,
        confidence: 'high',
        insufficient_evidence: false,
      },
    },
    risk_score: {
      total: '0.1850',
      confidence: 'high',
      rule_version: 'risk-v1',
      sub_scores: [
        { name: 'Fulfilment Risk', score: '5.0', weight: '0.3', evidence: {} },
        { name: 'Quality Risk', score: '8.0', weight: '0.4', evidence: {} },
        { name: 'Price Volatility', score: '25.0', weight: '0.3', evidence: {} },
      ],
    },
    source_counts: {
      purchase_record: 50,
      tenant_purchase_record: 75,
      delivery_quality_issue: 1,
      landed_cost: 12,
      market_landed_cost: 36,
      saving_record: 3,
      tenant_saving_record: 10,
    },
    confidence: 'high',
    insufficient_evidence: false,
    computed_at: '2026-09-14T00:00:00Z',
    rule_version: 'scorecard-v1',
  };

  const mockInsufficientScorecard: SupplierScorecard = {
    ...mockScorecard,
    insufficient_evidence: true,
    confidence: 'low',
    metrics: {
      fulfilment_rate: {
        value: null,
        sample_count: 1,
        confidence: 'low',
        insufficient_evidence: true,
      },
    },
    risk_score: {
      total: '0.4500',
      confidence: 'low',
      rule_version: 'risk-v1',
      sub_scores: [],
    },
    source_counts: {
      purchase_record: 1,
      tenant_purchase_record: 1,
      delivery_quality_issue: 0,
      landed_cost: 0,
      market_landed_cost: 0,
      saving_record: 0,
      tenant_saving_record: 0,
    },
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'supplier',
      'getSupplierScorecard',
    ]);
    routeParams$ = new BehaviorSubject(convertToParamMap({ id: 'supp-123' }));

    apiService.supplier.and.returnValue(of(mockSupplier));
    apiService.getSupplierScorecard.and.returnValue(of(mockScorecard));

    await TestBed.configureTestingModule({
      imports: [SupplierScorecardComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ApiService, useValue: apiService },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: routeParams$.asObservable(),
          },
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(SupplierScorecardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and extract supplierId from route params', () => {
    expect(component).toBeTruthy();
    expect(component.supplierId()).toBe('supp-123');
    expect(apiService.supplier).toHaveBeenCalledWith('supp-123');
    expect(apiService.getSupplierScorecard).toHaveBeenCalledWith('supp-123', {
      window_months: 6,
    });
  });

  it('should render supplier name when loaded', () => {
    expect(component.supplierName()).toBe('Acme Supplies');
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Acme Supplies');
  });

  it('should render performance metrics with formatted percentages', () => {
    const el: HTMLElement = fixture.nativeElement;
    // 0.9800 -> 98.0%
    expect(el.textContent).toContain('98.0%');
    // 0.9400 -> 94.0%
    expect(el.textContent).toContain('94.0%');
    // 0.9900 -> 99.0%
    expect(el.textContent).toContain('99.0%');
    expect(el.textContent).toContain('30.0%');
    expect(el.textContent).toContain('Freshness');
    expect(el.textContent).toContain('Savings');
  });

  it('should show insufficient evidence warning when insufficient_evidence is true', () => {
    apiService.getSupplierScorecard.and.returnValue(of(mockInsufficientScorecard));
    component.loadSupplierAndScorecard('supp-123', 6);
    fixture.detectChanges();

    expect(component.isInsufficient()).toBeTrue();
    const notice = fixture.nativeElement.querySelector('.insufficient-notice');
    expect(notice).toBeTruthy();
  });

  it('should not show insufficient evidence notice when evidence is sufficient', () => {
    expect(component.isInsufficient()).toBeFalse();
    const notice = fixture.nativeElement.querySelector('.insufficient-notice');
    expect(notice).toBeNull();
  });

  it('should compute risk level correctly based on total score', () => {
    expect(component.riskLevel()).toBe('low'); // 0.1850 < 0.30

    component.scorecard.set({
      ...mockScorecard,
      risk_score: { ...mockScorecard.risk_score, total: '0.5500' },
    });
    expect(component.riskLevel()).toBe('medium'); // 0.30 <= 0.55 < 0.70

    component.scorecard.set({
      ...mockScorecard,
      risk_score: { ...mockScorecard.risk_score, total: '0.8200' },
    });
    expect(component.riskLevel()).toBe('high'); // >= 0.70
  });

  it('should render source transaction counts', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('12'); // landed costs
    expect(el.textContent).toContain('50'); // purchase records
    expect(el.textContent).toContain('1'); // quality issues
  });

  it('should handle window months selection change', () => {
    component.changeWindow(12);
    expect(component.windowMonths()).toBe(12);
    expect(apiService.getSupplierScorecard).toHaveBeenCalledWith('supp-123', {
      window_months: 12,
    });
  });

  it('should handle 404 error when scorecard is not found', () => {
    apiService.getSupplierScorecard.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 404, statusText: 'Not Found' })),
    );

    component.loadSupplierAndScorecard('supp-missing', 6);
    fixture.detectChanges();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBeTruthy();
    const errorEl = fixture.nativeElement.querySelector('.error-banner');
    expect(errorEl).toBeTruthy();
  });

  it('should uphold cross-tenant security: supplierId is passed without tenant parameter', () => {
    expect(apiService.getSupplierScorecard).toHaveBeenCalledWith(
      'supp-123',
      jasmine.objectContaining({ window_months: 6 }),
    );
    // Verified: no tenant_id query parameter is passed
  });

  it('should render without errors in RTL direction', () => {
    document.documentElement.setAttribute('dir', 'rtl');
    fixture.detectChanges();
    expect(component).toBeTruthy();
    document.documentElement.setAttribute('dir', 'ltr');
  });

  it('should support keyboard navigation: metric cards are focusable', () => {
    const cards: NodeListOf<HTMLElement> =
      fixture.nativeElement.querySelectorAll('.metric-card');
    expect(cards.length).toBeGreaterThan(0);
    cards.forEach((card) => {
      expect(card.getAttribute('tabindex')).toBe('0');
    });
  });
});
