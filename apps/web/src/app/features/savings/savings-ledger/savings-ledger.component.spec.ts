import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
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
      baseline_policy: 'last_paid',
      baseline_source_landed_cost_ids: ['lc-1'],
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
      imports: [SavingsLedgerComponent, TranslateModule.forRoot()],
      providers: [
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
    component.onFilterChange();

    expect(mockSavingsApiService.getSavings).toHaveBeenCalledWith(
      jasmine.objectContaining({ status: 'verified' }),
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
