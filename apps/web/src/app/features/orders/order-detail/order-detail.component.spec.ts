import { provideHttpClient, withXhr } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import type { Product } from '../../../core/api/models';

import { OrdersApiService } from '../orders-api';
import { OrderDetailComponent } from './order-detail.component';

describe('OrderDetailComponent', () => {
  let fixture: ComponentFixture<OrderDetailComponent>;
  let api: jasmine.SpyObj<OrdersApiService>;
  let catalogue: jasmine.SpyObj<ApiService>;
  const product: Product = {
    id: 'p1', tenant_name: 'Paper', canonical_name: 'Paper', base_unit: 'kilogram',
    pack: { pack_count: 1, unit_size: '100', base_quantity: '100' }, status: 'active', created_at: '',
  };

  beforeEach(async () => {
    catalogue = jasmine.createSpyObj<ApiService>('ApiService', ['product']);
    catalogue.product.and.returnValue(of(product));
    api = jasmine.createSpyObj<OrdersApiService>('OrdersApiService', [
      'getOrder', 'submitOrder', 'cancelOrder', 'recordConfirmation', 'recordReceipt',
    ]);
    api.getOrder.and.returnValue(of({
      order: {
        id: 'order-1', tenant_id: 'tenant-1', order_number: 'PO-1001', supplier_id: 'supplier-1',
        status: 'submitted', order_date: '2026-09-20', expected_delivery_date: '2026-09-25',
        total: { amount: '120.00', currency: 'GBP' }, tax: { amount: '0.00', currency: 'GBP' },
        source_kind: 'manual', source_reference: 'PO-1001', source_hash: null, created_by: 'member-1',
        created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z', lines: [{
          id: 'line-1', line_number: 1, workspace_product_id: 'p1', description: 'Paper', ordered_quantity: '10',
          base_unit: 'kilogram', pack_base_quantity: '25.000000', unit_price: { amount: '940.00', currency: 'GBP' }, tax: { amount: '0.00', currency: 'GBP' },
          line_total: { amount: '120.00', currency: 'GBP' },
        }],
      },
      confirmation: null, receipts: [], lifecycle: {
        purchase_order_id: 'order-1', status: 'submitted', confirmation: 'pending', receipt: 'pending',
        lines: [{ purchase_order_line_id: 'line-1', ordered_quantity: '10.000000',
          confirmed: { state: 'pending', quantity: null, source_ids: [] },
          received: { state: 'pending', quantity: null, source_ids: [] }, remaining_quantity: null, over_received_quantity: null }],
      },
    }));
    await TestBed.configureTestingModule({
      imports: [OrderDetailComponent],
      providers: [
        provideTranslateService(),
        { provide: ApiService, useValue: catalogue },
        provideHttpClient(withXhr()), provideNoopAnimations(), provideRouter([]), { provide: OrdersApiService, useValue: api },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'order-1' } } } },
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      units: { kilogram: 'kg', litre: 'L' },
      orders: {
        create: { packUnit: 'pack of {{size}} {{unit}}' },
        backToOrders: 'Back', retry: 'Retry', loadError: 'Load failed', saveError: 'Save failed', notProvided: 'Not provided',
        status: { submitted: 'Submitted' }, evidence: { pending: 'Pending' },
        detail: {
          errors: { order_not_open_for_evidence: 'This order cannot take delivery or confirmation evidence.' },
          eyebrow: 'Purchase order', createdAt: 'Created {{date}}', orderDate: 'Order date', expectedDelivery: 'Expected',
          total: 'Total', confirmation: 'Confirmation', receipt: 'Receipt', linesTitle: 'Lines', linesSubtitle: 'Evidence',
          ordered: 'Ordered', confirmed: 'Confirmed', received: 'Received', remaining: 'Remaining', fromRequest: 'From request', actionsTitle: 'Actions',
          actionsSubtitle: 'Internal', submit: 'Submit', recordOutcome: 'Record outcome', recordConfirmation: 'Confirm', recordReceipt: 'Receive',
          confirmationFormTitle: 'Confirmation', receiptFormTitle: 'Receipt', reference: 'Reference', confirmedDate: 'Date',
          receivedDate: 'Date', confirmedQuantity: 'Quantity', receivedQuantity: 'Quantity', save: 'Save',
          timelineTitle: 'Timeline', orderCreated: 'Created', confirmationRecorded: 'Confirmed', receiptRecorded: 'Receipt {{reference}}',
        },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OrderDetailComponent);
  });

  it('uses the saved pack snapshot despite a different live catalogue pack', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const line = component.evidence()!.order.lines[0];
    expect(catalogue.product).not.toHaveBeenCalled();
    expect(component.linePriceLabel(line)).toContain('pack of 25 kg');
    expect(component.linePriceLabel(line)).toContain('37.60');
  });

  it('shows fractional pack size and derived per-litre price', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const line = { ...component.evidence()!.order.lines[0],
      base_unit: 'litre', pack_base_quantity: '0.500000',
      unit_price: { amount: '10.00', currency: 'GBP' },
    };
    const label = component.linePriceLabel(line);
    expect(label).toContain('pack of 0.5 L');
    expect(label).toContain('20 / L');
    expect(catalogue.product).not.toHaveBeenCalled();
  });

  it('shows only the unit for a size-one pack or an unknown snapshot', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    for (const size of ['1.000000', null, undefined]) {
      const label = component.linePriceLabel({
        ...component.evidence()!.order.lines[0], pack_base_quantity: size,
      });
      expect(label).toContain('/ kg');
      expect(label).not.toContain('pack of');
      expect(label).not.toContain('·');
    }
    expect(catalogue.product).not.toHaveBeenCalled();
  });

  it('formats lifecycle quantities and preserves missing values', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component.formatQuantity('12.500000')).toBe('12.5');
    expect(component.formatQuantity('0.000001')).toBe('0.000001');
    expect(component.formatQuantity('1.234567')).toBe('1.234567');
    expect(component.formatQuantity(null)).toBe('Not provided');
    const text = (fixture.nativeElement as HTMLElement).querySelector('.line-evidence')?.textContent;
    expect(text).toContain('Ordered 10');
    expect(text).not.toContain('10.000000');
    expect(text).toContain('Not provided');
  });

  it('renders pending evidence and exposes lifecycle actions', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="order-lines"]')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Pending');
    expect(fixture.nativeElement.textContent).toContain('Paper');
    expect(fixture.nativeElement.textContent).toContain('Confirm');
    expect(fixture.nativeElement.textContent).toContain('Receive');
  });

  it('links a sent order to recording its purchase outcome', () => {
    fixture.detectChanges();
    const link = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="record-outcome"]');
    expect(link?.textContent).toContain('Record outcome');
    expect(link?.getAttribute('href')).toBe('/orders/order-1/record-outcome');
    const component = fixture.componentInstance;
    expect(component.canRecordOutcome('received')).toBeTrue();
    expect(component.canRecordOutcome('draft')).toBeFalse();
    expect(component.canRecordOutcome('cancelled')).toBeFalse();
  });

  it('accepts typed day-first confirmation date, shows day-first format, and produces ISO timestamp in payload', async () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.confirmationOpen.set(true);
    fixture.detectChanges();
    await fixture.whenStable();

    const input = (fixture.nativeElement as HTMLElement).querySelector(
      'input[name="confirmationDate"]'
    ) as HTMLInputElement;
    expect(input).toBeTruthy();

    input.value = '';
    for (const char of '22/10/2026') {
      input.value += char;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    input.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(component.confirmationDate()).toBe('2026-10-22');
    expect(input.value).toBe('22/10/2026');

    component.confirmationReference.set('CONF-999');
    api.recordConfirmation.and.returnValue(of(component.evidence()!));

    component.recordConfirmation();

    expect(api.recordConfirmation).toHaveBeenCalledWith(
      'order-1',
      jasmine.objectContaining({
        supplier_reference: 'CONF-999',
        confirmed_at: '2026-10-22T12:00:00Z',
      }),
    );
  });

  it('accepts typed day-first receipt date, shows day-first format, and produces ISO date in payload', async () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    fixture.detectChanges();
    await fixture.whenStable();

    const input = (fixture.nativeElement as HTMLElement).querySelector(
      'input[name="receiptDate"]'
    ) as HTMLInputElement;
    expect(input).toBeTruthy();

    input.value = '';
    for (const char of '25/10/2026') {
      input.value += char;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    input.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(component.receiptDate()).toBe('2026-10-25');
    expect(input.value).toBe('25/10/2026');

    component.receiptReference.set('REC-888');
    component.setQuantity('receipt', 'line-1', '2');
    api.recordReceipt.and.returnValue(of(component.evidence()!));

    component.recordReceipt();

    expect(api.recordReceipt).toHaveBeenCalledWith(
      'order-1',
      jasmine.objectContaining({
        receipt_reference: 'REC-888',
        receipt_date: '2026-10-25',
      }),
    );
  });

  it('displays supplier name, from-request link, and remaining quantity as ordered minus received', () => {
    api.getOrder.and.returnValue(
      of({
        order: {
          id: 'order-1',
          tenant_id: 'tenant-1',
          order_number: 'PO-1001',
          supplier_id: 'supplier-1',
          supplier_name: 'الوفرة للمواد الغذائية',
          source_request_id: 'req-456',
          status: 'submitted',
          order_date: '2026-09-20',
          expected_delivery_date: '2026-09-25',
          total: { amount: '120.00', currency: 'GBP' },
          tax: { amount: '0.00', currency: 'GBP' },
          source_kind: 'manual',
          source_reference: 'PO-1001',
          source_hash: null,
          created_by: 'member-1',
          created_at: '2026-09-20T10:00:00Z',
          updated_at: '2026-09-20T10:00:00Z',
          lines: [{
            id: 'line-1',
            line_number: 1,
            workspace_product_id: 'p1',
            description: 'Paper',
            ordered_quantity: '10',
            base_unit: 'kilogram',
            pack_base_quantity: '25.000000',
            unit_price: { amount: '940.00', currency: 'GBP' },
            tax: { amount: '0.00', currency: 'GBP' },
            line_total: { amount: '120.00', currency: 'GBP' },
          }],
        },
        confirmation: null,
        receipts: [],
        lifecycle: {
          purchase_order_id: 'order-1',
          status: 'submitted',
          confirmation: 'pending',
          receipt: 'pending',
          lines: [{
            purchase_order_line_id: 'line-1',
            ordered_quantity: '10.000000',
            confirmed: { state: 'pending', quantity: null, source_ids: [] },
            received: { state: 'pending', quantity: null, source_ids: [] },
            remaining_quantity: null,
            over_received_quantity: null,
          }],
        },
      }),
    );
    fixture = TestBed.createComponent(OrderDetailComponent);
    fixture.detectChanges();

    const supplier = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="order-supplier"]');
    expect(supplier).toBeTruthy();
    expect(supplier?.textContent?.trim()).toBe('الوفرة للمواد الغذائية');
    expect(supplier?.getAttribute('dir')).toBe('auto');

    const requestLink = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="from-request-link"]');
    expect(requestLink).toBeTruthy();
    expect(requestLink?.getAttribute('href')).toBe('/requests/req-456');

    const remainingText = (fixture.nativeElement as HTMLElement).querySelector('.line-remaining strong');
    expect(remainingText?.textContent?.trim()).toBe('10');
  });
  function showOrderAs(status: string): void {
    api.getOrder('order-1').subscribe((value) => {
      api.getOrder.and.returnValue(of({
        ...value,
        order: { ...value.order, status: status as typeof value.order.status },
        lifecycle: { ...value.lifecycle, status: status as typeof value.lifecycle.status },
      }));
    }).unsubscribe();
  }

  const el = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const byTestId = (id: string): HTMLElement | null => el().querySelector(`[data-testid="${id}"]`);

  // P-181: submitting is not undoable in the UI, so it asks first.
  it('asks before submitting a draft order and submits only on confirmation', () => {
    showOrderAs('draft');
    fixture.detectChanges();
    api.submitOrder.and.returnValue(of(fixture.componentInstance.evidence()!.order));

    byTestId('submit-order')!.click();
    fixture.detectChanges();

    expect(api.submitOrder).not.toHaveBeenCalled();
    expect(byTestId('confirm-submit')).toBeTruthy();

    byTestId('confirm-submit')!.click();
    expect(api.submitOrder).toHaveBeenCalledWith('order-1');
  });

  // P-181: the API cancels sent orders short of fully received (spec 016 FR-020).
  it('offers cancel on sent orders that are not fully received, closed or cancelled', () => {
    const offered: Record<string, boolean> = {};
    for (const status of ['draft', 'submitted', 'confirmed', 'partially_received', 'received', 'closed', 'cancelled']) {
      fixture = TestBed.createComponent(OrderDetailComponent);
      showOrderAs(status);
      fixture.detectChanges();
      offered[status] = byTestId('cancel-order') !== null;
    }
    expect(offered).toEqual({
      draft: true, submitted: true, confirmed: true, partially_received: true,
      received: false, closed: false, cancelled: false,
    });
  });

  // P-181: a failed save used to replace the whole page with a load-error card.
  it('keeps the order and the typed receipt on screen when saving a receipt fails, and says why', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    component.receiptReference.set('GRN-7');
    component.receiptDate.set('2026-10-25');
    component.setQuantity('receipt', 'line-1', '4');
    api.recordReceipt.and.returnValue(throwError(() => ({
      status: 409, error: { code: 'conflict', details: { reason: 'order_not_open_for_evidence' } },
    })));

    component.recordReceipt();
    fixture.detectChanges();

    expect(byTestId('order-lines')).toBeTruthy();
    expect(component.receiptReference()).toBe('GRN-7');
    expect(component.quantityValue(component.receiptQuantities(), component.evidence()!.order.lines[0])).toBe('4');
    expect(byTestId('action-error')?.getAttribute('role')).toBe('alert');
    expect(byTestId('action-error')?.textContent).toContain('cannot take delivery or confirmation evidence');
    expect(el().textContent).not.toContain('Load failed');
  });

  // P-180: a receipt of nothing is refused before it reaches the API.
  it('does not save a delivery receipt that receives nothing on any line', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    component.receiptReference.set('GRN-0');
    component.receiptDate.set('2026-10-25');
    fixture.detectChanges();

    component.recordReceipt();
    fixture.detectChanges();
    component.setQuantity('receipt', 'line-1', '0');
    component.recordReceipt();
    fixture.detectChanges();

    expect(api.recordReceipt).not.toHaveBeenCalled();
    expect(byTestId('receipt-quantity-error')).toBeTruthy();
  });
  it('clears an earlier failure message once a confirmation saves', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptReference.set('GRN-7');
    component.receiptDate.set('2026-10-25');
    component.setQuantity('receipt', 'line-1', '4');
    api.recordReceipt.and.returnValue(throwError(() => ({ status: 503 })));
    component.recordReceipt();
    fixture.detectChanges();
    expect(byTestId('action-error')).toBeTruthy();

    component.confirmationReference.set('SO-1');
    component.onConfirmationDateChange(new Date(2026, 9, 25));
    api.recordConfirmation.and.returnValue(of(component.evidence()!));
    component.recordConfirmation();
    fixture.detectChanges();

    expect(byTestId('action-error')).toBeNull();
  });
});
