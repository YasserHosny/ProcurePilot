import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { OutcomeCaptureComponent } from './outcome-capture.component';
import { SavingsApiService } from '../savings-api';

describe('OutcomeCaptureComponent (T021)', () => {
  let component: OutcomeCaptureComponent;
  let fixture: ComponentFixture<OutcomeCaptureComponent>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockSavingsApiService: jasmine.SpyObj<SavingsApiService>;
  let mockSessionService: Record<string, unknown>;

  const sampleProducts = [
    {
      id: 'prod-1',
      tenant_name: 'Full Cream Milk',
      canonical_name: 'full-cream-milk',
      base_unit: 'litre',
      pack: { pack_count: 12, unit_size: '1' },
      status: 'active' as const,
      created_at: '2026-08-20T10:00:00Z',
    },
  ];

  const sampleSuppliers = [
    {
      id: 'supp-1',
      name: 'Dairy Direct',
      status: 'active' as const,
      created_at: '2026-08-20T10:00:00Z',
    },
  ];

  beforeEach(async () => {
    mockApiService = jasmine.createSpyObj<ApiService>('ApiService', [
      'products',
      'suppliers',
    ]);
    mockSavingsApiService = jasmine.createSpyObj<SavingsApiService>('SavingsApiService', [
      'recordPurchase',
    ]);
    mockSessionService = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    mockApiService.products.and.returnValue(of({ items: sampleProducts, next_cursor: null }));
    mockApiService.suppliers.and.returnValue(of({ items: sampleSuppliers, next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [OutcomeCaptureComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        { provide: ApiService, useValue: mockApiService },
        { provide: SavingsApiService, useValue: mockSavingsApiService },
        { provide: SessionService, useValue: mockSessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: convertToParamMap({
                product_id: 'prod-1',
                supplier_id: 'supp-1',
                quantity: '20',
                unit_price: '1.2000',
                currency: 'GBP',
              }),
            },
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(OutcomeCaptureComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create and load reference products and suppliers', () => {
    expect(component).toBeTruthy();
    expect(mockApiService.products).toHaveBeenCalled();
    expect(mockApiService.suppliers).toHaveBeenCalled();
    expect(component.products().length).toBe(1);
    expect(component.suppliers().length).toBe(1);
  });

  it('should pre-populate form from query parameters without tenant id in inputs', () => {
    expect(component.form.get('workspace_product_id')?.value).toBe('prod-1');
    expect(component.form.get('supplier_id')?.value).toBe('supp-1');
    expect(component.form.get('quantity')?.value).toBe('20');
    expect(component.form.get('unit_price_amount')?.value).toBe('1.2000');
    expect(component.form.get('currency')?.value).toBe('GBP');
    expect(component.form.get('base_unit')?.value).toBe('litre');
    // Total should be auto-computed: 20 * 1.2 = 24.0000
    expect(component.form.get('total_paid_amount')?.value).toBe('24.0000');
  });

  it('should require product, quantity, unit price, currency, and total paid', () => {
    component.form.reset();
    expect(component.form.valid).toBeFalse();
    expect(component.form.get('workspace_product_id')?.hasError('required')).toBeTrue();
    expect(component.form.get('quantity')?.hasError('required')).toBeTrue();
    expect(component.form.get('unit_price_amount')?.hasError('required')).toBeTrue();
    expect(component.form.get('currency')?.hasError('required')).toBeTrue();
    expect(component.form.get('total_paid_amount')?.hasError('required')).toBeTrue();
  });

  it('should submit full payload with all user selections included (prevents Chunk 4.3 bug class)', () => {
    component.form.patchValue({
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      quotation_line_id: 'ql-1',
      match_decision_id: 'md-1',
      landed_cost_id: 'lc-1',
      quantity: '50.000000',
      base_unit: 'litre',
      unit_price_amount: '1.5000',
      currency: 'GBP',
      total_paid_amount: '75.0000',
      delivery_result: 'delivered',
      notes: 'Test PO #999',
    });

    const mockResponse = {
      purchase_record: {
        id: 'pur-1',
        workspace_product_id: 'prod-1',
        quantity: '50.000000',
        base_unit: 'litre',
        unit_price: { amount: '1.5000', currency: 'GBP' },
        total_paid: { amount: '75.0000', currency: 'GBP' },
        delivery_result: 'delivered' as const,
        recorded_by: 'user-1',
        recorded_at: '2026-08-21T12:00:00Z',
      },
      saving_record: {
        id: 'sav-1',
        purchase_record_id: 'pur-1',
        workspace_product_id: 'prod-1',
        status: 'pending' as const,
        baseline_policy: 'last_paid' as const,
        baseline_source_landed_cost_ids: ['lc-prev'],
        baseline_unit_price: { amount: '2.0000', currency: 'GBP' },
        baseline_value: { amount: '100.0000', currency: 'GBP' },
        actual_value: { amount: '75.0000', currency: 'GBP' },
        delta: { amount: '25.0000', currency: 'GBP' },
        calculation_version: 'saving-baseline-v1',
        calculation_inputs: {},
        recorded_by: 'user-1',
        recorded_at: '2026-08-21T12:00:00Z',
      },
    };

    mockSavingsApiService.recordPurchase.and.returnValue(of(mockResponse));

    component.onSubmit();

    expect(mockSavingsApiService.recordPurchase).toHaveBeenCalledWith({
      workspace_product_id: 'prod-1',
      supplier_id: 'supp-1',
      quotation_line_id: 'ql-1',
      match_decision_id: 'md-1',
      landed_cost_id: 'lc-1',
      quantity: '50.000000',
      base_unit: 'litre',
      unit_price: { amount: '1.5000', currency: 'GBP' },
      total_paid: { amount: '75.0000', currency: 'GBP' },
      delivery_result: 'delivered',
      ordered_at: null,
      delivered_at: null,
      notes: 'Test PO #999',
    });
  });

  it('should handle submission errors gracefully and display error message', () => {
    mockSavingsApiService.recordPurchase.and.returnValue(
      throwError(() => ({
        error: { message: 'Baseline calculation failed', trace_id: 'trace-404' },
      })),
    );

    component.onSubmit();

    expect(component.isSubmitting()).toBeFalse();
    expect(component.errorMessage()).toBe('Baseline calculation failed');
    expect(component.errorTraceId()).toBe('trace-404');
  });
});
