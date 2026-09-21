import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../../core/auth/session.service';
import {
  BriefItemKind,
  NegotiationBrief,
  NegotiationBriefItem,
  SupplierRiskApiService,
} from '../supplier-risk-api';
import { BriefDetailComponent } from './brief-detail.component';

describe('BriefDetailComponent', () => {
  let fixture: ComponentFixture<BriefDetailComponent>;
  let component: BriefDetailComponent;
  let api: jasmine.SpyObj<SupplierRiskApiService>;
  let session: jasmine.SpyObj<SessionService>;
  let routeParams$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  const questionKeys: Record<BriefItemKind, string> = {
    price_trajectory: 'negotiationBrief.priceTrajectory.question',
    alternatives: 'negotiationBrief.alternatives.question',
    service_performance: 'negotiationBrief.servicePerformance.question',
    concentration_volume: 'negotiationBrief.concentrationVolume.question',
    payment_context: 'negotiationBrief.paymentContext.question',
    purchase_pattern: 'negotiationBrief.purchasePattern.question',
  };

  const item = (kind: BriefItemKind, rank: number): NegotiationBriefItem => ({
    kind,
    rank,
    value: '0.4200',
    amount: kind === 'concentration_volume' ? { amount: '420.0000', currency: 'GBP' } : null,
    confidence: 'medium',
    risk: '0.4200',
    valid_from: '2026-03-24',
    valid_until: '2099-09-21',
    question_i18n_key: questionKeys[kind],
    calculation_version: 'negotiation-brief-v1',
    metric_id: `metric-${rank}`,
    evidence_ids: [`evidence-${rank}`],
    evidence: [
      {
        evidence_id: `evidence-${rank}`,
        source_kind: 'purchase_order',
        source_id: `order-${rank}`,
      },
    ],
  });

  const kinds: BriefItemKind[] = [
    'price_trajectory',
    'alternatives',
    'service_performance',
    'concentration_volume',
    'payment_context',
    'purchase_pattern',
  ];

  const brief = (overrides: Partial<NegotiationBrief> = {}): NegotiationBrief => ({
    id: 'brief-001',
    supplier_id: 'supplier-001',
    snapshot_id: 'snapshot-001',
    brief_version: 'negotiation-brief-v1',
    source_fingerprint: 'fingerprint-001',
    release_posture: 'g3_unmet',
    valid_from: '2026-09-20T12:00:00Z',
    valid_until: '2099-09-21T12:00:00Z',
    status: 'prepared',
    items: kinds.map((kind, index) => item(kind, index + 1)),
    ...overrides,
  });

  beforeEach(async () => {
    api = jasmine.createSpyObj<SupplierRiskApiService>('SupplierRiskApiService', [
      'getBrief',
      'acknowledgeBrief',
      'dismissBrief',
    ]);
    api.getBrief.and.returnValue(of(brief()));
    api.acknowledgeBrief.and.returnValue(of(brief({ status: 'acknowledged' })));
    api.dismissBrief.and.returnValue(of(brief({ status: 'dismissed' })));
    session = jasmine.createSpyObj<SessionService>('SessionService', ['hasRole'], {
      isAuthenticated: signal(false),
      activeLocale: signal<'en' | 'ar'>('en'),
    });
    session.hasRole.and.returnValue(true);
    routeParams$ = new BehaviorSubject(convertToParamMap({ id: 'brief-001' }));

    await TestBed.configureTestingModule({
      imports: [BriefDetailComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SupplierRiskApiService, useValue: api },
        { provide: SessionService, useValue: session },
        { provide: ActivatedRoute, useValue: { paramMap: routeParams$.asObservable() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(BriefDetailComponent);
    component = fixture.componentInstance;
  });

  it('renders one ranked item per category with calculations and localized question keys', () => {
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;

    expect(fixture.nativeElement.querySelectorAll('[data-testid="brief-item"]').length).toBe(6);
    for (const kind of kinds) {
      expect(text).toContain(`negotiationBrief.kinds.${kind}`);
      expect(text).toContain(questionKeys[kind]);
    }
    expect(text).toContain('GBP');
    expect(fixture.nativeElement.querySelector('a[href="/orders/order-1"]')).not.toBeNull();
  });

  it('keeps G3 posture and stale validity visible', () => {
    api.getBrief.and.returnValue(of(brief({ valid_until: '2020-01-01T00:00:00Z' })));
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('negotiationBrief.posture.g3_unmet');
    expect(fixture.nativeElement.querySelector('[data-testid="brief-stale"]')).not.toBeNull();
  });

  it('acknowledges a prepared brief once and disables replay actions', () => {
    fixture.detectChanges();
    fixture.nativeElement.querySelector('[data-testid="acknowledge-brief"]').click();
    fixture.detectChanges();

    expect(api.acknowledgeBrief).toHaveBeenCalledOnceWith('brief-001');
    expect(component.brief()?.status).toBe('acknowledged');
    expect(fixture.nativeElement.querySelector('[data-testid="acknowledge-brief"]')).toBeNull();
  });

  it('keeps review actions disabled while an append is in flight', () => {
    const pending = new Subject<NegotiationBrief>();
    api.acknowledgeBrief.and.returnValue(pending);
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector(
      '[data-testid="acknowledge-brief"]',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    component.acknowledge();

    expect(button.disabled).toBeTrue();
    expect(api.acknowledgeBrief).toHaveBeenCalledTimes(1);
  });

  it('requires a dismissal reason before calling the API', () => {
    fixture.detectChanges();
    component.dismiss();
    expect(api.dismissBrief).not.toHaveBeenCalled();
    expect(component.dismissReasonError()).toBeTrue();

    component.dismissReason.set('Supplier evidence needs correction');
    component.dismiss();
    fixture.detectChanges();
    expect(api.dismissBrief).toHaveBeenCalledOnceWith(
      'brief-001',
      'Supplier evidence needs correction',
    );
    expect(component.brief()?.status).toBe('dismissed');
  });

  it('keeps non-writers read-only', () => {
    session.hasRole.and.returnValue(false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="brief-readonly"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="brief-actions"]')).toBeNull();
  });

  it('shows an error without stale content when loading fails', () => {
    api.getBrief.and.returnValue(throwError(() => new Error('offline')));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="brief-item"]')).toBeNull();
  });
});
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
