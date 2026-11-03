import { isOrderOverdue, orderToCsv } from './order-helpers';
import type { PurchaseOrder } from './orders-api';

const order = (overrides: Partial<PurchaseOrder> = {}): PurchaseOrder => ({
  id: 'o1', tenant_id: 't', order_number: 'PO-1001', supplier_id: 's', supplier_name: 'الذهبي للتموين',
  status: 'submitted', order_date: '2026-11-02', expected_delivery_date: '2026-11-05',
  total: { amount: '1245.0000', currency: 'SAR' }, tax: { amount: '162.3900', currency: 'SAR' },
  source_kind: 'manual', source_reference: 'PO-1001', source_hash: null, created_by: 'm',
  created_at: '2026-11-02T10:00:00Z', updated_at: '2026-11-02T10:00:00Z',
  lines: [{
    id: 'l1', line_number: 1, workspace_product_id: 'p1', description: 'أرز بسمتي (كيس 10 كجم)',
    ordered_quantity: '3.000000', base_unit: 'kilogram', pack_base_quantity: '10.000000',
    unit_price: { amount: '73.9100', currency: 'SAR' }, tax: { amount: '28.9300', currency: 'SAR' },
    line_total: { amount: '250.6600', currency: 'SAR' },
  }],
  ...overrides,
} as PurchaseOrder);

describe('isOrderOverdue (P-188)', () => {
  const today = new Date(2026, 10, 6); // 6 Nov 2026

  it('is overdue when the expected date has passed and goods are still expected', () => {
    expect(isOrderOverdue(order({ expected_delivery_date: '2026-11-05' }), today)).toBeTrue();
    expect(isOrderOverdue(order({ status: 'confirmed', expected_delivery_date: '2026-11-05' }), today)).toBeTrue();
    expect(isOrderOverdue(order({ status: 'partially_received', expected_delivery_date: '2026-11-05' }), today)).toBeTrue();
  });

  it('is not overdue on the expected day, before it, or without a date', () => {
    expect(isOrderOverdue(order({ expected_delivery_date: '2026-11-06' }), today)).toBeFalse();
    expect(isOrderOverdue(order({ expected_delivery_date: '2026-11-07' }), today)).toBeFalse();
    expect(isOrderOverdue(order({ expected_delivery_date: null }), today)).toBeFalse();
  });

  it('is never overdue for drafts or finished orders', () => {
    for (const status of ['draft', 'received', 'closed', 'cancelled'] as const) {
      expect(isOrderOverdue(order({ status, expected_delivery_date: '2026-11-01' }), today)).toBeFalse();
    }
  });
});

describe('orderToCsv (P-188)', () => {
  it('writes a header, one row per line, the currency and a BOM so Arabic opens in Excel', () => {
    const csv = orderToCsv(order());
    expect(csv.startsWith('﻿')).toBeTrue();
    const rows = csv.slice(1).split('\r\n');
    expect(rows[0]).toBe(
      'order_number,supplier,status,order_date,expected_delivery_date,line_number,description,quantity_packs,base_unit,pack_base_quantity,unit_price,line_tax,line_total,currency',
    );
    expect(rows[1]).toBe(
      'PO-1001,الذهبي للتموين,submitted,2026-11-02,2026-11-05,1,أرز بسمتي (كيس 10 كجم),3,kilogram,10,73.91,28.93,250.66,SAR',
    );
    expect(rows).toHaveSize(2);
  });

  it('quotes cells with commas, quotes and line breaks', () => {
    const csv = orderToCsv(order({ supplier_name: 'Acme, "Fresh" Foods' }));
    expect(csv).toContain('"Acme, ""Fresh"" Foods"');
  });

  it('neutralises spreadsheet formulas in text cells', () => {
    const base = order();
    const csv = orderToCsv(order({
      supplier_name: '=HYPERLINK("http://evil")',
      lines: [{ ...base.lines[0], description: '+SUM(A1)' }],
    }));
    expect(csv).toContain("\"'=HYPERLINK(\"\"http://evil\"\")\"");
    expect(csv).toContain(",'+SUM(A1),");
  });
});
