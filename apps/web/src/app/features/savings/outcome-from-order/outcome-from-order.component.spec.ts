import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';

import { toLocalMidnightIso } from '../../../core/format/iso-date';
import {
  type PurchaseOutcomeCreated,
  type PurchaseOutcomePrefill,
  SavingsApiService,
} from '../savings-api';
import { OutcomeFromOrderComponent } from './outcome-from-order.component';

describe('OutcomeFromOrderComponent', () => {
  let fixture: ComponentFixture<OutcomeFromOrderComponent>;
  let component: OutcomeFromOrderComponent;
  let api: jasmine.SpyObj<SavingsApiService>;

  const prefill: PurchaseOutcomePrefill = {
    purchase_order_id: 'order-1',
    order_number: 'PO-1001',
    status: 'received',
    supplier_id: 'supplier-1',
    order_date: '2026-10-15',
    delivery_result: 'delivered',
    lines: [
      {
        purchase_order_line_id: 'line-1',
        line_number: 1,
        description: 'Eggs carton',
        workspace_product_id: 'prod-eggs',
        ordered_packs: '2.000000',
        pack_base_quantity: '30.000000',
        quantity: '60.000000',
        base_unit: 'each',
        unit_price: { amount: '5.5000', currency: 'EGP' },
        total_paid: { amount: '330.0000', currency: 'EGP' },
        tax: { amount: '0.0000', currency: 'EGP' },
        recordable: true,
        reason: null,
        recorded_saving_id: null,
      },
      {
        purchase_order_line_id: 'line-2',
        line_number: 2,
        description: 'Delivery fee',
        workspace_product_id: null,
        ordered_packs: '1.000000',
        pack_base_quantity: null,
        quantity: '1.000000',
        base_unit: 'each',
        unit_price: { amount: '50.0000', currency: 'EGP' },
        total_paid: { amount: '50.0000', currency: 'EGP' },
        tax: { amount: '0.0000', currency: 'EGP' },
        recordable: false,
        reason: 'no_product',
        recorded_saving_id: null,
      },
    ],
  };

  beforeEach(async () => {
    api = jasmine.createSpyObj<SavingsApiService>('SavingsApiService', [
      'getPurchasePrefill',
      'recordPurchase',
    ]);
    api.getPurchasePrefill.and.returnValue(of(prefill));
    api.recordPurchase.and.returnValue(of({} as PurchaseOutcomeCreated));

    await TestBed.configureTestingModule({
      imports: [OutcomeFromOrderComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SavingsApiService, useValue: api },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'order-1' } } } },
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      rfq: { email: { units: { each: 'piece' } } },
      orders: { create: { packUnit: 'pack of {{size}} {{unit}}' } },
      savings: {
        fromOrder: {
          conversion: '{{packs}} × {{pack}} = {{quantity}} {{unit}}',
          reasons: { no_product: 'Not linked to a catalogue product' },
          notRecordable: 'Order not recordable',
          saveError: 'Save failed',
        },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OutcomeFromOrderComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('pre-fills one line per PO line in base units, with unlinked lines not selectable', () => {
    expect(api.getPurchasePrefill).toHaveBeenCalledWith('order-1');
    expect(component.lines().map((l) => l.include)).toEqual([true, false]);
    expect(component.deliveryResult()).toBe('delivered');
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    // Unit name comes from the shared rfq.email.units catalogue; assert the conversion, not the label.
    expect(text).toMatch(/2 × pack of 30 (\S+) = 60 \1/);
    expect(text).toContain('Not linked to a catalogue product');
    expect(component.unitPrice(component.lines()[0])).toBe('5.5000');
  });

  it('pre-fills inputs without trailing zeros', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    const qtyInput = host.querySelector<HTMLInputElement>('[data-testid="line-quantity"]');
    const totalInput = host.querySelector<HTMLInputElement>('[data-testid="line-total"]');
    expect(qtyInput?.value).toBe('60');
    expect(totalInput?.value).toBe('330');
    expect(component.lines()[0].quantity).toBe('60');
    expect(component.lines()[0].total).toBe('330');
  });

  it('keeps the net total trimmed and shows the excluded tax in both languages', async () => {
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog, true);
    translate.setTranslation('ar', arCatalog, true);
    api.getPurchasePrefill.and.returnValue(of({ ...prefill, lines: [{ ...prefill.lines[0],
      total_paid: { amount: '1200.0000', currency: 'SAR' },
      tax: { amount: '180.0000', currency: 'SAR' },
    }] }));
    component.load();
    fixture.detectChanges();
    await fixture.whenStable();
    const host = fixture.nativeElement as HTMLElement;
    expect(host.querySelector<HTMLInputElement>('[data-testid="line-total"]')?.value).toBe('1200');
    expect(host.querySelector('[data-testid="excluded-tax-hint"]')?.textContent).toContain('Excludes tax');
    expect(host.querySelector('[data-testid="excluded-tax-hint"]')?.textContent).toContain('180');
    translate.use('ar');
    fixture.detectChanges();
    expect(host.querySelector('[data-testid="excluded-tax-hint"]')?.textContent).toContain('لا يشمل الضريبة');
  });

  it('does not show an excluded-tax hint for zero tax', () => {
    api.getPurchasePrefill.and.returnValue(of({ ...prefill, lines: [{ ...prefill.lines[0],
      tax: { amount: '0.0000', currency: 'EGP' },
    }] }));
    component.load();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="excluded-tax-hint"]')).toBeNull();
  });

  it('sends trimmed values when saving unedited pre-filled line', () => {
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);

    component.submit();

    expect(api.recordPurchase).toHaveBeenCalledTimes(1);
    const [body] = api.recordPurchase.calls.mostRecent().args;
    expect(body.quantity).toBe('60');
    expect(body.total_paid).toEqual({ amount: '330', currency: 'EGP' });
  });

  it('keeps full precision on save when unedited', () => {
    const precisionPrefill: PurchaseOutcomePrefill = {
      ...prefill,
      lines: [
        {
          ...prefill.lines[0],
          quantity: '12.345678',
          total_paid: { amount: '1230.5000', currency: 'EGP' },
        },
      ],
    };
    api.getPurchasePrefill.and.returnValue(of(precisionPrefill));
    component.load();

    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    component.submit();

    expect(api.recordPurchase).toHaveBeenCalledTimes(1);
    const [body] = api.recordPurchase.calls.mostRecent().args;
    expect(body.quantity).toBe('12.345678');
    expect(body.total_paid.amount).toBe('1230.5');
  });

  it('records the selected lines linked to their PO line, with edits, then opens the ledger', () => {
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    component.update(0, { quantity: '58', total: '319' });

    component.submit();

    expect(api.recordPurchase).toHaveBeenCalledTimes(1);
    const [body, key] = api.recordPurchase.calls.mostRecent().args;
    expect(body).toEqual({
      workspace_product_id: 'prod-eggs',
      supplier_id: 'supplier-1',
      purchase_order_line_id: 'line-1',
      quantity: '58',
      base_unit: 'each',
      unit_price: { amount: '5.5000', currency: 'EGP' },
      total_paid: { amount: '319', currency: 'EGP' },
      delivery_result: 'delivered',
      ordered_at: toLocalMidnightIso('2026-10-15'),
      notes: null,
    });
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    expect(router.navigate).toHaveBeenCalledWith(['/savings']);
  });

  it('blocks saving an invalid quantity', () => {
    component.update(0, { quantity: '0' });
    expect(component.canSubmit()).toBeFalse();
    component.update(0, { quantity: 'abc' });
    expect(component.canSubmit()).toBeFalse();
  });

  it('reuses the same idempotency key when a failed save is retried', () => {
    api.recordPurchase.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 503, error: { code: 'x', message: 'x', trace_id: 't' } })),
    );
    component.submit();
    const firstKey = api.recordPurchase.calls.mostRecent().args[1];
    expect(component.errorMessage()).toBe('Save failed');

    api.recordPurchase.and.returnValue(of({} as PurchaseOutcomeCreated));
    spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    component.submit();
    expect(api.recordPurchase.calls.mostRecent().args[1]).toBe(firstKey);
  });

  it('explains when the order cannot be recorded', () => {
    api.getPurchasePrefill.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 409,
            error: { code: 'conflict', message: 'x', details: { reason: 'purchase_order_not_recordable' }, trace_id: 't' },
          }),
      ),
    );
    component.load();
    expect(component.errorMessage()).toBe('Order not recordable');
  });
});
