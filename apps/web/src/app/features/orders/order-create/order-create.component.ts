import { parseIsoDateLocal, toIsoDate } from '../../../core/format/iso-date';
import { FormatService } from '../../../core/format/format.service';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatOptionModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { SessionService } from '../../../core/auth/session.service';
import type { Branch, PurchaseRequest, PurchaseRequestLine } from '../../../core/api/models';
import type { RequestAllocation } from '../orders-api';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { catchError, forkJoin, of } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Product, Supplier } from '../../../core/api/models';
import {
  OrdersApiService,
  type PurchaseOrder,
  type PurchaseOrderCreate,
  type RequestAllocationOrder,
} from '../orders-api';
import { packLabel } from '../pack-label';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';
import { formatMoneyUnits, lineNetUnits, moneyUnits, splitVatInclusiveLine } from '../vat-split';

interface OrderLineForm {
  workspace_product_id: FormControl<string | null>;
  description: FormControl<string>;
  quantity: FormControl<number | null>;
  base_unit: FormControl<string>;
  unit_price: FormControl<number | null>;
  line_tax: FormControl<number | null>;
  source_request_line_id: FormControl<string | null>;
  remaining_quantity: FormControl<number | null>;
  estimated_price: FormControl<number | null>;
}

@Component({
  selector: 'app-order-create',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatOptionModule,
    RouterLink,
    TranslatePipe,
    FormatMoneyPipe,
  ],
  providers: [provideAppDateAdapter()],
  templateUrl: './order-create.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './order-create.component.scss',
})
export class OrderCreateComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly formatService = inject(FormatService);
  private readonly api = inject(ApiService);
  private readonly ordersApi = inject(OrdersApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly requestsApi = inject(RequestsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly session = inject(SessionService);
  private readonly destroyRef = inject(DestroyRef);
  readonly homeCurrency = this.session.homeCurrency() ?? 'USD';

  readonly suppliers = signal<Supplier[]>([]);
  readonly products = signal<Product[]>([]);
  readonly branches = signal<Branch[]>([]);

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const b of this.branches()) {
      byId.set(b.id, b.name);
    }
    return byId;
  });

  sourceSupplierName(): string {
    return (
      this.sourceRequest()?.source?.supplier_name ||
      this.suppliers().find(s => s.id === this.form.controls.supplier_id.value)?.name ||
      ''
    );
  }

  sourceBranchName(): string {
    const branchId = this.sourceRequest()?.branch_id;
    return branchId ? this.branchNameById().get(branchId) || branchId : '';
  }

  readonly isSubmitting = signal(false);
  readonly savedOrder = signal<PurchaseOrder | null>(null);
  readonly navigationFailed = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly sourceRequest = signal<PurchaseRequest | null>(null);
  // Currency of the supplier quote the unit prices were pre-filled from; the order must use it.
  private readonly quotedCurrency = signal<string | null>(null);
  // Pre-filled quoted price per source request line; the quote currency is enforced only while
  // at least one of these values is still in the form unchanged.
  private readonly prefilledQuotes = new Map<string, number>();

  private inclusiveQuote(line: FormGroup<OrderLineForm>): PurchaseRequestLine | null {
    const requestLine = this.sourceRequest()?.lines.find(
      candidate => candidate.id === line.controls.source_request_line_id.value,
    );
    if (!requestLine?.quoted_prices_include_vat || !requestLine.quoted_net_unit_price ||
        !requestLine.quoted_unit_price || !requestLine.quoted_vat_rate ||
        !this.prefilledQuotes.has(requestLine.id)) return null;
    return requestLine;
  }

  vatInclusiveHint(line: FormGroup<OrderLineForm>): string | null {
    const quote = this.inclusiveQuote(line);
    if (!quote) return null;
    return this.translate.instant('orders.create.vatInclusiveHint', {
      rate: this.formatService.formatNumber(Number(quote.quoted_vat_rate) * 100),
      gross: this.formatService.formatMoney(quote.quoted_unit_price),
    });
  }

  private lineTotalUnits(line: ReturnType<FormGroup<OrderLineForm>['getRawValue']>): bigint {
    return lineNetUnits(line.unit_price || 0, line.quantity || 0) + moneyUnits(line.line_tax || 0);
  }

  packDescription(product: Product | undefined): string | null {
    return packLabel(product?.pack, product?.base_unit ?? '', this.translate, this.formatService).label;
  }

  packHint(line: FormGroup<OrderLineForm>): string | null {
    const product = this.products().find(p => p.id === line.controls.workspace_product_id.value);
    const requestLine = this.sourceRequest()?.lines.find(
      candidate => candidate.id === line.controls.source_request_line_id.value,
    );
    if (requestLine?.pack_base_quantity != null) {
      return packLabel(
        requestLine.pack_base_quantity,
        requestLine.base_unit ?? product?.base_unit ?? line.controls.base_unit.value,
        this.translate,
        this.formatService,
      ).label;
    }
    return this.packDescription(product);
  }

  private requestLineDescription(product: Product | undefined): string {
    return product?.tenant_name || '';
  }

  readonly requestAllocations = signal<RequestAllocation | null>(null);
  readonly editOrderId = signal<string | null>(null);

  readonly allocatedOrders = computed<RequestAllocationOrder[]>(() => {
    return this.requestAllocations()?.orders ?? [];
  });

  readonly isFullyOrdered = computed<boolean>(() => {
    if (this.editOrderId()) return false;
    const req = this.sourceRequest();
    const alloc = this.requestAllocations();
    if (!req || !alloc) return false;
    return alloc.lines.length > 0 && alloc.lines.every(l => parseFloat(l.remaining_quantity || '0') <= 0);
  });

  readonly form = new FormGroup({
    order_number: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    supplier_id: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    order_date: new FormControl<Date | null>(new Date(), { validators: [Validators.required] }),
    expected_delivery_date: new FormControl<Date | null>(null),
    currency: new FormControl<string>(this.session.homeCurrency() ?? 'USD', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^[A-Z]{3}$/)] }),
    order_tax: new FormControl<number>(0, { nonNullable: true, validators: [Validators.min(0)] }),
    lines: new FormArray<FormGroup<OrderLineForm>>([]),
  });

  get lines(): FormArray<FormGroup<OrderLineForm>> {
    return this.form.controls.lines;
  }

  get computedTotals() {
    return () => {
      let units = 0n;
      const lines = this.lines.getRawValue();
      for (const line of lines) {
        units += this.lineTotalUnits(line);
      }
      const linesTotal = Number(units) / 10000;
      return {
        linesTotal,
        orderTotal: linesTotal,
      };
    };
  }

  ngOnInit(): void {
    const sourceRequestId = this.route.snapshot.queryParamMap.get('source_request_id');
    const editId = this.route.snapshot.paramMap.get('id');
    
    if (editId) {
      this.editOrderId.set(editId);
    }

    forkJoin({
      suppliers: this.api.suppliers({ limit: 100 }).pipe(catchError(() => of({ items: [], next_cursor: null }))),
      products: this.api.products({ status: 'all', limit: 100 }).pipe(catchError(() => of({ items: [], next_cursor: null }))),
      branches: this.organisationApi.listBranches({ limit: 100 }).pipe(catchError(() => of({ items: [], next_cursor: null }))),
      request: sourceRequestId ? this.requestsApi.getRequest(sourceRequestId).pipe(catchError(() => of(null))) : of(null),
      allocations: sourceRequestId ? this.ordersApi.getAllocations(sourceRequestId).pipe(catchError(() => of(null))) : of(null),
      prefill: !editId && sourceRequestId && this.ordersApi.getRequestPrefill
        ? this.ordersApi.getRequestPrefill(sourceRequestId).pipe(catchError(() => of(null)))
        : of(null),
      nextNumber: !editId && this.ordersApi.getNextOrderNumber
        ? this.ordersApi.getNextOrderNumber().pipe(catchError(() => of(null)))
        : of(null),
      orderToEdit: editId ? this.ordersApi.getOrder(editId).pipe(catchError(() => of(null))) : of(null),
    }).subscribe(({ suppliers, products, branches, request, allocations, prefill, nextNumber, orderToEdit }) => {
      this.branches.set([...branches.items]);
      const supplierItems = [...suppliers.items];
      if (!orderToEdit && prefill?.supplier) {
        const prefillSupplier = prefill.supplier;
        if (!supplierItems.some(s => s.id === prefillSupplier.id)) {
          supplierItems.push({
            id: prefillSupplier.id,
            name: prefillSupplier.name,
            status: 'active',
            created_at: '',
          });
        }
      }
      this.suppliers.set(supplierItems);
      this.products.set(products.items);

      if (!orderToEdit) {
        if (nextNumber?.order_number && !this.form.controls.order_number.value) {
          this.form.controls.order_number.setValue(nextNumber.order_number);
        }
        if (prefill?.supplier?.id) {
          this.form.controls.supplier_id.setValue(prefill.supplier.id);
        }
      }
      
      if (orderToEdit) {
        const order = orderToEdit.order;
        this.form.patchValue({
          order_number: order.order_number,
          supplier_id: order.supplier_id,
          order_date: new Date(order.order_date),
          expected_delivery_date: order.expected_delivery_date ? new Date(order.expected_delivery_date) : null,
          currency: order.total.currency,
          order_tax: parseFloat(order.tax.amount),
        });
        
        this.lines.clear();
        order.lines.forEach((line) => {
          this.lines.push(
            new FormGroup<OrderLineForm>({
              workspace_product_id: new FormControl<string | null>(line.workspace_product_id),
              description: new FormControl<string>(line.description, { nonNullable: true, validators: [Validators.required] }),
              quantity: new FormControl<number | null>(parseFloat(line.ordered_quantity), { validators: [Validators.required, Validators.min(0.0001)] }),
              base_unit: new FormControl<string>(line.base_unit, { nonNullable: true, validators: [Validators.required] }),
              unit_price: new FormControl<number | null>(parseFloat(line.unit_price.amount), { validators: [Validators.required, Validators.min(0)] }),
              line_tax: new FormControl<number | null>(parseFloat(line.tax.amount), { validators: [Validators.min(0)] }),
              source_request_line_id: new FormControl<string | null>(line.source_request_line_id || null),
              remaining_quantity: new FormControl<number | null>(null),
              estimated_price: new FormControl<number | null>(null),
            })
          );
        });
        if (order.source_request_id) {
          forkJoin({
            request: this.requestsApi.getRequest(order.source_request_id).pipe(catchError(() => of(null))),
            allocations: this.ordersApi.getAllocations(order.source_request_id).pipe(catchError(() => of(null))),
          }).subscribe(({ request, allocations }) => {
            if (!request || !allocations) return;
            this.sourceRequest.set(request);
            this.requestAllocations.set(allocations);

            for (const lineGroup of this.lines.controls) {
              const lineId = lineGroup.controls.source_request_line_id.value;
              if (!lineId) continue;
              const requestLine = request.lines.find(line => line.id === lineId);
              const allocation = allocations.lines.find(line => line.source_request_line_id === lineId);
              const currentQuantity = lineGroup.controls.quantity.value || 0;
              const remaining = parseFloat(allocation?.remaining_quantity || '0') + currentQuantity;
              lineGroup.controls.remaining_quantity.setValue(remaining);
              lineGroup.controls.estimated_price.setValue(
                requestLine?.estimated_unit_price ? parseFloat(requestLine.estimated_unit_price.amount) : null,
              );
              lineGroup.controls.quantity.addValidators(Validators.max(remaining));
              lineGroup.controls.quantity.updateValueAndValidity({ emitEvent: false });
            }
          });
        }
      } else if (request && allocations) {
        this.sourceRequest.set(request);
        this.requestAllocations.set(allocations);
        if (request.required_by_date && !this.form.controls.expected_delivery_date.value) {
          this.form.controls.expected_delivery_date.setValue(parseIsoDateLocal(request.required_by_date));
        }
        this.lines.clear();

        // Pre-filled prices are in the quote's currency, so the order currency follows it. A
        // request whose quote lines mix currencies cannot be pre-filled into one order.
        // Only lines still to be ordered count: a fully allocated line is not on this PO.
        const remainingOf = (lineId: string) =>
          parseFloat(allocations.lines.find(a => a.source_request_line_id === lineId)?.remaining_quantity || '0');
        const quotedCurrencies = new Set(
          request.lines
            .filter(l => remainingOf(l.id) > 0)
            .map(l => l.quoted_unit_price?.currency)
            .filter((c): c is string => !!c),
        );
        const prefillQuotes = quotedCurrencies.size === 1;
        if (prefillQuotes) {
          const [currency] = quotedCurrencies;
          this.quotedCurrency.set(currency);
          this.form.controls.currency.setValue(currency);
        } else if (quotedCurrencies.size > 1) {
          this.errorMessage.set(this.translate.instant('orders.create.quotedMixedCurrencies'));
        }

        request.lines.forEach(reqLine => {
          const allocation = allocations.lines.find(a => a.source_request_line_id === reqLine.id);
          const remainingStr = allocation?.remaining_quantity || '0';
          const remaining = parseFloat(remainingStr);
          
          if (remaining > 0) {
            const inclusive = prefillQuotes && reqLine.quoted_prices_include_vat &&
              reqLine.quoted_unit_price && reqLine.quoted_net_unit_price && reqLine.quoted_vat_rate;
            const quotedPrice = inclusive ? reqLine.quoted_net_unit_price : reqLine.quoted_unit_price;
            const split = inclusive
              ? splitVatInclusiveLine(reqLine.quoted_unit_price!.amount, remainingStr, reqLine.quoted_vat_rate!)
              : null;
            if (prefillQuotes && reqLine.quoted_unit_price) {
              this.prefilledQuotes.set(reqLine.id, parseFloat(quotedPrice!.amount));
            }
            const lineGroup = new FormGroup<OrderLineForm>({
                workspace_product_id: new FormControl<string | null>(reqLine.workspace_product_id || null),
                description: new FormControl<string>(reqLine.product_name ?? this.requestLineDescription(products.items.find(p => p.id === reqLine.workspace_product_id)), { nonNullable: true, validators: [Validators.required] }),
                quantity: new FormControl<number | null>(remaining, { validators: [Validators.required, Validators.min(0.0001), Validators.max(remaining)] }),
                // Request quantities are in PACKS. Only the supplier's quoted per-pack price pre-fills
                // the PO; the (landed) estimate stays a reference. packHint uses the request snapshot.
                base_unit: new FormControl<string>(reqLine.base_unit ?? products.items.find(p => p.id === reqLine.workspace_product_id)?.base_unit ?? 'EA', { nonNullable: true, validators: [Validators.required] }),
                unit_price: new FormControl<number | null>(prefillQuotes && quotedPrice ? parseFloat(quotedPrice.amount) : null, { validators: [Validators.required, Validators.min(0)] }),
                line_tax: new FormControl<number | null>(split?.tax ?? 0, { validators: [Validators.min(0)] }),
                source_request_line_id: new FormControl<string | null>(reqLine.id),
                remaining_quantity: new FormControl<number | null>(remaining),
                estimated_price: new FormControl<number | null>(reqLine.estimated_unit_price ? parseFloat(reqLine.estimated_unit_price.amount) : null),
              });
            if (inclusive) {
              lineGroup.controls.quantity.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(quantity => {
                if (quantity !== null && lineGroup.controls.unit_price.value === this.prefilledQuotes.get(reqLine.id)) {
                  lineGroup.controls.line_tax.setValue(
                    splitVatInclusiveLine(reqLine.quoted_unit_price!.amount, quantity, reqLine.quoted_vat_rate!).tax,
                  );
                }
              });
            }
            this.lines.push(lineGroup);
          }
        });
      } else {
        this.addLine();
      }
    });
  }

  addLine(): void {
    this.lines.push(
      new FormGroup<OrderLineForm>({
        workspace_product_id: new FormControl<string | null>(null),
        description: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
        quantity: new FormControl<number | null>(1, { validators: [Validators.required, Validators.min(0.0001)] }),
        base_unit: new FormControl<string>('EA', { nonNullable: true, validators: [Validators.required] }),
        unit_price: new FormControl<number | null>(0, { validators: [Validators.required, Validators.min(0)] }),
        line_tax: new FormControl<number | null>(0, { validators: [Validators.min(0)] }),
        source_request_line_id: new FormControl<string | null>(null),
        remaining_quantity: new FormControl<number | null>(null),
        estimated_price: new FormControl<number | null>(null),
      })
    );
  }

  removeLine(index: number): void {
    this.lines.removeAt(index);
  }

  onProductSelected(index: number, productId: string | null): void {
    if (!productId) return;
    const product = this.products().find(p => p.id === productId);
    if (!product) return;

    const lineGroup = this.lines.at(index);
    lineGroup.patchValue({
      description: product.tenant_name,
      base_unit: product.base_unit,
    });
  }

  submit(): void {
    if (this.isSubmitting() || this.savedOrder() !== null || this.form.invalid || this.lines.length === 0) return;

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    const value = this.form.getRawValue();
    const currency = value.currency;

    const quoted = this.quotedCurrency();
    const quotedPriceStillInUse = value.lines.some(
      l => l.source_request_line_id != null
        && this.prefilledQuotes.get(l.source_request_line_id) === l.unit_price,
    );
    if (quoted && quotedPriceStillInUse && currency !== quoted) {
      this.errorMessage.set(
        this.translate.instant('orders.create.quotedCurrencyMismatch', { order: currency, quoted }),
      );
      this.isSubmitting.set(false);
      return;
    }

    const formatDate = (date: Date | null) => date ? toIsoDate(date) : null;

    let linesTotalAmount = 0n;
    const mappedLines = value.lines.map((line, i) => {
      const qty = line.quantity || 0;
      const price = line.unit_price || 0;
      const tax = line.line_tax || 0;
      const lineTotal = this.lineTotalUnits(line);
      linesTotalAmount += lineTotal;

      return {
        line_number: i + 1,
        workspace_product_id: line.workspace_product_id,
        description: line.description,
        ordered_quantity: qty.toFixed(6), // up to 6 decimal places as per api schema
        base_unit: line.base_unit,
        unit_price: { amount: formatMoneyUnits(moneyUnits(price)), currency },
        tax: { amount: formatMoneyUnits(moneyUnits(tax)), currency },
        line_total: { amount: formatMoneyUnits(lineTotal), currency },
        source_request_line_id: line.source_request_line_id,
      };
    });

    const orderTaxAmount = value.order_tax || 0;

    const payload: PurchaseOrderCreate = {
      order_number: value.order_number,
      supplier_id: value.supplier_id,
      order_date: formatDate(value.order_date)!,
      expected_delivery_date: formatDate(value.expected_delivery_date),
      total: { amount: formatMoneyUnits(linesTotalAmount), currency },
      tax: { amount: orderTaxAmount.toFixed(4), currency },
      source_kind: 'manual',
      source_reference: value.order_number,
      source_request_id: this.sourceRequest()?.id || undefined,
      lines: mappedLines,
    };

    const request$ = this.editOrderId() 
      ? this.ordersApi.editDraftOrder(this.editOrderId()!, payload) 
      : this.ordersApi.createOrder(payload);

    request$.subscribe({
      next: (order) => {
        this.savedOrder.set(order);
        this.snackBar.open(this.translate.instant('orders.create.success'), undefined, { duration: 3500 });
        const navPromise = this.router.navigate(['/orders', order.id]);
        Promise.resolve(navPromise).then(
          (navigated) => {
            if (!navigated) {
              this.navigationFailed.set(true);
            }
          },
          () => {
            this.navigationFailed.set(true);
          },
        );
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (err instanceof HttpErrorResponse && err.status === 409) {
          const details = err.error?.details as Record<string, unknown> | undefined;
          const reason = details?.['reason'];
          if (reason === 'order_number_exists') {
            this.errorMessage.set(this.translate.instant('orders.create.errors.orderNumberExists'));
            return;
          }
          if (reason === 'idempotency_key_exists') {
            this.errorMessage.set(this.translate.instant('orders.create.errors.idempotencyKeyExists'));
            return;
          }
          if (reason === 'quantity_exceeds_allocation') {
            this.errorMessage.set(this.translate.instant('orders.create.errors.quantityExceedsAllocation'));
            return;
          }
        }
        if (err instanceof HttpErrorResponse && err.error?.message) {
          this.errorMessage.set(err.error.message);
        } else {
          this.errorMessage.set(this.translate.instant('orders.saveError'));
        }
      },
    });
  }
}
