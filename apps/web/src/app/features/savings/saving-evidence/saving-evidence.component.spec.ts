import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { SavingEvidenceComponent } from './saving-evidence.component';
import { type SavingEvidence, SavingsApiService } from '../savings-api';

describe('SavingEvidenceComponent (T022, T033)', () => {
  let component: SavingEvidenceComponent;
  let fixture: ComponentFixture<SavingEvidenceComponent>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockSavingsApiService: jasmine.SpyObj<SavingsApiService>;
  let mockSessionService: Record<string, unknown>;

  const pendingEvidence: SavingEvidence = {
    saving_record: {
      id: 'sav-1',
      purchase_record_id: 'pur-1',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      status: 'pending',
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
    },
    purchase_record: {
      id: 'pur-1',
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      quantity: '10',
      base_unit: 'each',
      unit_price: { amount: '8.0000', currency: 'GBP' },
      total_paid: { amount: '80.0000', currency: 'GBP' },
      delivery_result: 'delivered',
      recorded_by: 'user-1',
      recorded_at: '2026-08-21T10:00:00Z',
    },
    competing_offers: [
      { supplier_name: 'Supplier Two', unit_price: { amount: '9.0000', currency: 'GBP' } },
    ],
    calculation: {
      baseline_policy: 'last_paid',
      baseline_value: { amount: '100.0000', currency: 'GBP' },
      actual_value: { amount: '80.0000', currency: 'GBP' },
      delta: { amount: '20.0000', currency: 'GBP' },
      source_landed_cost_ids: ['lc-1'],
    },
  };

  const verifiedEvidence: SavingEvidence = {
    ...pendingEvidence,
    saving_record: {
      ...pendingEvidence.saving_record,
      status: 'verified',
      verified_by: 'user-1',
      verified_at: '2026-08-21T11:00:00Z',
    },
  };

  beforeEach(async () => {
    mockApiService = jasmine.createSpyObj<ApiService>('ApiService', ['products', 'suppliers']);
    mockSavingsApiService = jasmine.createSpyObj<SavingsApiService>('SavingsApiService', [
      'getSavingEvidence',
      'verifySaving',
    ]);
    const roleSignal = signal<Role | null>('buyer');
    mockSessionService = {
      hasRole: jasmine.createSpy('hasRole').and.callFake((...roles: Role[]) => {
        const r = roleSignal();
        return r ? roles.includes(r) : false;
      }),
      role: roleSignal,
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
    mockSavingsApiService.getSavingEvidence.and.returnValue(of(pendingEvidence));

    await TestBed.configureTestingModule({
      imports: [SavingEvidenceComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: mockApiService },
        { provide: SavingsApiService, useValue: mockSavingsApiService },
        { provide: SessionService, useValue: mockSessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of(convertToParamMap({ id: 'sav-1' })),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(SavingEvidenceComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load saving evidence and show pending status with verify affordance', () => {
    expect(component).toBeTruthy();
    expect(mockSavingsApiService.getSavingEvidence).toHaveBeenCalledWith('sav-1');
    expect(component.savingEvidence()).toEqual(pendingEvidence);
    expect(component.isVerified()).toBeFalse();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pending-banner')).toBeTruthy();
    expect(compiled.querySelector('.verify-action-btn')).toBeTruthy();
    expect(compiled.querySelector('.immutable-banner')).toBeFalsy();
  });

  it('should verify pending saving when verify action is triggered', () => {
    mockSavingsApiService.verifySaving.and.returnValue(of(verifiedEvidence.saving_record));

    component.onVerify();

    expect(mockSavingsApiService.verifySaving).toHaveBeenCalledWith('sav-1');
    expect(component.isVerified()).toBeTrue();
    expect(component.savingEvidence()?.saving_record.status).toBe('verified');
  });

  it('should present verified row as permanently read-only with no edit or delete affordance', async () => {
    mockSavingsApiService.getSavingEvidence.and.returnValue(of(verifiedEvidence));
    component.fetchEvidence('sav-1');
    fixture.detectChanges();

    expect(component.isVerified()).toBeTrue();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.immutable-banner')).toBeTruthy();
    expect(compiled.querySelector('.verify-action-btn')).toBeFalsy();
    // Ensure no edit affordance exists anywhere on the verified evidence page
    expect(compiled.querySelector('button[aria-label*="edit" i]')).toBeFalsy();
    expect(compiled.querySelector('a[href*="edit"]')).toBeFalsy();
  });

  it('should not allow verification by non-writer roles', () => {
    (mockSessionService['role'] as ReturnType<typeof signal<Role | null>>).set('viewer');
    fixture.detectChanges();

    expect(component.isWriter()).toBeFalse();
    component.onVerify();
    expect(mockSavingsApiService.verifySaving).not.toHaveBeenCalled();
  });
});
