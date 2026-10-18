import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
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
      'getOrder', 'submitOrder', 'recordConfirmation', 'recordReceipt',
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
      imports: [OrderDetailComponent, TranslateModule.forRoot()],
      providers: [
        { provide: ApiService, useValue: catalogue },
        provideHttpClient(), provideNoopAnimations(), provideRouter([]), { provide: OrdersApiService, useValue: api },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'order-1' } } } },
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      rfq: { email: { units: { kilogram: 'kg', litre: 'L' } } },
      orders: {
        create: { packUnit: 'pack of {{size}} {{unit}}' },
        backToOrders: 'Back', retry: 'Retry', loadError: 'Load failed', saveError: 'Save failed', notProvided: 'Not provided',
        status: { submitted: 'Submitted' }, evidence: { pending: 'Pending' },
        detail: {
          eyebrow: 'Purchase order', createdAt: 'Created {{date}}', orderDate: 'Order date', expectedDelivery: 'Expected',
          total: 'Total', confirmation: 'Confirmation', receipt: 'Receipt', linesTitle: 'Lines', linesSubtitle: 'Evidence',
          ordered: 'Ordered', confirmed: 'Confirmed', received: 'Received', remaining: 'Remaining', actionsTitle: 'Actions',
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
    expect(label).toContain('20.00 / L');
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
});
