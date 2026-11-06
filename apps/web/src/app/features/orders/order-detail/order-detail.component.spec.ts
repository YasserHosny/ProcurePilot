import { provideHttpClient, withXhr } from '@angular/common/http';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { DateAdapter } from '@angular/material/core';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import type { Product } from '../../../core/api/models';

import { OrdersApiService } from '../orders-api';
import { RequestsApiService } from '../../requests/requests-api';
import { OrderDetailComponent } from './order-detail.component';

describe('OrderDetailComponent', () => {
  let fixture: ComponentFixture<OrderDetailComponent>;
  let api: jasmine.SpyObj<OrdersApiService>;
  let catalogue: jasmine.SpyObj<ApiService>;
  let requests: jasmine.SpyObj<RequestsApiService>;
  const product: Product = {
    id: 'p1', tenant_name: 'Paper', canonical_name: 'Paper', base_unit: 'kilogram',
    pack: { pack_count: 1, unit_size: '100', base_quantity: '100' }, status: 'active', created_at: '',
  };

  beforeEach(async () => {
    catalogue = jasmine.createSpyObj<ApiService>('ApiService', ['product']);
    catalogue.product.and.returnValue(of(product));
    requests = jasmine.createSpyObj<RequestsApiService>('RequestsApiService', ['getRequest']);
    requests.getRequest.and.returnValue(throwError(() => new Error('no request')));
    api = jasmine.createSpyObj<OrdersApiService>('OrdersApiService', [
      'getOrder', 'submitOrder', 'cancelOrder', 'closeOrder', 'withdrawOrder', 'recordConfirmation', 'recordReceipt',
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
        { provide: RequestsApiService, useValue: requests },
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
          receivedQuantityFor: '{{product}} · Received quantity ({{unit}}, ordered {{ordered}})', confirmedQuantityFor: '{{product}} · Confirmed quantity ({{unit}}, ordered {{ordered}})', receiptSaved: 'Delivery receipt saved.', submitted: 'Order submitted.', dateFormatHintDayFirst: 'dd/mm/yyyy', dateFormatHintMonthFirst: 'mm/dd/yyyy',
          errors: { order_not_open_for_evidence: 'This order cannot take delivery or confirmation evidence.', order_has_evidence: 'It already has a supplier confirmation or a delivery receipt.' }, withdrawn: 'Order is a draft again.', closed: 'Order closed.',
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
  // P-187: saved receipts, submits and cancels were silent to a screen reader.
  it('announces a saved receipt in a polite live region that exists before the news', fakeAsync(() => {
    fixture.detectChanges();
    const region = byTestId('action-status');
    expect(region?.getAttribute('role')).toBe('status');
    expect(region?.getAttribute('aria-live')).toBe('polite');
    expect(region?.textContent?.trim()).toBe('');

    saveReceipt();
    tick();
    fixture.detectChanges();

    expect(byTestId('action-status')?.textContent).toContain('Delivery receipt saved.');
  }));

  // Review (#P-187): the same message twice leaves the text unchanged, so nothing is announced.
  it('re-announces when the same action is saved a second time', fakeAsync(() => {
    fixture.detectChanges();
    saveReceipt();
    tick();
    fixture.detectChanges();
    expect(byTestId('action-status')?.textContent).toContain('Delivery receipt saved.');

    saveReceipt();
    fixture.detectChanges();
    expect(byTestId('action-status')?.textContent?.trim()).toBe(''); // cleared, so the next text is news
    tick();
    fixture.detectChanges();
    expect(byTestId('action-status')?.textContent).toContain('Delivery receipt saved.');
  }));

  function saveReceipt(): void {
    const component = fixture.componentInstance;
    component.receiptReference.set('GRN-1');
    component.receiptDate.set('2026-10-25');
    component.setQuantity('receipt', 'line-1', '4');
    api.recordReceipt.and.returnValue(of(component.evidence()!));
    component.recordReceipt();
  }

  // P-187: the inline confirmation did not take focus, so keyboard users were left behind it.
  it('moves focus into the submit and cancel confirmations when they open', fakeAsync(() => {
    showOrderAs('draft');
    fixture.detectChanges();

    byTestId('submit-order')!.click();
    fixture.detectChanges();
    tick();
    expect(byTestId('submit-confirm-panel')?.contains(document.activeElement)).toBeTrue();

    byTestId('cancel-order')!.click();
    fixture.detectChanges();
    tick();
    expect(byTestId('cancel-confirm-panel')?.contains(document.activeElement)).toBeTrue();
  }));

  // P-187: the quantity inputs said nothing of the unit or what was ordered.
  it('labels receipt quantities with the unit and the ordered quantity', () => {
    fixture.detectChanges();
    fixture.componentInstance.receiptOpen.set(true);
    fixture.detectChanges();

    const label = el().querySelector('input[name="receipt-line-1"]')?.closest('mat-form-field')?.textContent ?? '';
    // Order quantities are in packs (ADR-020): the fixture line is 10 packs of 25 kg.
    expect(label).toContain('ordered 10');
    expect(label).toContain('pack of 25 kg');
    expect(label).not.toContain('(kg,');
  });

  it('shows the date order the date input actually parses, day-first or month-first', () => {
    fixture.detectChanges();
    fixture.componentInstance.receiptOpen.set(true);
    fixture.detectChanges();
    expect(byTestId('date-format-hint')?.textContent).toContain('dd/mm/yyyy');

    // Review (Codex, #443): an English US workspace parses typed dates month-first.
    const adapter = fixture.debugElement.injector.get(DateAdapter) as unknown as { isDayFirst(): boolean };
    spyOn(adapter, 'isDayFirst').and.returnValue(false);
    fixture.detectChanges();
    expect(byTestId('date-format-hint')?.textContent).toContain('mm/dd/yyyy');
    expect(byTestId('date-format-hint')?.textContent).not.toContain('dd/mm/yyyy');
  });

  // P-188: a PO document for the hand-off to the supplier (the app itself sends nothing).
  it('exports the order as a CSV named after the PO and prints it', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const saved: { name: string; content: string }[] = [];
    spyOn(component, 'saveFile').and.callFake((name: string, content: string) => { saved.push({ name, content }); });
    const print = spyOn(window, 'print');

    byTestId('export-csv')!.click();
    byTestId('print-order')!.click();

    expect(saved.length).toBe(1);
    expect(saved[0].name).toBe('PO-1001.csv');
    expect(saved[0].content).toContain('PO-1001');
    expect(saved[0].content).toContain('GBP');
    expect(print).toHaveBeenCalled();
  });

  it('fills every line with what is still to be received', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    fixture.detectChanges();

    byTestId('receive-all')!.click();

    expect(component.quantityValue(component.receiptQuantities(), component.evidence()!.order.lines[0])).toBe('10');
  });

  it('flags a sent order whose expected delivery date has passed', () => {
    fixture.detectChanges(); // fixture: submitted, expected 25 Sep 2026
    expect(byTestId('order-overdue')).toBeTruthy();

    showOrderAs('received');
    fixture = TestBed.createComponent(OrderDetailComponent);
    fixture.detectChanges();
    expect(byTestId('order-overdue')).toBeNull();
  });
  // PPS-212: how much of the order has arrived, at a glance.
  it('shows how much of the order has been received as a progress bar', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const value = component.evidence()!;
    component.evidence.set({
      ...value,
      lifecycle: {
        ...value.lifecycle,
        lines: value.lifecycle.lines.map((line) => ({
          ...line,
          received: { state: 'available', quantity: '4.000000', source_ids: [] },
        })),
      },
    });
    fixture.detectChanges();

    const bar = byTestId('receipt-progress');
    expect(bar?.getAttribute('role')).toBe('progressbar');
    expect(bar?.getAttribute('aria-valuenow')).toBe('40'); // 4 of the 10 ordered
    expect(component.receivedPercent()).toBe(40);
  });

  it('caps the progress at 100 when more than was ordered arrived', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const value = component.evidence()!;
    component.evidence.set({
      ...value,
      lifecycle: {
        ...value.lifecycle,
        lines: value.lifecycle.lines.map((line) => ({
          ...line,
          received: { state: 'available', quantity: '14.000000', source_ids: [] },
        })),
      },
    });
    expect(component.receivedPercent()).toBe(100);
  });

  // PPS-212: trace the order back to the RFQ and the quotation it came from.
  it('links to the RFQ and the quotation behind the source request', () => {
    const base = api.getOrder('order-1');
    base.subscribe((value) => {
      api.getOrder.and.returnValue(of({ ...value, order: { ...value.order, source_request_id: 'req-1' } }));
    }).unsubscribe();
    requests.getRequest.and.returnValue(of({
      id: 'req-1', source: { rfq_id: 'rfq-9', rfq_response_id: 'resp-1', quotation_id: 'quo-3', supplier_id: 's' },
    } as unknown as import('../../../core/api/models').PurchaseRequest));
    fixture = TestBed.createComponent(OrderDetailComponent);
    fixture.detectChanges();

    expect(byTestId('source-rfq-link')?.getAttribute('href')).toBe('/rfq/rfq-9');
    expect(byTestId('source-quotation-link')?.getAttribute('href')).toBe('/quotations/quo-3');
  });

  it('shows no RFQ or quotation links, and no error, when the request cannot be loaded', () => {
    fixture.detectChanges(); // the default spy fails
    expect(byTestId('source-rfq-link')).toBeNull();
    expect(byTestId('source-quotation-link')).toBeNull();
    expect(byTestId('action-error')).toBeNull();
  });
  // Review (Codex): 199 of 200 packs is not «100% received».
  it('never reads 100% until every line has fully arrived', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const value = component.evidence()!;
    const order = { ...value.order, lines: [{ ...value.order.lines[0], ordered_quantity: '200' }] };
    component.evidence.set({
      ...value,
      order,
      lifecycle: {
        ...value.lifecycle,
        lines: [{ ...value.lifecycle.lines[0], ordered_quantity: '200', received: { state: 'available', quantity: '199', source_ids: [] } }],
      },
    });
    expect(component.receivedPercent()).toBe(99);
  });

  // Review (Codex): packs of different products must not be added up as if they were alike.
  it('weights each line by its value, not by its pack count', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const value = component.evidence()!;
    const line = value.order.lines[0];
    const money = (amount: string) => ({ amount, currency: 'GBP' });
    component.evidence.set({
      ...value,
      order: {
        ...value.order,
        lines: [
          { ...line, id: 'a', ordered_quantity: '50', line_total: money('50.00') }, // cheap, many packs
          { ...line, id: 'b', ordered_quantity: '2', line_total: money('150.00') }, // dear, few packs
        ],
      },
      lifecycle: {
        ...value.lifecycle,
        lines: [
          { ...value.lifecycle.lines[0], purchase_order_line_id: 'a', ordered_quantity: '50', received: { state: 'available', quantity: '50', source_ids: [] } },
          { ...value.lifecycle.lines[0], purchase_order_line_id: 'b', ordered_quantity: '2', received: { state: 'pending', quantity: null, source_ids: [] } },
        ],
      },
    });
    expect(component.receivedPercent()).toBe(25); // 50 of 200 of the order's value
  });
  // Review (Codex, #471): a free line that has not arrived must keep the bar below 100.
  it('stays below 100 while a zero-value line has not arrived', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const value = component.evidence()!;
    const line = value.order.lines[0];
    const money = (amount: string) => ({ amount, currency: 'GBP' });
    component.evidence.set({
      ...value,
      order: {
        ...value.order,
        lines: [
          { ...line, id: 'paid', ordered_quantity: '10', line_total: money('100.00') },
          { ...line, id: 'free', ordered_quantity: '5', line_total: money('0.00') },
        ],
      },
      lifecycle: {
        ...value.lifecycle,
        lines: [
          { ...value.lifecycle.lines[0], purchase_order_line_id: 'paid', ordered_quantity: '10', received: { state: 'available', quantity: '10', source_ids: [] } },
          { ...value.lifecycle.lines[0], purchase_order_line_id: 'free', ordered_quantity: '5', received: { state: 'pending', quantity: null, source_ids: [] } },
        ],
      },
    });
    expect(component.receivedPercent()).toBe(99);

    component.evidence.set({
      ...component.evidence()!,
      lifecycle: {
        ...component.evidence()!.lifecycle,
        lines: component.evidence()!.lifecycle.lines.map((l) => ({
          ...l, received: { state: 'available', quantity: l.ordered_quantity, source_ids: [] },
        })),
      },
    });
    expect(component.receivedPercent()).toBe(100);
  });

  // PPS-212: say why a delivery was short, or what arrived damaged, on the line itself.
  it('sends the note typed against a line with the receipt and leaves blank notes out', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    component.receiptReference.set('GRN-9');
    component.receiptDate.set('2026-10-25');
    component.setQuantity('receipt', 'line-1', '4');
    component.setReceiptNote('line-1', '  two cartons crushed ');
    api.recordReceipt.and.returnValue(of(component.evidence()!));

    component.recordReceipt();

    const sent = api.recordReceipt.calls.mostRecent().args[1];
    expect(sent.lines[0].note).toBe('two cartons crushed');

    component.setReceiptNote('line-1', '   ');
    component.recordReceipt();
    expect(api.recordReceipt.calls.mostRecent().args[1].lines[0].note).toBeUndefined();
  });

  it('offers a note field on every receipt line and shows a recorded note with its receipt', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    fixture.detectChanges();
    expect(byTestId('receipt-note-line-1')).toBeTruthy();

    const current = component.evidence()!;
    component.evidence.set({
      ...current,
      receipts: [{
        id: 'r1', tenant_id: 't', purchase_order_id: current.order.id, receipt_reference: 'GRN-1',
        receipt_date: '2026-10-20', received_by: 'm', source_kind: 'manual', source_reference: 'GRN-1',
        created_at: '2026-10-20T10:00:00Z',
        lines: [{ id: 'rl1', purchase_order_line_id: 'line-1', received_quantity: '4', note: 'Short: supplier ran out' }],
      }] as never,
    });
    fixture.detectChanges();

    expect(byTestId('receipt-note')?.textContent).toContain('Short: supplier ran out');
  });

  // PPS-212: a back link from the order to the basket split that produced its request.
  it('links back to the basket split the order came from, and only then', () => {
    fixture.detectChanges();
    expect(byTestId('source-split-link')).toBeNull();

    const component = fixture.componentInstance;
    component.evidence.set({ ...component.evidence()!, source_split_job_id: 'job-7' });
    fixture.detectChanges();

    expect(byTestId('source-split-link')?.getAttribute('href')).toBe('/offers/basket-split/job-7');
  });

  it('does not carry a saved receipt note into the next receipt', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.receiptOpen.set(true);
    component.receiptReference.set('GRN-10');
    component.receiptDate.set('2026-10-25');
    component.setQuantity('receipt', 'line-1', '4');
    component.setReceiptNote('line-1', 'two cartons crushed');
    api.recordReceipt.and.returnValue(of(component.evidence()!));

    component.recordReceipt();

    expect(component.receiptNotes()).toEqual({});
  });

  it('names the order line a recorded receipt note belongs to', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const current = component.evidence()!;
    component.evidence.set({
      ...current,
      receipts: [{
        id: 'r1', tenant_id: 't', purchase_order_id: current.order.id, receipt_reference: 'GRN-1',
        receipt_date: '2026-10-20', received_by: 'm', source_kind: 'manual', source_reference: 'GRN-1',
        created_at: '2026-10-20T10:00:00Z',
        lines: [{ id: 'rl1', purchase_order_line_id: 'line-1', received_quantity: '4', note: 'Short: supplier ran out' }],
      }] as never,
    });
    fixture.detectChanges();

    const text = byTestId('receipt-note')?.textContent ?? '';
    expect(text).toContain(component.lineDescription(current.order.lines[0]));
    expect(text).toContain('Short: supplier ran out');
  });

  // PPS-205: `closed` can be set, from received only, behind a confirmation.
  it('offers Close only on received orders and asks first', fakeAsync(() => {
    const offered: Record<string, boolean> = {};
    for (const status of ['draft', 'submitted', 'confirmed', 'partially_received', 'received', 'closed', 'cancelled']) {
      fixture = TestBed.createComponent(OrderDetailComponent);
      showOrderAs(status);
      fixture.detectChanges();
      offered[status] = byTestId('close-order') !== null;
    }
    expect(offered).toEqual({
      draft: false, submitted: false, confirmed: false, partially_received: false,
      received: true, closed: false, cancelled: false,
    });

    fixture = TestBed.createComponent(OrderDetailComponent);
    showOrderAs('received');
    fixture.detectChanges();
    byTestId('close-order')!.click();
    fixture.detectChanges();
    tick();
    expect(api.closeOrder).not.toHaveBeenCalled();
    expect(byTestId('close-confirm-panel')?.contains(document.activeElement)).toBeTrue();
  }));

  it('closes the order after confirmation, reloads it and announces it', fakeAsync(() => {
    showOrderAs('received');
    fixture.detectChanges();
    api.closeOrder.and.returnValue(of({} as unknown as import('../orders-api').PurchaseOrder));
    byTestId('close-order')!.click();
    fixture.detectChanges();

    byTestId('confirm-close')!.click();
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(api.closeOrder).toHaveBeenCalledTimes(1);
    expect(byTestId('close-confirm-panel')).toBeNull();
    expect(byTestId('action-status')?.textContent).toContain('closed');
  }));

  it('keeps the order on screen and says why when closing fails', () => {
    showOrderAs('received');
    fixture.detectChanges();
    api.closeOrder.and.returnValue(throwError(() => ({
      status: 409, error: { code: 'conflict', details: { reason: 'order_not_closable' } },
    })));
    fixture.componentInstance.closeOrder();
    fixture.componentInstance.confirmClose();
    fixture.detectChanges();

    expect(byTestId('order-lines')).toBeTruthy();
    expect(byTestId('action-error')?.getAttribute('role')).toBe('alert');
  });

  // PPS-205: the timeline said nothing of how an order ended.
  it('puts a cancelled or closed order\'s ending in the timeline', () => {
    showOrderAs('cancelled');
    fixture.detectChanges();
    expect(byTestId('timeline-cancelled')).toBeTruthy();

    fixture = TestBed.createComponent(OrderDetailComponent);
    showOrderAs('closed');
    fixture.detectChanges();
    expect(byTestId('timeline-closed')).toBeTruthy();

    fixture = TestBed.createComponent(OrderDetailComponent);
    showOrderAs('submitted');
    fixture.detectChanges();
    expect(byTestId('timeline-cancelled')).toBeNull();
    expect(byTestId('timeline-closed')).toBeNull();
  });

  // PPS-205: undo a submit while nothing has been confirmed or received.
  it('offers Withdraw only on a submitted order that has no confirmation or receipt', () => {
    const offered: Record<string, boolean> = {};
    for (const status of ['draft', 'submitted', 'confirmed', 'partially_received', 'received', 'closed', 'cancelled']) {
      fixture = TestBed.createComponent(OrderDetailComponent);
      showOrderAs(status);
      fixture.detectChanges();
      offered[status] = byTestId('withdraw-order') !== null;
    }
    expect(offered).toEqual({
      draft: false, submitted: true, confirmed: false, partially_received: false,
      received: false, closed: false, cancelled: false,
    });

    fixture = TestBed.createComponent(OrderDetailComponent);
    showOrderAs('submitted');
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.evidence.set({
      ...component.evidence()!,
      receipts: [{ id: 'r1', lines: [] }] as never,
    });
    fixture.detectChanges();
    expect(byTestId('withdraw-order')).toBeNull();
  });

  it('asks before taking a submitted order back to a draft, then reloads it and says so', fakeAsync(() => {
    showOrderAs('submitted');
    fixture.detectChanges();
    api.withdrawOrder.and.returnValue(of({} as unknown as import('../orders-api').PurchaseOrder));

    byTestId('withdraw-order')!.click();
    fixture.detectChanges();
    tick();
    expect(api.withdrawOrder).not.toHaveBeenCalled();
    expect(byTestId('withdraw-confirm-panel')?.contains(document.activeElement)).toBeTrue();

    byTestId('confirm-withdraw')!.click();
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(api.withdrawOrder).toHaveBeenCalledTimes(1);
    expect(byTestId('withdraw-confirm-panel')).toBeNull();
    expect(byTestId('action-status')?.textContent).toContain('draft');
  }));

  it('keeps the order on screen and says why when withdrawing fails', () => {
    showOrderAs('submitted');
    fixture.detectChanges();
    api.withdrawOrder.and.returnValue(throwError(() => ({
      status: 409, error: { code: 'conflict', details: { reason: 'order_has_evidence' } },
    })));
    fixture.componentInstance.withdrawOrder();
    fixture.componentInstance.confirmWithdraw();
    fixture.detectChanges();

    expect(byTestId('order-lines')).toBeTruthy();
    expect(byTestId('action-error')?.getAttribute('role')).toBe('alert');
    expect(byTestId('action-error')?.textContent).toContain('already has a supplier confirmation');
  });
});
