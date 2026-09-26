import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslateModule } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import { GuardrailsComponent } from './guardrails.component';
import { RfqApi, RfqGuardrail } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';

describe('GuardrailsComponent', () => {
  let component: GuardrailsComponent;
  let fixture: ComponentFixture<GuardrailsComponent>;
  let rfqApi: jasmine.SpyObj<RfqApi>;
  let api: jasmine.SpyObj<ApiService>;

  const guardrail: RfqGuardrail = {
    id: 'g-1', tenant_id: 't-1', created_by_membership_id: 'm-1',
    max_order_value_amount: '1000', max_order_value_currency: 'USD',
    supplier_allowlist: [], category_allowlist: null, min_response_count: 2,
    max_price_variance_pct: '0.15', enabled: true, default_branch_id: 'b-1',
    created_at: '2026-09-25T10:00:00Z',
  };

  beforeEach(async () => {
    rfqApi = jasmine.createSpyObj('RfqApi', ['listGuardrails', 'createGuardrail', 'updateGuardrail']);
    rfqApi.listGuardrails.and.returnValue(of([guardrail]));
    rfqApi.createGuardrail.and.returnValue(of(guardrail));
    rfqApi.updateGuardrail.and.returnValue(of({ ...guardrail, enabled: false }));
    api = jasmine.createSpyObj('ApiService', ['suppliers', 'listBranches', 'configOptions']);
    api.suppliers.and.returnValue(of({ items: [], next_cursor: null }));
    api.listBranches.and.returnValue(of({
      items: [{ id: 'b-1', name: 'Main', is_active: true, created_at: '2026-09-25T10:00:00Z' }],
      next_cursor: null,
    }));
    api.configOptions.and.returnValue(of({
      regions: [],
      currencies: [
        { code: 'USD', label_en: 'US Dollar', label_ar: 'دولار أمريكي' },
        { code: 'GBP', label_en: 'Pound Sterling', label_ar: 'جنيه إسترليني' },
      ],
      tax_models: [],
    }));

    await TestBed.configureTestingModule({
      imports: [GuardrailsComponent, TranslateModule.forRoot()],
      providers: [
        { provide: RfqApi, useValue: rfqApi },
        { provide: ApiService, useValue: api },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(GuardrailsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the configured guardrail list', () => {
    expect(component.guardrails()).toEqual([guardrail]);
    expect(fixture.nativeElement.textContent).toContain('rfq.guardrails.title');
  });

  it('rejects a non-positive order value and invalid variance', () => {
    component.maxOrderValue = '0';
    component.maxPriceVariancePercent = '10';
    component.defaultBranchId = 'b-1';
    component.save();
    expect(rfqApi.createGuardrail).not.toHaveBeenCalled();

    component.maxOrderValue = '100';
    component.maxPriceVariancePercent = '101';
    component.save();
    expect(rfqApi.createGuardrail).not.toHaveBeenCalled();
  });

  it('sends the UI percentage as an API fraction', () => {
    component.maxOrderValue = '2500';
    component.currency = 'GBP';
    component.minResponseCount = 3;
    component.maxPriceVariancePercent = '12.5';
    component.supplierAllowlist = ['s-1'];
    component.defaultBranchId = 'b-1';
    component.save();
    expect(rfqApi.createGuardrail).toHaveBeenCalledWith(jasmine.objectContaining({
      max_order_value_amount: '2500', max_order_value_currency: 'GBP',
      min_response_count: 3, max_price_variance_pct: '0.125',
      supplier_allowlist: ['s-1'], default_branch_id: 'b-1', enabled: true,
    }));
  });

  it('patches the enabled flag', () => {
    component.toggle(guardrail);
    expect(rfqApi.updateGuardrail).toHaveBeenCalledWith('g-1', { enabled: false });
  });

  it('shows a translated error when saving fails', () => {
    rfqApi.createGuardrail.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 422, error: { details: { max_order_value_amount: 'bad' } } })),
    );
    component.maxOrderValue = '100';
    component.maxPriceVariancePercent = '10';
    component.defaultBranchId = 'b-1';
    component.save();
    expect(component.errorMessage()).toBe('rfq.guardrails.validation.maxOrderValue');
  });
});
