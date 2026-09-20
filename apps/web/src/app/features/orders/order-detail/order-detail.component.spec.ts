import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { OrdersApiService } from '../orders-api';
import { OrderDetailComponent } from './order-detail.component';

describe('OrderDetailComponent', () => {
  let fixture: ComponentFixture<OrderDetailComponent>;
  let api: jasmine.SpyObj<OrdersApiService>;

  beforeEach(async () => {
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
          id: 'line-1', line_number: 1, workspace_product_id: null, description: 'Paper', ordered_quantity: '10',
          base_unit: 'each', unit_price: { amount: '12.00', currency: 'GBP' }, tax: { amount: '0.00', currency: 'GBP' },
          line_total: { amount: '120.00', currency: 'GBP' },
        }],
      },
      confirmation: null, receipts: [], lifecycle: {
        purchase_order_id: 'order-1', status: 'submitted', confirmation: 'pending', receipt: 'pending',
        lines: [{ purchase_order_line_id: 'line-1', ordered_quantity: '10',
          confirmed: { state: 'pending', quantity: null, source_ids: [] },
          received: { state: 'pending', quantity: null, source_ids: [] }, remaining_quantity: null, over_received_quantity: null }],
      },
    }));
    await TestBed.configureTestingModule({
      imports: [OrderDetailComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(), provideNoopAnimations(), provideRouter([]), { provide: OrdersApiService, useValue: api },
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'order-1' } } } },
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      orders: {
        backToOrders: 'Back', retry: 'Retry', loadError: 'Load failed', saveError: 'Save failed', notProvided: 'Not provided',
        status: { submitted: 'Submitted' }, evidence: { pending: 'Pending' },
        detail: {
          eyebrow: 'Purchase order', createdAt: 'Created {{date}}', orderDate: 'Order date', expectedDelivery: 'Expected',
          total: 'Total', confirmation: 'Confirmation', receipt: 'Receipt', linesTitle: 'Lines', linesSubtitle: 'Evidence',
          ordered: 'Ordered', confirmed: 'Confirmed', received: 'Received', remaining: 'Remaining', actionsTitle: 'Actions',
          actionsSubtitle: 'Internal', submit: 'Submit', recordConfirmation: 'Confirm', recordReceipt: 'Receive',
          confirmationFormTitle: 'Confirmation', receiptFormTitle: 'Receipt', reference: 'Reference', confirmedDate: 'Date',
          receivedDate: 'Date', confirmedQuantity: 'Quantity', receivedQuantity: 'Quantity', save: 'Save',
          timelineTitle: 'Timeline', orderCreated: 'Created', confirmationRecorded: 'Confirmed', receiptRecorded: 'Receipt {{reference}}',
        },
      },
    });
    TestBed.inject(TranslateService).use('en');
    fixture = TestBed.createComponent(OrderDetailComponent);
  });

  it('renders pending evidence and exposes lifecycle actions', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="order-lines"]')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Pending');
    expect(fixture.nativeElement.textContent).toContain('Paper');
    expect(fixture.nativeElement.textContent).toContain('Confirm');
    expect(fixture.nativeElement.textContent).toContain('Receive');
  });
});
