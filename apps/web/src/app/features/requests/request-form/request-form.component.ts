import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { DateAdapter } from '@angular/material/core';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink, convertToParamMap } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { EMPTY, combineLatest, defer, forkJoin, of, Subscription, type Observable } from 'rxjs';
import { catchError, distinctUntilChanged, expand, finalize, reduce, switchMap, tap } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal, toIsoDateOrNull } from '../../../core/format/iso-date';
import { trimDecimal } from '../../../core/format/trim-decimal';
import type {
  ApiError,
  Branch,
  CostCentre,
  Member,
  Money,
  Product,
  PurchaseRequest,
  PurchaseRequestLine,
} from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import {
  OrdersApiService,
  type RequestAllocation,
  type RequestAllocationOrder,
} from '../../orders/orders-api';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { AppDateAdapter, provideAppDateAdapter } from '../../../core/i18n/date-adapter';

const I18N = 'requests';

const SERVER_ERROR_KEYS: Record<string, string> = {
  quantity_not_positive: 'requests.errors.quantity_not_positive',
  required_by_in_the_past: 'requests.errors.required_by_in_the_past',
  duplicate_product: 'requests.errors.duplicate_product',
  cost_centre_not_found: 'requests.errors.cost_centre_not_found',
  cost_centre_branch_mismatch: 'requests.errors.cost_centre_branch_mismatch',
  product_not_found: 'requests.errors.product_not_found',
  too_many_decimals: 'requests.errors.too_many_decimals',
};

interface LineFormGroup {
  workspace_product_id: FormControl<string>;
  quantity: FormControl<string>;
  note: FormControl<string>;
}

interface SavedLineInfo {
  id: string;
  workspace_product_id: string;
  quantity: string;
  estimated_unit_price: Money | null;
}

interface Paginated<T> {
  items: readonly T[];
  next_cursor: string | null;
}

export function fetchAllPages<T>(
  fetchPage: (cursor?: string) => Observable<Paginated<T>>,
  maxPages = 50,
): Observable<T[]> {
  return defer(() => {
    let pageCount = 0;
    return fetchPage().pipe(
      expand((res) => {
        pageCount++;
        if (res.next_cursor && pageCount < maxPages) {
          return fetchPage(res.next_cursor);
        }
        return EMPTY;
      }),
      reduce((acc: T[], res) => [...acc, ...res.items], [] as T[]),
    );
  });
}

