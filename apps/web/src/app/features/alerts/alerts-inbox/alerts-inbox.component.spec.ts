import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { Alert } from '../alerts-api';
import { AlertsInboxComponent } from './alerts-inbox.component';

describe('AlertsInboxComponent (US4, T061)', () => {
  let component: AlertsInboxComponent;
  let fixture: ComponentFixture<AlertsInboxComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let router: Router;

  const mockAlerts: Alert[] = [
    {
      id: 'fp-expiring-1',
      kind: 'recommended_price_expiring',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      severity: 'warning',
      evidence: { valid_to: '2026-08-25T00:00:00Z' },
      action: 'compare_product',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-disappeared-2',
      kind: 'preferred_supplier_offer_disappeared',
      workspace_product_id: 'prod-2',
      supplier_id: 'supp-2',
      severity: 'critical',
      evidence: {},
      action: 'review_supplier',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-swing-3',
      kind: 'price_swing',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      severity: 'info',
      evidence: {
        current_price: { amount: '15.0000', currency: 'GBP' },
        swing_percent: '25.0',
        average_price: { amount: '12.0000', currency: 'GBP' },
      },
      action: 'view_price_history',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-spike-4',
      kind: 'price_spike',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      severity: 'critical',
      confidence: 'high',
      evidence: {
        current_normalised_unit_price: { amount: '18.0000', currency: 'GBP' },
        rolling_average: { amount: '12.0000', currency: 'GBP' },
        spike_percentage: '50.00',
      },
      action: 'view_price_history',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-dup-5',
      kind: 'likely_duplicate_quotation_line',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      severity: 'warning',
      confidence: 'high',
      evidence: {
        quotation_id_1: 'quot-101',
        quotation_line_id_1: 'line-1',
        quotation_line_id_2: 'line-2',
        unit_price: { amount: '5.5000', currency: 'GBP' },
        requested_quantity_1: '10.000000',
      },
      action: 'review_quotation',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-quality-6',
      kind: 'supplier_quality_trend_change',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      severity: 'critical',
      confidence: 'high',
      evidence: {
        dispute_rate: '0.1200',
        quality_score: '0.6500',
        incident_count: 2,
      },
      action: 'inspect_scorecard',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
    {
      id: 'fp-delivery-7',
      kind: 'delivery_cost_anomaly',
      workspace_product_id: 'prod-2',
      supplier_id: 'supp-2',
      severity: 'warning',
      confidence: 'high',
      evidence: {
        delivery_fee: '45.00',
        minimum_order_value: '100.00',
        fee_ratio: '0.4500',
        currency: 'GBP',
      },
      action: 'view_delivery_issues',
      created_from_current_data_at: '2026-08-21T09:00:00Z',
      dismissed: false,
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'getAlerts',
      'dismissAlert',
      'products',
      'suppliers',
    ]);

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    apiService.getAlerts.and.returnValue(of({ items: mockAlerts, next_cursor: null }));
    apiService.dismissAlert.and.returnValue(
      of({ alert_id: 'fp-expiring-1', dismissed_at: '2026-08-21T10:00:00Z' }),
    );
    apiService.products.and.returnValue(
      of({
        items: [
          {
            id: 'prod-1',
            tenant_name: 'Semi-Skimmed Milk 2L',
            canonical_name: 'Milk',
            base_unit: 'L',
            pack: { pack_count: 1, unit_size: '2' },
            status: 'active',
            created_at: '2026-08-01T00:00:00Z',
          },
          {
            id: 'prod-2',
            tenant_name: 'Salted Butter 250g',
            canonical_name: 'Butter',
            base_unit: 'KG',
            pack: { pack_count: 1, unit_size: '0.25' },
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
          { id: 'supp-1', name: 'Supplier Alpha', status: 'active', created_at: '2026-08-01T00:00:00Z' },
          { id: 'supp-2', name: 'Supplier Beta', status: 'active', created_at: '2026-08-01T00:00:00Z' },
        ],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [AlertsInboxComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    fixture = TestBed.createComponent(AlertsInboxComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and load live alerts', () => {
    expect(component).toBeTruthy();
    expect(apiService.getAlerts).toHaveBeenCalled();
    expect(component.alerts().length).toBe(7);
  });

  it('should filter alerts by kind', () => {
    component.onKindFilterChange('recommended_price_expiring');
    expect(apiService.getAlerts).toHaveBeenCalledWith({
      kind: 'recommended_price_expiring',
    });
  });

  it('should filter alerts by anomaly kind', () => {
    component.onKindFilterChange('price_spike');
    expect(apiService.getAlerts).toHaveBeenCalledWith({
      kind: 'price_spike',
    });
  });

  it('should dismiss an alert and remove it from view', () => {
    const alertToDismiss = mockAlerts[0];
    component.dismissAlert(alertToDismiss);
    expect(apiService.dismissAlert).toHaveBeenCalledWith('fp-expiring-1');
    expect(component.alerts().find((a) => a.id === 'fp-expiring-1')).toBeUndefined();
    expect(component.alerts().length).toBe(6);
  });

  it('should route compare_product action to compare screen', () => {
    component.onActionClick(mockAlerts[0]);
    expect(router.navigate).toHaveBeenCalledWith(['/offers/compare', 'prod-1'], {
      queryParams: { product_id: 'prod-1' },
    });
  });

  it('should route review_supplier action to suppliers screen', () => {
    component.onActionClick(mockAlerts[1]);
    expect(router.navigate).toHaveBeenCalledWith(['/suppliers', 'supp-2']);
  });

  it('should route view_price_history action to product intelligence screen', () => {
    component.onActionClick(mockAlerts[2]);
    expect(router.navigate).toHaveBeenCalledWith(['/offers/product-intelligence', 'prod-1'], {
      queryParams: { product_id: 'prod-1', supplier_id: 'supp-1' },
    });
  });

  it('should route inspect_scorecard action to supplier scorecard screen', () => {
    const qualityAlert = mockAlerts.find((a) => a.action === 'inspect_scorecard')!;
    component.onActionClick(qualityAlert);
    expect(router.navigate).toHaveBeenCalledWith(['/suppliers', 'supp-1', 'scorecard']);
  });

  it('should route review_quotation action to quotation review screen', () => {
    const dupAlert = mockAlerts.find((a) => a.action === 'review_quotation')!;
    component.onActionClick(dupAlert);
    expect(router.navigate).toHaveBeenCalledWith(['/quotations', 'quot-101', 'review']);
  });

  it('should route view_delivery_issues action to supplier scorecard screen', () => {
    const deliveryAlert = mockAlerts.find((a) => a.action === 'view_delivery_issues')!;
    component.onActionClick(deliveryAlert);
    expect(router.navigate).toHaveBeenCalledWith(['/suppliers', 'supp-2', 'scorecard']);
  });

  it('should render empty all-clear state when no alerts exist', () => {
    component.alerts.set([]);
    fixture.detectChanges();

    expect(component.filteredAlerts().length).toBe(0);
  });
});
