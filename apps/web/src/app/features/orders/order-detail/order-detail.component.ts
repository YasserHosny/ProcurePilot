import { Component, ElementRef, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DateAdapter } from '@angular/material/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { lineDescription, packLabel } from '../pack-label';
import { RequestsApiService } from '../../requests/requests-api';
import type { PurchaseRequest } from '../../../core/api/models';
import { isOrderOverdue, orderToCsv } from '../order-helpers';

import { FormatService } from '../../../core/format/format.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { AppDateAdapter, provideAppDateAdapter } from '../../../core/i18n/date-adapter';
import {
  OrdersApiService,
  type EvidenceState,
  type LifecycleLineSummary,
  type OrderEvidenceProjection,
  type PurchaseOrderLine,
} from '../orders-api';

@Component({
  selector: 'app-order-detail',
  standalone: true,
  providers: [provideAppDateAdapter()],
  imports: [
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './order-detail.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './order-detail.component.scss',
})
export class OrderDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly ordersApi = inject(OrdersApiService);
  private readonly translate = inject(TranslateService);
  private readonly formatService = inject(FormatService);
  private readonly requestsApi = inject(RequestsApiService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly dateAdapter = inject(DateAdapter) as AppDateAdapter;

  readonly evidence = signal<OrderEvidenceProjection | null>(null);
  /** The request this order was made from, for the RFQ and quotation links; null when unknown. */
  readonly sourceRequest = signal<PurchaseRequest | null>(null);
  readonly isLoading = signal(true);
  readonly isSaving = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly confirmationOpen = signal(false);
  readonly receiptOpen = signal(false);
  readonly cancelOpen = signal(false);
  readonly submitOpen = signal(false);
  readonly actionError = signal<string | null>(null);
  /** Polite announcement of the last successful action, for screen readers. */
  readonly actionStatus = signal('');
  readonly receiptQuantityError = signal(false);
  readonly confirmationReference = signal('');
  readonly confirmationDate = signal('');
  readonly receiptReference = signal('');
  readonly receiptDate = signal('');
  readonly confirmationDateModel = computed(() => parseIsoDateLocal(this.confirmationDate()));
  readonly receiptDateModel = computed(() => parseIsoDateLocal(this.receiptDate()));
  readonly confirmationQuantities = signal<Record<string, string>>({});
  readonly receiptQuantities = signal<Record<string, string>>({});
  readonly receiptNotes = signal<Record<string, string>>({});

  onConfirmationDateChange(date: Date | null): void {
    this.confirmationDate.set(toIsoDateOrNull(date) ?? '');
  }

  onReceiptDateChange(date: Date | null): void {
    this.receiptDate.set(toIsoDateOrNull(date) ?? '');
  }

  private orderId = '';

  ngOnInit(): void {
    this.orderId = this.route.snapshot.paramMap.get('id') ?? '';
    this.loadOrder();
  }

  loadOrder(): void {
    if (!this.orderId) return;
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.ordersApi.getOrder(this.orderId).subscribe({
      next: (value) => {
        this.evidence.set(value);
        this.isLoading.set(false);
        this.loadSourceRequest(value.order.source_request_id);
      },
      error: () => { this.errorMessage.set(this.translate.instant('orders.loadError')); this.isLoading.set(false); },
    });
  }

  /** Best effort: without the request the page just has no RFQ or quotation links. */
  private loadSourceRequest(requestId: string | null | undefined): void {
    this.sourceRequest.set(null);
    if (!requestId) return;
    this.requestsApi.getRequest(requestId).subscribe({
      next: (request) => this.sourceRequest.set(request),
      error: () => this.sourceRequest.set(null),
    });
  }

  /**
   * How much of the order has arrived (0-100), each line weighted by its value: packs of
   * different products are not comparable (ADR-020), a line's value is. Over-receipt counts only
   * up to what was ordered, and 100 shows only when every line has fully arrived.
   */
  receivedPercent(): number {
    const order = this.evidence()?.order;
    const lines = this.evidence()?.lifecycle.lines ?? [];
    if (!order || lines.length === 0) return 0;
    const value = (lineId: string) =>
      parseFloat(order.lines.find((line) => line.id === lineId)?.line_total.amount ?? '') || 0;
    const total = lines.reduce((sum, line) => sum + value(line.purchase_order_line_id), 0);
    // A PO whose lines carry no value still has progress: weigh the lines equally.
    const weight = (lineId: string) => (total > 0 ? value(lineId) : 1);
    const weights = lines.reduce((sum, line) => sum + weight(line.purchase_order_line_id), 0);
    const arrived = lines.reduce((sum, line) => {
      const ordered = parseFloat(line.ordered_quantity) || 0;
      const received = parseFloat(line.received.quantity ?? '') || 0;
      return sum + (ordered > 0 ? Math.min(received / ordered, 1) : 0) * weight(line.purchase_order_line_id);
    }, 0);
    // A line that carries no value has no weight, so completion is checked line by line.
    const everyLineArrived = lines.every(
      (line) =>
        (parseFloat(line.ordered_quantity) || 0) <= 0 ||
        (parseFloat(line.received.quantity ?? '') || 0) >= parseFloat(line.ordered_quantity),
    );
    const percent = Math.floor((arrived / weights) * 100 + 1e-9);
    return everyLineArrived ? 100 : Math.min(99, percent);
  }

  readonly lineDescription = lineDescription;

  linePriceLabel(line: PurchaseOrderLine): string {
    const { size, unit, label } = packLabel(
      line.pack_base_quantity, line.base_unit, this.translate, this.formatService,
    );
    const amount = this.formatService.formatMoney(line.unit_price);
    if (label !== null) {
      const base = this.formatService.formatMoney({ amount: String(parseFloat(line.unit_price.amount) / size), currency: line.unit_price.currency });
      return `${amount} / ${label} · ${base} / ${unit}`;
    }
    return `${amount} / ${unit}`;
  }

  formatQuantity(value: string | null): string {
    return value === null
      ? this.translate.instant('orders.notProvided')
      : this.formatService.formatExactQuantity(value);
  }

  lineRemainingQuantity(summary: LifecycleLineSummary): string {
    if (summary.remaining_quantity !== null && summary.remaining_quantity !== undefined) {
      return this.formatService.formatExactQuantity(summary.remaining_quantity);
    }
    const ordered = parseFloat(summary.ordered_quantity) || 0;
    const received = summary.received?.quantity ? parseFloat(summary.received.quantity) || 0 : 0;
    const remaining = Math.max(0, ordered - received);
    return this.formatService.formatExactQuantity(String(remaining));
  }

  /** Purchase outcomes (savings) can be recorded from a sent order, not a draft or cancelled one. */
  canRecordOutcome(status: string): boolean {
    return ['submitted', 'confirmed', 'partially_received', 'received', 'closed'].includes(status);
  }

  getStatusLabel(status: string): string { return this.translate.instant(`orders.status.${status}`); }
  getEvidenceLabel(state: EvidenceState): string { return this.translate.instant(`orders.evidence.${state}`); }

  lineSummary(lineId: string): LifecycleLineSummary | undefined {
    return this.evidence()?.lifecycle.lines.find((line) => line.purchase_order_line_id === lineId);
  }

  quantityValue(values: Record<string, string>, line: PurchaseOrderLine): string {
    return values[line.id] ?? '';
  }

  setQuantity(kind: 'confirmation' | 'receipt', lineId: string, value: string): void {
    if (kind === 'receipt') this.receiptQuantityError.set(false);
    const target = kind === 'confirmation' ? this.confirmationQuantities : this.receiptQuantities;
    target.set({ ...target(), [lineId]: value });
  }

  setReceiptNote(lineId: string, value: string): void {
    this.receiptNotes.set({ ...this.receiptNotes(), [lineId]: value });
  }

  /** What a recorded receipt line was for, so its note reads on its own. */
  receiptLineName(lineId: string): string {
    const line = this.evidence()?.order.lines.find((candidate) => candidate.id === lineId);
    return line ? lineDescription(line) : '';
  }

  readonly isOverdue = isOrderOverdue;

  /** Hands the browser a file to save; separate so tests do not need a real download. */
  saveFile(name: string, content: string): void {
    const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  }

  exportCsv(): void {
    const order = this.evidence()?.order;
    if (order) this.saveFile(`${order.order_number}.csv`, orderToCsv(order));
  }

  printOrder(): void {
    window.print();
  }

  /** Puts what is still to be received on every line that has something left. */
  receiveAll(): void {
    const quantities: Record<string, string> = { ...this.receiptQuantities() };
    for (const summary of this.evidence()?.lifecycle.lines ?? []) {
      const remaining = Math.max(0, (parseFloat(summary.ordered_quantity) || 0) - (parseFloat(summary.received.quantity ?? '') || 0));
      if (remaining > 0) quantities[summary.purchase_order_line_id] = String(Math.round(remaining * 1e6) / 1e6);
    }
    this.receiptQuantities.set(quantities);
    this.receiptQuantityError.set(false);
  }

  /** Cancel is offered until goods are fully received (spec 016 FR-020: partially received can be cancelled). */
  canCancel(status: string): boolean {
    return ['draft', 'submitted', 'confirmed', 'partially_received'].includes(status);
  }

  private failWith(err: unknown): void {
    const reason = (err as { error?: { details?: { reason?: unknown } } })?.error?.details?.reason;
    const key = typeof reason === 'string' ? `orders.detail.errors.${reason}` : null;
    const specific = key ? this.translate.instant(key) : null;
    this.actionError.set(specific && specific !== key ? specific : this.translate.instant('orders.saveError'));
    this.isSaving.set(false);
  }

  /** The hint follows the order the date input really parses (English US workspaces type month-first). */
  dateFormatHintKey(): string {
    return this.dateAdapter.isDayFirst()
      ? 'orders.detail.dateFormatHintDayFirst'
      : 'orders.detail.dateFormatHintMonthFirst';
  }

  private announce(key: string): void {
    // Clear first: the same message twice leaves the text unchanged and a live region stays quiet.
    this.actionStatus.set('');
    const message = this.translate.instant(key);
    setTimeout(() => this.actionStatus.set(message));
  }

  /** Moves focus into an inline confirmation once it has rendered. */
  private focusPanel(testId: string): void {
    setTimeout(() => {
      this.host.nativeElement.querySelector<HTMLElement>(`[data-testid="${testId}"] h3`)?.focus();
    });
  }

  /** Quantities on the order are in packs (ADR-020), so the unit shown is the pack when there is one. */
  quantityLabel(kind: 'confirmed' | 'received', line: PurchaseOrderLine): string {
    const { unit, label } = packLabel(
      line.pack_base_quantity, line.base_unit, this.translate, this.formatService,
    );
    return this.translate.instant(`orders.detail.${kind}QuantityFor`, {
      product: lineDescription(line),
      unit: label ?? unit,
      ordered: this.formatQuantity(line.ordered_quantity),
    });
  }

  requestSubmit(): void {
    this.actionError.set(null);
    this.submitOpen.set(true);
    this.focusPanel('submit-confirm-panel');
  }

  submitOrder(): void {
    this.isSaving.set(true);
    this.actionError.set(null);
    this.actionStatus.set('');
    this.ordersApi.submitOrder(this.orderId).subscribe({
      next: () => { this.submitOpen.set(false); this.loadOrder(); this.isSaving.set(false); this.announce('orders.detail.submitted'); },
      error: (err: unknown) => this.failWith(err),
    });
  }

  cancelOrder(): void {
    this.actionError.set(null);
    this.cancelOpen.set(true);
    this.focusPanel('cancel-confirm-panel');
  }

  confirmCancel(): void {
    this.isSaving.set(true);
    this.actionError.set(null);
    this.ordersApi.cancelOrder(this.orderId).subscribe({
      next: () => {
        this.loadOrder();
        this.cancelOpen.set(false);
        this.isSaving.set(false);
        this.announce('orders.detail.cancelled');
      },
      error: (err: unknown) => this.failWith(err),
    });
  }

  recordConfirmation(): void {
    const current = this.evidence();
    if (!current || !this.confirmationReference().trim() || !this.confirmationDate()) return;
    this.actionError.set(null);
    this.isSaving.set(true);
    this.ordersApi.recordConfirmation(this.orderId, {
      supplier_reference: this.confirmationReference().trim(),
      confirmed_at: `${this.confirmationDate()}T12:00:00Z`,
      expected_delivery_date: null,
      source_kind: 'manual',
      source_reference: this.confirmationReference().trim(),
      lines: current.order.lines.map((line) => ({
        purchase_order_line_id: line.id,
        confirmed_quantity: this.quantityValue(this.confirmationQuantities(), line) || '0',
        confirmed_unit_price: null,
      })),
    }).subscribe({
      next: (value) => { this.evidence.set(value); this.confirmationOpen.set(false); this.isSaving.set(false); this.announce('orders.detail.confirmationSaved'); },
      error: (err: unknown) => this.failWith(err),
    });
  }

  recordReceipt(): void {
    const current = this.evidence();
    if (!current || !this.receiptReference().trim() || !this.receiptDate()) return;
    const quantities = this.receiptQuantities();
    if (!current.order.lines.some((line) => (parseFloat(quantities[line.id] ?? '') || 0) > 0)) {
      this.receiptQuantityError.set(true);
      return;
    }
    this.receiptQuantityError.set(false);
    this.actionError.set(null);
    this.isSaving.set(true);
    this.ordersApi.recordReceipt(this.orderId, {
      receipt_reference: this.receiptReference().trim(),
      receipt_date: this.receiptDate(),
      source_kind: 'manual',
      source_reference: this.receiptReference().trim(),
      lines: current.order.lines.map((line) => {
        const note = (this.receiptNotes()[line.id] ?? '').trim();
        return {
          purchase_order_line_id: line.id,
          received_quantity: this.quantityValue(this.receiptQuantities(), line) || '0',
          ...(note ? { note } : {}),
        };
      }),
    }).subscribe({
      next: (value) => { this.evidence.set(value); this.receiptOpen.set(false); this.receiptNotes.set({}); this.isSaving.set(false); this.announce('orders.detail.receiptSaved'); },
      error: (err: unknown) => this.failWith(err),
    });
  }
}