@Component({
  providers: [provideAppDateAdapter()],
  selector: 'app-request-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    TranslatePipe,
    FormatDatePipe,
    RouterLink,
  ],
  templateUrl: './request-form.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './request-form.component.scss',
})
export class RequestFormComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly branchId = signal('');
  private readonly requestsApi = inject(RequestsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly formatService = inject(FormatService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly ordersApi = inject(OrdersApiService);
  private readonly elementRef = inject(ElementRef);
  private readonly dateAdapter = inject(DateAdapter);

  get dateFormat(): string {
    const adapter = this.dateAdapter as unknown as AppDateAdapter;
    const isDayFirst = adapter?.isDayFirst ? adapter.isDayFirst() : true;
    return isDayFirst ? 'DD/MM/YYYY' : 'MM/DD/YYYY';
  }

  readonly isLoading = signal<boolean>(false);
  readonly isSaving = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly allCostCentres = signal<CostCentre[]>([]);
  readonly costCentres = computed(() =>
    this.allCostCentres().filter(cc => !cc.branch_id || cc.branch_id === this.branchId()),
  );
  readonly members = signal<Member[]>([]);
  readonly products = signal<Product[]>([]);
  readonly existingRequest = signal<PurchaseRequest | null>(null);
  readonly isEditMode = signal<boolean>(false);

  readonly allocations = signal<RequestAllocation | null>(null);
  readonly isAllocationsLoading = signal<boolean>(false);
  readonly allocationsFailed = signal<boolean>(false);

  readonly allocatedOrders = computed<RequestAllocationOrder[]>(() => {
    return this.allocations()?.orders ?? [];
  });

  readonly isFullyOrdered = computed<boolean>(() => {
    const req = this.existingRequest();
    if (!req || req.approval_step?.status !== 'approved' || (req.status !== 'approved' && req.status !== 'ordered')) {
      return false;
    }
    if (this.isAllocationsLoading() || this.allocationsFailed()) {
      return false;
    }
    const alloc = this.allocations();
    if (!alloc) {
      return false;
    }
    return alloc.lines.length > 0 && alloc.lines.every(l => parseFloat(l.remaining_quantity || '0') <= 0);
  });

  private submitIdempotencyKey: string | null = null;
  private createSubmitIdempotencyKey: string | null = null;
  private createSubmitSubmitKey: string | null = null;
  private withdrawIdempotencyKey: string | null = null;
  private currentRequestId: string | null | undefined = undefined;
  private allocationsSub?: Subscription;

  readonly formChangeSignal = signal<number>(0);
  private readonly savedLineMeta = new Map<FormGroup<LineFormGroup>, SavedLineInfo>();

  readonly isEstimateStale = computed<boolean>(() => {
    this.formChangeSignal();
    const req = this.existingRequest();
    if (!req || !req.estimated_total) {
      return false;
    }
    if (!this.form.dirty) {
      return false;
    }
    const currentLines = this.lines.controls;
    const savedLines = req.lines;
    if (currentLines.length !== savedLines.length) {
      return true;
    }
    for (const group of currentLines) {
      const meta = this.savedLineMeta.get(group);
      if (!meta) {
        return true;
      }
      if (group.controls.workspace_product_id.value !== meta.workspace_product_id) {
        return true;
      }
      const currentQty = parseFloat(String(group.controls.quantity.value ?? ''));
      const savedQty = parseFloat(String(meta.quantity));
      if (isNaN(currentQty) || isNaN(savedQty) || currentQty !== savedQty) {
        return true;
      }
    }
    return false;
  });

  readonly duplicateSourceStatus = signal<PurchaseRequest['status'] | null>(null);
  private currentDuplicateFrom: string | null = null;

  private resetState(): void {
    this.allocationsSub?.unsubscribe();
    this.allocationsSub = undefined;
    this.existingRequest.set(null);
    this.duplicateSourceStatus.set(null);
    this.form.reset({ branch_id: '', cost_centre_id: '', required_by_date: null });
    this.form.enable();
    this.lines.clear();
    this.savedLineMeta.clear();
    this.allocations.set(null);
    this.isAllocationsLoading.set(false);
    this.allocationsFailed.set(false);
    this.errorMessage.set(null);
    this.submitIdempotencyKey = null;
    this.createSubmitIdempotencyKey = null;
    this.createSubmitSubmitKey = null;
    this.withdrawIdempotencyKey = null;
    this.formChangeSignal.update((v) => v + 1);
  }

  readonly isReadOnly = computed<boolean>(() => {
    const req = this.existingRequest();
    return req !== null && (req.status !== 'draft' || !!req.request_group);
  });

  readonly canCreateOrder = computed<boolean>(() => {
    const req = this.existingRequest();
    if (!req || req.approval_step?.status !== 'approved' || (req.status !== 'approved' && req.status !== 'ordered')) {
      return false;
    }
    if (this.isAllocationsLoading()) {
      return false;
    }
    if (this.allocationsFailed()) {
      return true;
    }
    const alloc = this.allocations();
    if (!alloc) {
      return false;
    }
    return alloc.lines.some(l => parseFloat(l.remaining_quantity || '0') > 0);
  });

  readonly canWithdraw = computed<boolean>(() => {
    const req = this.existingRequest();
    return req !== null && (req.status === 'draft' || req.status === 'submitted');
  });

  getGroupSubmitLabel(size: number): string {
    if (this.isSubmitting()) {
      return this.translate.instant(`${I18N}.form.submittingButton`);
    }
    if (size === 2) {
      return this.translate.instant(`${I18N}.split.submitBoth`);
    }
    return this.translate.instant(`${I18N}.split.submitAll`, { count: size });
  }

  getGroupWithdrawLabel(size: number): string {
    if (size === 2) {
      return this.translate.instant(`${I18N}.split.withdrawBoth`);
    }
    return this.translate.instant(`${I18N}.split.withdrawAll`, { count: size });
  }

  readonly memberEmailById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const member of this.members()) {
      byId.set(member.id, member.email);
    }
    return byId;
  });

  readonly productNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const product of this.products()) {
      byId.set(product.id, product.tenant_name);
    }
    return byId;
  });

  readonly form = new FormGroup({
    branch_id: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    cost_centre_id: new FormControl<string>('', { nonNullable: true }),
    required_by_date: new FormControl<Date | string | null>(null, [Validators.required]),
    lines: new FormArray<FormGroup<LineFormGroup>>([]),
  });

  get lines(): FormArray<FormGroup<LineFormGroup>> {
    return this.form.controls.lines;
  }

  ngOnInit(): void {
    this.isLoading.set(true);
    this.branchId.set(this.form.controls.branch_id.value);
    this.form.controls.branch_id.valueChanges
      .pipe(distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((branchId) => {
        this.branchId.set(branchId);
        const selected = this.form.controls.cost_centre_id.value;
        if (selected && !this.costCentres().some(cc => cc.id === selected)) {
          this.form.controls.cost_centre_id.setValue('');
        }
      });

    this.form.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.clearServerErrors();
        this.formChangeSignal.update((v) => v + 1);
      });

    let refDataLoaded = false;
    const refData$ = forkJoin({
      branches: this.loadBranches(),
      costCentres: this.loadCostCentres(),
      products: this.loadProducts(),
    }).pipe(
      tap(() => {
        refDataLoaded = true;
      }),
    );

    const paramMap$ = (this.route.paramMap ?? of(this.route.snapshot?.paramMap ?? convertToParamMap({}))).pipe(
      takeUntilDestroyed(this.destroyRef),
    );

    const queryParamMap$ = this.route.queryParamMap ?? of(this.route.snapshot?.queryParamMap ?? convertToParamMap({}));

    combineLatest([paramMap$, queryParamMap$])
      .pipe(
        switchMap(([params, queryParams]) => {
          const requestId = params.get('id');
          const duplicateFrom = requestId ? null : queryParams.get('duplicate_from');
          if (this.currentRequestId !== undefined && this.currentRequestId === requestId
            && this.currentDuplicateFrom === duplicateFrom) {
            return of(null);
          }
          this.currentRequestId = requestId;
          this.currentDuplicateFrom = duplicateFrom;
          this.resetState();
          this.isLoading.set(true);

          const isEditMode = requestId !== null;
          this.isEditMode.set(isEditMode);
          if (isEditMode) {
            this.loadMembers();
          }

          const req$: Observable<unknown> = requestId ? this.loadRequest(requestId)
            : duplicateFrom ? this.loadDuplicate(duplicateFrom) : of(null);
          const load$: Observable<unknown> = refDataLoaded ? req$ : refData$.pipe(switchMap(() => req$));

          return load$.pipe(
            catchError((err: unknown) => {
              this.handleError(err);
              return of(null);
            }),
            finalize(() => {
              this.isLoading.set(false);
              if (!this.isEditMode() && this.lines.length === 0) {
                this.addLine();
              }
            }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  addLine(): void {
    this.clearServerErrors();
    this.lines.push(
      new FormGroup<LineFormGroup>({
        workspace_product_id: new FormControl<string>('', {
          nonNullable: true,
          validators: [Validators.required],
        }),
        quantity: new FormControl<string>('', {
          nonNullable: true,
          validators: [Validators.required, Validators.pattern(/^(?!0(?:\.0+)?$)\d+(?:\.\d{1,6})?$/)],
        }),
        note: new FormControl<string>('', { nonNullable: true }),
      }),
    );
    this.formChangeSignal.update((v) => v + 1);
  }

  removeLine(index: number): void {
    const group = this.lines.at(index);
    this.lines.removeAt(index);
    if (group) {
      this.savedLineMeta.delete(group);
    }
    this.clearServerErrors();
    this.form.markAsDirty();
    this.formChangeSignal.update((v) => v + 1);
  }

  getPackHint(group: FormGroup<LineFormGroup>): { size: string; unit: string; total: string | null } | null {
    const product = this.products().find(p => p.id === group.controls.workspace_product_id.value);
    if (!product?.pack) {
      return null;
    }
    const size = Number(product.pack.base_quantity ?? Number(product.pack.unit_size) * product.pack.pack_count);
    if (!Number.isFinite(size) || size <= 0) {
      return null;
    }
    // Disabled controls may contain localized display values; calculate from the saved decimal instead.
    const rawQuantity = group.disabled
      ? this.savedLineMeta.get(group)?.quantity ?? group.controls.quantity.value
      : group.controls.quantity.value;
    const quantity = Number(rawQuantity);
    const total = quantity * size;
    const showTotal = (group.disabled || group.controls.quantity.valid)
      && Number.isFinite(quantity) && quantity > 0 && Number.isFinite(total);
    return {
      size: this.formatQuantity(trimDecimal(String(size))),
      unit: product.base_unit,
      total: showTotal ? this.formatQuantity(trimDecimal(String(total))) : null,
    };
  }

  saveAndSubmit(): void {
    if (this.isSaving() || this.isSubmitting() || this.isReadOnly()) {
      return;
    }
    // Only a draft created by this action can be retried here; existing drafts keep their Submit flow.
    if (this.isEditMode() && !this.createSubmitIdempotencyKey) {
      return;
    }
    if (this.form.invalid || this.lines.length === 0) {
      this.form.markAllAsTouched();
      this.errorMessage.set(this.getValidationErrorMessage());
      this.focusErrorBanner();
      return;
    }

    this.createSubmitIdempotencyKey ??= crypto.randomUUID();
    this.createSubmitSubmitKey ??= crypto.randomUUID();
    this.isSaving.set(true);
    this.errorMessage.set(null);
    let created = this.existingRequest();
    const draft$ = created ? of(created)
      : this.requestsApi.createRequest(this.buildRequestPayload(), this.createSubmitIdempotencyKey);
    draft$.pipe(
      switchMap(draft => {
        created = draft;
        this.isSubmitting.set(true);
        return this.requestsApi.submitRequest(draft.id, this.createSubmitSubmitKey!);
      }),
      finalize(() => {
        this.isSaving.set(false);
        this.isSubmitting.set(false);
      }),
    ).subscribe({
      next: submitted => {
        this.adoptSavedRequest(submitted);
        this.form.disable();
        this.snackBar.open(this.translate.instant(`${I18N}.submitSuccess`), undefined, { duration: 3500 });
        this.router.navigate(['/requests', submitted.id]);
      },
      error: (err: unknown) => {
        if (created) {
          this.adoptSavedRequest(created);
          this.snackBar.open(this.translate.instant(`${I18N}.form.draftSavedSubmitFailed`), undefined, { duration: 3500 });
          this.router.navigate(['/requests', created.id]);
        } else {
          this.handleError(err);
        }
      },
    });
  }

  saveDraft(): void {
    if (this.isSaving() || this.isSubmitting()) {
      return;
    }
    const existing = this.existingRequest();
    if (existing?.request_group) {
      return;
    }

    if (this.form.invalid || this.lines.length === 0) {
      this.form.markAllAsTouched();
      this.errorMessage.set(this.getValidationErrorMessage());
      this.focusErrorBanner();
      return;
    }

    this.isSaving.set(true);
    this.errorMessage.set(null);

    const body = this.buildRequestPayload();

    const obs = existing
      ? this.requestsApi.updateRequest(existing.id, body)
      : this.requestsApi.createRequest(body);

    obs.subscribe({
      next: (saved) => {
        this.isSaving.set(false);
        this.adoptSavedRequest(saved);
        this.snackBar.open(this.translate.instant(`${I18N}.createSuccess`), undefined, {
          duration: 3500,
        });
        this.router.navigate(['/requests', saved.id]);
      },
      error: (err: unknown) => {
        this.isSaving.set(false);
        this.handleError(err);
      },
    });
  }

  private adoptSavedRequest(saved: PurchaseRequest): void {
    this.existingRequest.set(saved);
    this.isEditMode.set(true);
    this.form.markAsPristine();
    this.currentRequestId = saved.id;
    this.currentDuplicateFrom = null;
    this.duplicateSourceStatus.set(null);
    this.savedLineMeta.clear();
    for (let i = 0; i < this.lines.length; i++) {
      const group = this.lines.at(i);
      const savedLine = saved.lines[i];
      if (group && savedLine) {
        this.savedLineMeta.set(group, {
          id: savedLine.id,
          workspace_product_id: savedLine.workspace_product_id,
          quantity: savedLine.quantity,
          estimated_unit_price: savedLine.estimated_unit_price ?? null,
        });
      }
    }
    this.formChangeSignal.update((v) => v + 1);
  }

  submitRequest(): void {
    const existing = this.existingRequest();
    if (!existing) {
      return;
    }

    if (!existing.request_group && (this.form.invalid || this.lines.length === 0)) {
      this.form.markAllAsTouched();
      this.errorMessage.set(this.getValidationErrorMessage());
      this.focusErrorBanner();
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    if (!this.submitIdempotencyKey) {
      this.submitIdempotencyKey = crypto.randomUUID();
    }
    const key = this.submitIdempotencyKey;

    const isSplit = Boolean(existing.request_group);
    const splitCount = existing.request_group?.size;

    const submitObs$: Observable<unknown> = isSplit
      ? this.requestsApi.submitGroup(existing.request_group!.id, key)
      : this.requestsApi.updateRequest(existing.id, this.buildRequestPayload()).pipe(
          tap((saved) => {
            this.existingRequest.set(saved);
            this.form.markAsPristine();
          }),
          switchMap((saved) => this.requestsApi.submitRequest(saved.id)),
        );

    submitObs$.subscribe({
      next: (res) => {
        this.submitIdempotencyKey = null;
        this.isSubmitting.set(false);
        if (isSplit) {
          const count = splitCount || (Array.isArray(res) && res.length ? res.length : 1);
          this.snackBar.open(
            this.translate.instant('basketSplit.submit.successSplit', { count }),
            undefined,
            { duration: 3500 },
          );
        } else {
          this.snackBar.open(this.translate.instant(`${I18N}.submitSuccess`), undefined, {
            duration: 3500,
          });
        }
        this.router.navigate(['/requests']);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleError(err);
      },
    });
  }

  withdrawRequest(): void {
    const req = this.existingRequest();
    if (!req) {
      return;
    }
    const isGroup = !!req.request_group;
    const size = req.request_group?.size ?? 1;

    const titleKey = isGroup ? `${I18N}.split.withdrawConfirmTitle` : `${I18N}.withdrawConfirmTitle`;
    const messageKey = isGroup
      ? size === 2
        ? `${I18N}.split.withdrawConfirmMessageBoth`
        : `${I18N}.split.withdrawConfirmMessageAll`
      : `${I18N}.withdrawConfirmMessage`;
    const confirmKey = isGroup
      ? size === 2
        ? `${I18N}.split.withdrawBoth`
        : `${I18N}.split.withdrawAll`
      : `${I18N}.actions.withdraw`;

    this.dialog.open(CatalogueConfirmDialogComponent, {
      data: {
        titleKey,
        messageKey,
        messageParams: isGroup ? { count: size } : undefined,
        confirmKey,
        confirmParams: isGroup ? { count: size } : undefined,
        isDestructive: true,
      },
    }).afterClosed().subscribe((confirmed: boolean) => {
      if (confirmed) {
        this.performWithdrawal(req);
      }
    });
  }

  discardDraft(): void {
    const req = this.existingRequest();
    if (!req || req.status !== 'draft' || req.request_group) {
      return;
    }
    this.dialog.open(CatalogueConfirmDialogComponent, {
      data: {
        titleKey: 'requests.discard.title',
        messageKey: 'requests.discard.message',
        confirmKey: 'requests.discard.confirm',
        isDestructive: true,
      },
    }).afterClosed().subscribe((confirmed: boolean) => {
      if (confirmed) {
        this.performWithdrawal(req, 'requests.discard.success');
      }
    });
  }

  duplicateRequest(): void {
    const req = this.existingRequest();
    if (req?.status === 'withdrawn' || req?.status === 'rejected') {
      this.router.navigate(['/requests/new'], { queryParams: { duplicate_from: req.id } });
    }
  }

  private performWithdrawal(req: PurchaseRequest, successKey = `${I18N}.withdrawSuccess`): void {
    const isGroup = !!req.request_group;

    if (!this.withdrawIdempotencyKey) {
      this.withdrawIdempotencyKey = crypto.randomUUID();
    }
    const key = this.withdrawIdempotencyKey;

    const withdrawObs$: Observable<unknown> = isGroup
      ? this.requestsApi.withdrawGroup(req.request_group!.id, key)
      : this.requestsApi.withdrawRequest(req.id, key);

    withdrawObs$.subscribe({
      next: () => {
        this.withdrawIdempotencyKey = null;
        this.snackBar.open(this.translate.instant(successKey), undefined, {
          duration: 3500,
        });
        this.router.navigate(['/requests']);
      },
      error: (err: unknown) => this.handleError(err),
    });
  }

  navigateToCreateOrder(): void {
    const req = this.existingRequest();
    if (!req || req.approval_step?.status !== 'approved') {
      return;
    }
    this.router.navigate(['/orders/new'], { queryParams: { source_request_id: req.id } });
  }

  cancel(): void {
    this.router.navigate(['/requests']);
  }

  formatMoney(value: Money | null | undefined): string {
    return this.formatService.formatCurrencyAmount(value);
  }

  formatQuantity(value: number | string | null | undefined): string {
    return this.formatService.formatQuantity(value);
  }

  formatEstimate(line: PurchaseRequestLine): string {
    if (!line.estimated_unit_price) {
      return this.translate.instant(`${I18N}.form.noEstimateAvailable`);
    }
    const price = this.formatService.formatCurrencyAmount(line.estimated_unit_price);
    return this.translate.instant(`${I18N}.form.perPack`, { price });
  }

  getLineEstimate(group: FormGroup<LineFormGroup>): string | null {
    const meta = this.savedLineMeta.get(group);
    if (!meta) {
      return null;
    }
    if (group.controls.workspace_product_id.value !== meta.workspace_product_id) {
      return null;
    }
    if (!meta.estimated_unit_price) {
      return this.translate.instant(`${I18N}.form.noEstimateAvailable`);
    }
    return this.formatEstimate({
      id: meta.id,
      workspace_product_id: meta.workspace_product_id,
      quantity: meta.quantity,
      estimated_unit_price: meta.estimated_unit_price,
    } as PurchaseRequestLine);
  }

  hasProductName(productId: string): boolean {
    return this.productNameById().has(productId);
  }

  getRemoveLineAriaLabel(index: number, lineGroup: FormGroup<LineFormGroup>): string {
    const prodId = lineGroup.controls.workspace_product_id.value;
    const product = (prodId ? this.productNameById().get(prodId) : null) || prodId;
    if (product) {
      return this.translate.instant(`${I18N}.form.removeLineWithProduct`, {
        position: index + 1,
        product,
      });
    }
    return this.translate.instant(`${I18N}.form.removeLineButton`);
  }

  private getValidationErrorMessage(): string {
    if (this.form.controls.branch_id.invalid) {
      return this.translate.instant(`${I18N}.form.branchRequired`);
    }
    if (this.form.controls.required_by_date.invalid) {
      return this.translate.instant(`${I18N}.form.requiredByDateRequired`);
    }
    if (this.lines.length === 0) {
      return this.translate.instant(`${I18N}.form.atLeastOneLineRequired`);
    }
    for (const group of this.lines.controls) {
      if (group.controls.workspace_product_id.invalid) {
        return this.translate.instant(`${I18N}.form.productRequired`);
      }
      if (group.controls.quantity.invalid) {
        return this.translate.instant(`${I18N}.form.quantityRequired`);
      }
    }
    return this.translate.instant(`${I18N}.genericError`);
  }

  private buildRequestPayload() {
    const value = this.form.getRawValue();
    return {
      branch_id: value.branch_id,
      cost_centre_id: value.cost_centre_id || null,
      required_by_date: toIsoDateOrNull(value.required_by_date) ?? '',
      lines: value.lines.map((l) => ({
        workspace_product_id: l.workspace_product_id,
        // The API contract carries quantity as a decimal string (monetary-rule style), while
        // the number input's value accessor stores a JS number — serialise at the boundary.
        quantity: String(l.quantity),
        note: l.note || null,
      })),
    };
  }

  private loadBranches(): Observable<Branch[]> {
    return fetchAllPages<Branch>((cursor) =>
      this.organisationApi.listBranches({ is_active: true, ...(cursor ? { cursor } : {}) }),
    ).pipe(tap((items) => this.branches.set(items)));
  }

  private loadCostCentres(): Observable<CostCentre[]> {
    return fetchAllPages<CostCentre>((cursor) =>
      this.organisationApi.listCostCentres({ is_archived: false, ...(cursor ? { cursor } : {}) }),
    ).pipe(tap((items) => this.allCostCentres.set(items)));
  }

  private loadMembers(): void {
    this.api
      .members()
      .pipe(
        catchError(() =>
          of<{ items: Member[]; next_cursor: string | null }>({
            items: [],
            next_cursor: null,
          }),
        ),
      )
      .subscribe((res) => this.members.set([...res.items]));
  }

  private loadProducts(): Observable<Product[]> {
    return fetchAllPages<Product>((cursor) =>
      this.api.products({ status: 'all', limit: 100, ...(cursor ? { cursor } : {}) }),
    ).pipe(
      catchError(() => of<Product[]>([])),
      tap((items) => this.products.set(items)),
    );
  }

  private loadDuplicate(requestId: string): Observable<PurchaseRequest | null> {
    return this.requestsApi.getRequest(requestId).pipe(
      tap((req) => {
        this.form.controls.branch_id.setValue(req.branch_id);
        this.form.controls.cost_centre_id.setValue(
          this.costCentres().some(cc => cc.id === req.cost_centre_id) ? req.cost_centre_id! : '',
        );
        for (const line of req.lines) {
          this.addLine();
          this.lines.at(this.lines.length - 1).patchValue({
            workspace_product_id: line.workspace_product_id,
            quantity: trimDecimal(line.quantity),
            note: line.note ?? '',
          });
        }
        this.duplicateSourceStatus.set(req.status);
      }),
      catchError(() => {
        this.resetState();
        this.errorMessage.set(this.translate.instant('requests.genericError'));
        this.focusErrorBanner();
        return of(null);
      }),
    );
  }

  private loadRequest(requestId: string): Observable<PurchaseRequest> {
    return this.requestsApi.getRequest(requestId).pipe(
      tap((req) => {
        this.existingRequest.set(req);
        this.form.patchValue({
          branch_id: req.branch_id,
          cost_centre_id: req.cost_centre_id ?? '',
          required_by_date: parseIsoDateLocal(req.required_by_date),
        });

        const isReadOnly = req.status !== 'draft' || !!req.request_group;
        this.lines.clear();
        this.savedLineMeta.clear();
        for (const line of req.lines) {
          const displayQty = isReadOnly ? this.formatQuantity(line.quantity) : trimDecimal(line.quantity);
          const group = new FormGroup<LineFormGroup>({
            workspace_product_id: new FormControl<string>(line.workspace_product_id, {
              nonNullable: true,
              validators: [Validators.required],
            }),
            quantity: new FormControl<string>(displayQty, {
              nonNullable: true,
              validators: [Validators.required, Validators.pattern(/^(?!0(?:\.0+)?$)\d+(?:\.\d{1,6})?$/)],
            }),
            note: new FormControl<string>(line.note ?? '', { nonNullable: true }),
          });
          this.savedLineMeta.set(group, {
            id: line.id,
            workspace_product_id: line.workspace_product_id,
            quantity: line.quantity,
            estimated_unit_price: line.estimated_unit_price ?? null,
          });
          this.lines.push(group);
        }
        this.formChangeSignal.update((v) => v + 1);

        if (isReadOnly) {
          this.form.disable();
        }

        if (
          req.approval_step?.status === 'approved' &&
          (req.status === 'approved' || req.status === 'ordered')
        ) {
          this.loadAllocations(req.id);
        }
      }),
    );
  }

  private loadAllocations(requestId: string): void {
    this.allocationsSub?.unsubscribe();
    this.isAllocationsLoading.set(true);
    this.allocationsFailed.set(false);
    this.allocationsSub = this.ordersApi
      .getAllocations(requestId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (alloc) => {
          if (this.existingRequest()?.id !== requestId) {
            return;
          }
          this.allocations.set(alloc);
          this.isAllocationsLoading.set(false);
        },
        error: () => {
          if (this.existingRequest()?.id !== requestId) {
            return;
          }
          this.allocationsFailed.set(true);
          this.isAllocationsLoading.set(false);
        },
      });
  }

  private clearServerErrors(): void {
    let hadServerErrors = false;
    const clearControl = (control: FormControl | null | undefined) => {
      if (control?.errors && 'server' in control.errors) {
        hadServerErrors = true;
        const rest = { ...control.errors };
        delete rest['server'];
        control.setErrors(Object.keys(rest).length > 0 ? rest : null);
        control.updateValueAndValidity({ emitEvent: false });
      }
    };

    clearControl(this.form.controls.branch_id);
    clearControl(this.form.controls.cost_centre_id);
    clearControl(this.form.controls.required_by_date);
    for (const lineGroup of this.lines.controls) {
      clearControl(lineGroup.controls.workspace_product_id);
      clearControl(lineGroup.controls.quantity);
      clearControl(lineGroup.controls.note);
    }
    if (hadServerErrors) {
      this.form.updateValueAndValidity({ emitEvent: false });
    }
  }

  private focusErrorBanner(): void {
    setTimeout(() => {
      const banner = this.elementRef.nativeElement.querySelector('.error-banner') as HTMLElement | null;
      if (banner) {
        if (typeof banner.scrollIntoView === 'function') {
          banner.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        banner.focus();
      }
    }, 0);
  }

  private getControlByPath(path?: string): FormControl | null {
    if (!path) {
      return null;
    }
    const match = path.match(/^lines\[(\d+)\]\.(.+)$/);
    if (match) {
      const index = parseInt(match[1], 10);
      const subProp = match[2];
      const group = this.lines.at(index);
      return (group?.get(subProp) as FormControl) ?? null;
    }
    return (this.form.get(path) as FormControl) ?? null;
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      const rawDetails = apiError?.details;
      interface DetailEntry {
        field?: string;
        reason?: string;
        type?: string;
        msg?: string;
        loc?: (string | number)[];
      }

      let details: DetailEntry | undefined;
      if (Array.isArray(rawDetails)) {
        details = (rawDetails.find((d: DetailEntry) => Boolean(d?.field)) ?? rawDetails[0]) as DetailEntry | undefined;
      } else if (rawDetails && typeof rawDetails === 'object') {
        details = rawDetails as DetailEntry;
      }

      if (err.status === 409 && details?.reason === 'part_of_split') {
        this.errorMessage.set(this.translate.instant(`${I18N}.partOfSplitError`));
        this.focusErrorBanner();
        return;
      }

      let reason = details?.reason ?? details?.type;
      const isQuantityField = typeof details?.field === 'string' && /^lines\[\d+\]\.quantity$/.test(details.field);
      if (isQuantityField && reason === 'string_pattern_mismatch') {
        reason = 'too_many_decimals';
      }

      if (reason && SERVER_ERROR_KEYS[reason]) {
        const key = SERVER_ERROR_KEYS[reason];
        if (details?.field) {
          const control = this.getControlByPath(details.field);
          if (control) {
            control.setErrors({ server: key });
            control.markAsTouched();
          }
        }
        if (isQuantityField) {
          this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
        } else {
          this.errorMessage.set(this.translate.instant(key));
        }
        this.focusErrorBanner();
        return;
      }

      this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
      this.focusErrorBanner();
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
    this.focusErrorBanner();
  }
}
