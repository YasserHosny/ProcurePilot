import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { PlanDisplayComponent } from './plan-display.component';
import { type BillingAccount, BillingApiService, type LimitCheck } from '../billing-api';

describe('PlanDisplayComponent (T056)', () => {
  let component: PlanDisplayComponent;
  let fixture: ComponentFixture<PlanDisplayComponent>;
  let mockBillingApiService: jasmine.SpyObj<BillingApiService>;
  let router: Router;

  const sampleAccount: BillingAccount = {
    id: 'ba-1',
    plan: {
      code: 'starter',
      name: 'Starter',
      status: 'active',
      monthly_price: { amount: '0.0000', currency: 'GBP' },
      limits: { active_catalogue_products: 100 },
      features: { ai_matching: true, smart_compare: true },
    },
    provider: 'stub',
    provider_customer_id: 'stub_cust_1',
    status: 'active',
    assigned_at: '2026-08-21T10:00:00Z',
  };

  const sampleLimitCheck: LimitCheck = {
    resource: 'active_catalogue_products',
    plan_code: 'starter',
    limit: 100,
    used: 12,
    allowed: true,
    remaining: 88,
  };

  beforeEach(async () => {
    mockBillingApiService = jasmine.createSpyObj<BillingApiService>('BillingApiService', [
      'getBillingAccount',
      'checkActiveCatalogueProductsLimit',
    ]);

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('owner'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    mockBillingApiService.getBillingAccount.and.returnValue(of(sampleAccount));
    mockBillingApiService.checkActiveCatalogueProductsLimit.and.returnValue(of(sampleLimitCheck));

    await TestBed.configureTestingModule({
      imports: [PlanDisplayComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideRouter([]),
        { provide: BillingApiService, useValue: mockBillingApiService },
        { provide: SessionService, useValue: mockSession },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    fixture = TestBed.createComponent(PlanDisplayComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load billing account information and limits', () => {
    expect(component).toBeTruthy();
    expect(mockBillingApiService.getBillingAccount).toHaveBeenCalled();
    expect(mockBillingApiService.checkActiveCatalogueProductsLimit).toHaveBeenCalled();
    expect(component.billingAccount()).toEqual(sampleAccount);
    expect(component.limitCheck()).toEqual(sampleLimitCheck);
    expect(component.isLoading()).toBeFalse();
  });

  it('should display plan name and features', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.plan-name')?.textContent).toContain('Starter');
    expect(compiled.querySelectorAll('.feature-item').length).toBe(5);
  });

  it('should navigate to /home when continue button is clicked', () => {
    component.continueToWorkspace();
    expect(router.navigate).toHaveBeenCalledWith(['/home']);
  });

  it('should handle billing account load error', () => {
    mockBillingApiService.getBillingAccount.and.returnValue(
      throwError(() => ({ error: { message: 'Billing account not configured', trace_id: 'tr-404' } })),
    );

    component.loadBillingInfo();

    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBe('Billing account not configured');
    expect(component.errorTraceId()).toBe('tr-404');
  });
});
