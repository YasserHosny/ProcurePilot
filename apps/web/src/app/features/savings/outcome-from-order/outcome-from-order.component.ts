import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { concatMap, from, toArray } from 'rxjs';

import type { ApiError } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { toLocalMidnightIsoOrNull } from '../../../core/format/iso-date';
import { packLabel } from '../../orders/pack-label';
import {
  type PurchaseDeliveryResult,
  type PurchaseOutcomeCreate,
  type PurchaseOutcomePrefill,
  type PurchaseOutcomePrefillLine,
  SavingsApiService,
} from '../savings-api';

const QUANTITY_PATTERN = /^\d+(\.\d{1,6})?$/;
const AMOUNT_PATTERN = /^\d+(\.\d{1,4})?$/;

export interface EditableOutcomeLine {
  readonly line: PurchaseOutcomePrefillLine;
  readonly include: boolean;
  readonly quantity: string;
  readonly total: string;
}

/**
 * Records purchase outcomes from a purchase order (demo finding 22): one line per PO line,
 * pre-filled in base units by the API (ADR-020) and editable before saving. Each line is sent to
 * POST /purchases linked to its PO line, so the savings baseline excludes this order.
 */
@Component({
  selector: 'app-outcome-from-order',
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './outcome-from-order.component.html',
  styleUrl: './outcome-from-order.component.scss',
})
export class OutcomeFromOrderComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly savingsApi = inject(SavingsApiService);
  private readonly translate = inject(TranslateService);
  private readonly format = inject(FormatService);
  private readonly snackBar = inject(MatSnackBar);

  readonly prefill = signal<PurchaseOutcomePrefill | null>(null);
  readonly lines = signal<readonly EditableOutcomeLine[]>([]);
  readonly deliveryResult = signal<PurchaseDeliveryResult>('ordered');
  readonly isLoading = signal(true);
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly deliveryResults: readonly PurchaseDeliveryResult[] = [
    'ordered',
    'partially_delivered',
    'delivered',
    'cancelled',
    'disputed',
  ];

  readonly selectedCount = computed(() => this.lines().filter((l) => l.include).length);
  readonly canSubmit = computed(
    () =>
      !this.isSubmitting() &&
      this.selectedCount() > 0 &&
      this.lines().every((l) => !l.include || this.lineValid(l)),
  );

  orderId = '';
  // One Idempotency-Key per PO line for the life of the page, so a retry after a partial failure
  // replays the lines that were already saved instead of creating duplicates.
  private readonly keys = new Map<string, string>();

  ngOnInit(): void {
    this.orderId = this.route.snapshot.paramMap.get('id') ?? '';
    this.load();
  }

  load(): void {
    if (!this.orderId) return;
    this.isLoading.set(true);
    this.savingsApi.getPurchasePrefill(this.orderId).subscribe({
      next: (value) => {
        this.prefill.set(value);
        this.deliveryResult.set(value.delivery_result);
        this.lines.set(
          value.lines.map((line) => ({
            line,
            include: line.recordable,
            quantity: line.quantity,
            total: line.total_paid.amount,
          })),
        );
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.errorMessage.set(this.messageFor(err, 'savings.fromOrder.loadError'));
        this.isLoading.set(false);
      },
    });
  }

  update(index: number, patch: Partial<Pick<EditableOutcomeLine, 'include' | 'quantity' | 'total'>>): void {
    this.lines.set(this.lines().map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  lineValid(line: EditableOutcomeLine): boolean {
    return (
      QUANTITY_PATTERN.test(line.quantity.trim()) &&
      parseFloat(line.quantity) > 0 &&
      AMOUNT_PATTERN.test(line.total.trim())
    );
  }

  unitLabel(line: PurchaseOutcomePrefillLine): string {
    return packLabel(null, line.base_unit, this.translate, this.format).unit;
  }

  conversionLabel(line: PurchaseOutcomePrefillLine): string {
    const { unit, label } = packLabel(line.pack_base_quantity, line.base_unit, this.translate, this.format);
    return this.translate.instant('savings.fromOrder.conversion', {
      packs: this.format.formatExactQuantity(line.ordered_packs),
      pack: label ?? unit,
      quantity: this.format.formatExactQuantity(line.quantity),
      unit,
    });
  }

  unitPrice(line: EditableOutcomeLine): string | null {
    if (!this.lineValid(line)) return null;
    return (parseFloat(line.total) / parseFloat(line.quantity)).toFixed(4);
  }

  submit(): void {
    const order = this.prefill();
    if (!order || !this.canSubmit()) return;
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    const selected = this.lines().filter((l) => l.include);
    from(selected)
      .pipe(
        concatMap((line) =>
          this.savingsApi.recordPurchase(this.payload(order, line), this.keyFor(line.line)),
        ),
        toArray(),
      )
      .subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.snackBar.open(
            this.translate.instant('savings.fromOrder.success', { count: selected.length }),
            undefined,
            { duration: 4000 },
          );
          void this.router.navigate(['/savings']);
        },
        error: (err: unknown) => {
          this.isSubmitting.set(false);
          this.errorMessage.set(this.messageFor(err, 'savings.fromOrder.saveError'));
          this.load();
        },
      });
  }

  private payload(order: PurchaseOutcomePrefill, edit: EditableOutcomeLine): PurchaseOutcomeCreate {
    const currency = edit.line.total_paid.currency;
    return {
      workspace_product_id: edit.line.workspace_product_id ?? '',
      supplier_id: order.supplier_id,
      purchase_order_line_id: edit.line.purchase_order_line_id,
      quantity: edit.quantity.trim(),
      base_unit: edit.line.base_unit,
      unit_price: { amount: this.unitPrice(edit) ?? '0', currency },
      total_paid: { amount: edit.total.trim(), currency },
      delivery_result: this.deliveryResult(),
      ordered_at: toLocalMidnightIsoOrNull(order.order_date),
      notes: null,
    };
  }

  private keyFor(line: PurchaseOutcomePrefillLine): string {
    let key = this.keys.get(line.purchase_order_line_id);
    if (!key) {
      key = crypto.randomUUID();
      this.keys.set(line.purchase_order_line_id, key);
    }
    return key;
  }

  private messageFor(err: unknown, fallbackKey: string): string {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      const reason = apiError?.details?.['reason'];
      if (reason === 'purchase_order_not_recordable') {
        return this.translate.instant('savings.fromOrder.notRecordable');
      }
      if (reason === 'purchase_order_line_already_recorded') {
        return this.translate.instant('savings.fromOrder.alreadyRecorded');
      }
    }
    return this.translate.instant(fallbackKey);
  }
}
