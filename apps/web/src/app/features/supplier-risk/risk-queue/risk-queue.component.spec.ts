import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { Subject, of, throwError } from 'rxjs';

import { SessionService } from '../../../core/auth/session.service';
import {
  SupplierRiskApiService,
  SupplierRiskList,
  SupplierRiskSnapshot,
} from '../supplier-risk-api';
import { RiskQueueComponent } from './risk-queue.component';

describe('RiskQueueComponent', () => {
  let fixture: ComponentFixture<RiskQueueComponent>;
  let component: RiskQueueComponent;
  let api: jasmine.SpyObj<SupplierRiskApiService>;
  let session: jasmine.SpyObj<SessionService>;

  const snapshot = (
    overrides: Partial<SupplierRiskSnapshot> = {},
  ): SupplierRiskSnapshot => ({
    id: 'snapshot-001',
    supplier_id: 'supplier-001',
    supplier_name: 'Alfaisal Trade',
    window_start: '2026-03-24',
    window_end: '2026-09-20',
    state: 'ready',
    confidence: 'high',
    release_posture: 'g3_unmet',
    valid_from: '2026-09-20T00:00:00Z',
    valid_until: '2099-09-21T00:00:00Z',
    source_fingerprint: 'fingerprint-001',
    observed_history_days: 180,
    risk_score: {
      total: '0.7200',
      components: {
        concentration: '0.7200',
        price_drift: '0.4100',
        reliability: '0.2500',
        single_source: '0.6000',
      },
      weights: {
        concentration: '0.3000',
        price_drift: '0.2500',
        reliability: '0.3000',
        single_source: '0.1500',
      },
    },
    risk_level: 'high',
    computed_at: '2026-09-20T12:00:00Z',
    ...overrides,
  });

  const page = (
    items: SupplierRiskSnapshot[],
    nextCursor: string | null = null,
  ): SupplierRiskList => ({ items, next_cursor: nextCursor });

  beforeEach(async () => {
    api = jasmine.createSpyObj<SupplierRiskApiService>('SupplierRiskApiService', [
      'listRisks',
      'recompute',
    ]);
    session = jasmine.createSpyObj<SessionService>(
      'SessionService',
      ['hasRole'],
      {
        isAuthenticated: signal(false),
        activeLocale: signal<'en' | 'ar'>('en'),
      },
    );
    session.hasRole.and.returnValue(true);
    api.listRisks.and.returnValue(of(page([snapshot()])));
    api.recompute.and.returnValue(
      of({ generated_snapshots: 1, release_posture: 'g3_unmet' }),
    );

    await TestBed.configureTestingModule({
      imports: [RiskQueueComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SupplierRiskApiService, useValue: api },
        { provide: SessionService, useValue: session },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(RiskQueueComponent);
    component = fixture.componentInstance;
  });

  it('shows loading, error, and empty states', () => {
    const pending = new Subject<SupplierRiskList>();
    api.listRisks.and.returnValue(pending);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="risk-loading"]')).not.toBeNull();

    pending.error(new Error('offline'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="risk-empty"]')).toBeNull();

    api.listRisks.and.returnValue(of(page([])));
    component.loadRisks(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="risk-empty"]')).not.toBeNull();
  });

  it('renders the latest risk, confidence, posture, driver, and scorecard link', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;

    expect(text).toContain('Alfaisal Trade');
    expect(text).toContain('supplierRisk.level.high');
    expect(text).toContain('supplierRisk.confidence.high');
    expect(text).toContain('supplierRisk.posture.g3_unmet');
    expect(text).toContain('supplierRisk.drivers.concentration');
    const link = fixture.nativeElement.querySelector('a.scorecard-link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/suppliers/supplier-001/scorecard');
  });

  it('makes insufficient and stale states explicit', async () => {
    api.listRisks.and.returnValue(
      of(
        page([
          snapshot({
            state: 'insufficient_data',
            confidence: 'low',
            risk_level: null,
            risk_score: { total: null, components: {}, weights: {} },
            valid_until: '2020-01-01T00:00:00Z',
          }),
        ]),
      ),
    );
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'supplierRisk.state.insufficient_data',
    );
    expect(fixture.nativeElement.querySelector('[data-testid="validity-stale"]')).not.toBeNull();
  });

  it('renders every scored risk band', () => {
    api.listRisks.and.returnValue(
      of(
        page([
          snapshot({ id: 'low', supplier_id: 'low', risk_level: 'low' }),
          snapshot({ id: 'medium', supplier_id: 'medium', risk_level: 'medium' }),
          snapshot({ id: 'high', supplier_id: 'high', risk_level: 'high' }),
        ]),
      ),
    );
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('supplierRisk.level.low');
    expect(text).toContain('supplierRisk.level.medium');
    expect(text).toContain('supplierRisk.level.high');
  });

  it('appends the next cursor page without replacing current suppliers', () => {
    api.listRisks.and.returnValues(
      of(page([snapshot()], 'cursor-2')),
      of(
        page([
          snapshot({
            id: 'snapshot-002',
            supplier_id: 'supplier-002',
            supplier_name: 'Nile Supplies',
            risk_level: 'low',
          }),
        ]),
      ),
    );
    fixture.detectChanges();

    component.loadMore();
    fixture.detectChanges();

    expect(api.listRisks.calls.allArgs()).toEqual([
      [undefined, 50],
      ['cursor-2', 50],
    ]);
    expect(fixture.nativeElement.textContent).toContain('Alfaisal Trade');
    expect(fixture.nativeElement.textContent).toContain('Nile Supplies');
  });

  it('allows owners and buyers to recompute and then refreshes the queue', () => {
    api.listRisks.and.returnValues(of(page([snapshot()])), of(page([snapshot()])));
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector(
      '[data-testid="recompute-risks"]',
    ) as HTMLButtonElement;
    button.click();
    fixture.detectChanges();

    expect(api.recompute).toHaveBeenCalledTimes(1);
    expect(api.listRisks).toHaveBeenCalledTimes(2);
    expect(fixture.nativeElement.textContent).toContain('supplierRisk.recompute.success');
  });

  it('keeps non-writers read-only', () => {
    session.hasRole.and.returnValue(false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="recompute-risks"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="risk-readonly"]')).not.toBeNull();
    expect(api.recompute).not.toHaveBeenCalled();
  });

  it('surfaces recompute failures without dropping the current queue', () => {
    api.recompute.and.returnValue(throwError(() => new Error('service unavailable')));
    fixture.detectChanges();

    component.recompute();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Alfaisal Trade');
  });

  it('renders in RTL direction', () => {
    document.documentElement.setAttribute('dir', 'rtl');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.risk-queue')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Alfaisal Trade');
    document.documentElement.setAttribute('dir', 'ltr');
  });
});
