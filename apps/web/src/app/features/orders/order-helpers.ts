import { toIsoDate } from '../../core/format/iso-date';
import type { PurchaseOrder } from './orders-api';

/** Orders whose goods are still expected: a late date means something. */
const OPEN_STATUSES: readonly string[] = ['submitted', 'confirmed', 'partially_received'];

/** True when the expected delivery date has passed and the goods have not all arrived. */
export function isOrderOverdue(order: Pick<PurchaseOrder, 'status' | 'expected_delivery_date'>, today: Date = new Date()): boolean {
  if (!order.expected_delivery_date || !OPEN_STATUSES.includes(order.status)) return false;
  return order.expected_delivery_date < toIsoDate(today);
}

const HEADER = [
  'order_number', 'supplier', 'status', 'order_date', 'expected_delivery_date', 'line_number',
  'description', 'quantity_packs', 'base_unit', 'pack_base_quantity', 'unit_price', 'line_tax',
  'line_total', 'currency',
];

/** «3.000000» -> «3», «73.9100» -> «73.91». */
function trimDecimal(value: string | null | undefined): string {
  if (!value) return '';
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}

/** A text cell that a spreadsheet would run as a formula is turned into plain text. */
function textCell(value: string | null | undefined): string {
  const text = value ?? '';
  return /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
}

function quote(cell: string): string {
  return /[",\r\n]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell;
}

/** One row per order line, UTF-8 with a BOM so Excel reads Arabic, CRLF line ends. */
export function orderToCsv(order: PurchaseOrder): string {
  const rows = order.lines.map((line) =>
    [
      textCell(order.order_number),
      textCell(order.supplier_name),
      order.status,
      order.order_date,
      order.expected_delivery_date ?? '',
      String(line.line_number),
      textCell(line.description),
      trimDecimal(line.ordered_quantity),
      textCell(line.base_unit),
      trimDecimal(line.pack_base_quantity),
      trimDecimal(line.unit_price.amount),
      trimDecimal(line.tax.amount),
      trimDecimal(line.line_total.amount),
      order.total.currency,
    ].map(quote).join(','),
  );
  return '\ufeff' + [HEADER.join(','), ...rows].join('\r\n');
}
