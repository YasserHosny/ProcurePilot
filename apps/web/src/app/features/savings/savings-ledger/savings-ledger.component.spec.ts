import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { SavingsLedgerComponent } from './savings-ledger.component';
import { type SavingRecord, SavingsApiService } from '../savings-api';

describe('SavingsLedgerComponent (T022)', () => {
  let component: SavingsLedgerComponent;
  let fixture: ComponentFixture<SavingsLedgerComponent>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockSavingsApiService: jasmine.SpyObj<SavingsApiService>;
  let mockSessionService: Record<string, unknown>;

  const sampleSavings: SavingRecord[] = [
    {
      id: 'sav-1',
      purchase_record_id: 'pur-1',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      status: 'verified',
      baseline_policy: 'last_po_price',
      baseline_source_landed_cost_ids: [],
      baseline_source_po_line_ids: ['pol-1'],
      baseline_unit_price: { amount: '10.0000', currency: 'GBP' },
      baseline_value: { amount: '100.0000', currency: 'GBP' },
      actual_value: { amount: '80.0000', currency: 'GBP' },
      delta: { amount: '20.0000', currency: 'GBP' },
      calculation_version: 'saving-baseline-v1',
      calculation_inputs: {},
      recorded_by: 'user-1',
      recorded_at: '2026-08-21T10:00:00Z',
      verified_by: 'user-1',
      verified_at: '2026-08-21T11:00:00Z',
    },
    {
      id: 'sav-2',
      purchase_record_id: 'pur-2',
      workspace_product_id: 'prod-2',
      supplier_id: 'supp-2',
      status: 'pending',
      baseline_policy: 'last_paid',
      baseline_source_landed_cost_ids: ['lc-2'],
      baseline_unit_price: { amount: '15.0000', currency: 'GBP' },
      baseline_value: { amount: '150.0000', currency: 'GBP' },
      actual_value: { amount: '160.0000', currency: 'GBP' },
      delta: { amount: '-10.0000', currency: 'GBP' },
      calculation_version: 'saving-baseline-v1',
      calculation_inputs: {},
      recorded_by: 'user-2',
      recorded_at: '2026-08-21T10:30:00Z',
    },
  ];

  beforeEach(async () => {
    mockApiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'products',
      'suppliers',
    ]);
    mockSavingsApiService = jasmine.createSpyObj<SavingsApiService>('SavingsApiService', [
      'getSavings',
    ]);
    mockSessionService = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    mockApiService.products.and.returnValue(
      of({ items: [{ id: 'prod-1', tenant_name: 'Product One', canonical_name: 'product-one', base_unit: 'each', pack: { pack_count: 1, unit_size: '1' }, status: 'active' as const, created_at: '' }], next_cursor: null }),
    );
    mockApiService.suppliers.and.returnValue(
      of({ items: [{ id: 'supp-1', name: 'Supplier One', status: 'active' as const, created_at: '' }], next_cursor: null }),
    );
    mockSavingsApiService.getSavings.and.returnValue(of({ items: sampleSavings, next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [SavingsLedgerComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: mockApiService },
        { provide: SavingsApiService, useValue: mockSavingsApiService },
        { provide: SessionService, useValue: mockSessionService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(SavingsLedgerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load savings ledger list', () => {
    expect(component).toBeTruthy();
    expect(mockSavingsApiService.getSavings).toHaveBeenCalled();
    expect(component.savings().length).toBe(2);
    expect(component.verifiedSavingsCount()).toBe(1);
    expect(component.pendingSavingsCount()).toBe(1);
    expect(component.totalVerifiedAmount()).toEqual({ amount: '20.00', currency: 'GBP' });
  });

  it('shows the baseline policy under each baseline value', () => {
    const labels = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('[data-testid="baseline-policy"]'),
    ).map((el) => el.textContent?.trim());
    expect(labels).toEqual([
      'savings.evidence.baselinePolicies.last_po_price',
      'savings.evidence.baselinePolicies.last_paid',
    ]);
    expect(component.getPolicyClass('last_po_price')).toBe('policy-last-po');
  });

  it('never labels a pending delta as verified', () => {
    const el = fixture.nativeElement as HTMLElement;
    const header = el.querySelector('th.mat-column-delta')?.textContent?.trim();
    expect(header).toBe('savings.ledger.table.delta');

    const badges = Array.from(el.querySelectorAll<HTMLElement>('[data-testid="saving-delta"]'));
    expect(badges.length).toBe(2);
    const [verified, pending] = badges;
    expect(verified.classList).not.toContain('delta-pending');
    expect(verified.querySelector('[data-testid="delta-pending-hint"]')).toBeNull();
    expect(pending.classList).toContain('delta-pending');
    expect(pending.querySelector('[data-testid="delta-pending-hint"]')?.textContent?.trim()).toBe(
      'savings.ledger.table.deltaPendingHint',
    );
  });

  it('should visually differentiate pending vs verified status', () => {
    const verifiedStatus = component.getStatusClass('verified');
    const pendingStatus = component.getStatusClass('pending');
    expect(verifiedStatus).toBe('status-verified');
    expect(pendingStatus).toBe('status-pending');
  });

  it('should correctly determine delta classes for positive and negative savings', () => {
    expect(component.getDeltaClass(sampleSavings[0].delta)).toBe('positive-delta');
    expect(component.getDeltaClass(sampleSavings[1].delta)).toBe('negative-delta');
    expect(component.isPositive(sampleSavings[0].delta)).toBeTrue();
    expect(component.isNegative(sampleSavings[1].delta)).toBeTrue();
  });

  it('should reload data when filters change', () => {
    mockSavingsApiService.getSavings.calls.reset();
    component.statusFilter.set('verified');
    component.periodStartDate.set(new Date(2026, 9, 20));
    component.periodEndDate.set(new Date(2026, 9, 21));
    component.onFilterChange();

    expect(mockSavingsApiService.getSavings).toHaveBeenCalledWith(
      jasmine.objectContaining({ status: 'verified', period_start: '2026-10-20', period_end: '2026-10-21' }),
    );
  });

  it('should handle error when loading savings', () => {
    mockSavingsApiService.getSavings.and.returnValue(
      throwError(() => ({ error: { message: 'Failed to fetch', trace_id: 'tr-123' } })),
    );

    component.loadSavings();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBe('Failed to fetch');
    expect(component.errorTraceId()).toBe('tr-123');
  });
});
