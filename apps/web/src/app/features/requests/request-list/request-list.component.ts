import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatOptionModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { TranslatePipe,
TranslateService } from '@ngx-translate/core';
import { RoleDirective } from '../../../core/auth/role.directive';
import { EMPTY, Subject, defer, forkJoin, of, type Observable, type Subscription } from 'rxjs';
import { catchError, expand, reduce, switchMap } from 'rxjs/operators';

import type { ApiError, Branch, BranchList, PurchaseRequest } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import { OrganisationApiService } from '../../settings/organisation-api';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { RequestsApiService, type PurchaseRequestStatus } from '../requests-api';

const I18N = 'requests';

@Component({
  selector: 'app-request-list',
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatOptionModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: './request-list.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './request-list.component.scss',
})
export class RequestListComponent implements OnInit {
  private readonly requestsApi = inject(RequestsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly formatService = inject(FormatService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly requests = signal<PurchaseRequest[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly statusFilter = signal<PurchaseRequestStatus | ''>('');

  private readonly reloadSubject = new Subject<{ status?: PurchaseRequestStatus }>();
  private loadMoreSub?: Subscription;

  constructor() {
    this.reloadSubject
      .pipe(
        switchMap(({ status }) => {
          this.isLoading.set(true);
          this.errorMessage.set(null);
          this.errorTraceId.set(null);

          return forkJoin({
            requests: this.requestsApi.listRequests({ status }),
            branches: this.loadBranches(),
          }).pipe(
            catchError((err: unknown) => {
              this.isLoading.set(false);
              this.requests.set([]);
              this.nextCursor.set(null);
              this.handleError(err);
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe(({ requests, branches }) => {
        this.requests.set([...requests.items]);
        this.branches.set([...branches.items]);
        this.nextCursor.set(requests.next_cursor);
        this.isLoading.set(false);
      });
  }

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const branch of this.branches()) {
      byId.set(branch.id, branch.name);
    }
    return byId;
  });

  readonly displayedColumns: readonly string[] = [
    'requiredByDate',
    'branch',
    'supplier',
    'status',
    'estimatedTotal',
    'actions',
  ];

  ngOnInit(): void {
    this.loadRequests();
  }

  loadRequests(): void {
    this.loadMoreSub?.unsubscribe();
    this.isLoadingMore.set(false);
    this.reloadSubject.next({
      status: this.statusFilter() || undefined,
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) {
      return;
    }

    this.isLoadingMore.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.loadMoreSub?.unsubscribe();
    this.loadMoreSub = this.requestsApi
      .listRequests({
        status: this.statusFilter() || undefined,
        cursor,
      })
      .subscribe({
        next: (res) => {
          const existingIds = new Set(this.requests().map((r) => r.id));
          const newItems = res.items.filter((r) => !existingIds.has(r.id));
          this.requests.set([...this.requests(), ...newItems]);
          this.nextCursor.set(res.next_cursor);
          this.isLoadingMore.set(false);
        },
        error: (err: unknown) => {
          this.isLoadingMore.set(false);
          this.handleError(err);
        },
      });
  }

  onStatusFilterChange(value: PurchaseRequestStatus | ''): void {
    this.statusFilter.set(value);
    this.requests.set([]);
    this.nextCursor.set(null);
    this.loadRequests();
  }

  clearFilter(): void {
    this.onStatusFilterChange('');
  }

  navigateToCreate(): void {
    this.router.navigate(['/requests/new']);
  }

  
  navigateToCreateOrder(request: PurchaseRequest): void {
    this.router.navigate(['/orders/new'], { queryParams: { source_request_id: request.id } });
  }

  formatRequiredBy(value: string | null | undefined): string {
    return this.formatService.formatDate(parseIsoDateLocal(value));
  }

  canCreateOrder(request: PurchaseRequest): boolean {
    return (
      request.approval_step?.status === 'approved' &&
      (request.status === 'approved' || request.status === 'ordered') &&
      request.has_quantity_to_order !== false
    );
  }

  navigateToDetail(request: PurchaseRequest): void {
    this.router.navigate(['/requests', request.id]);
  }

  onRowKey(event: Event, request: PurchaseRequest): void {
    if (event.target === event.currentTarget) {
      this.navigateToDetail(request);
    }
  }

  canWithdraw(request: PurchaseRequest): boolean {
    return request.status === 'draft' || request.status === 'submitted';
  }

  withdrawRequest(request: PurchaseRequest): void {
    const isGroup = !!request.request_group;
    const size = request.request_group?.size ?? 1;

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
      if (confirmed) this.performWithdrawal(request);
    });
  }

  private performWithdrawal(request: PurchaseRequest): void {
    const isGroup = !!request.request_group;
    const withdrawObs$: Observable<unknown> = isGroup
      ? this.requestsApi.withdrawGroup(request.request_group!.id, crypto.randomUUID())
      : this.requestsApi.withdrawRequest(request.id);

    withdrawObs$.subscribe({
      next: () => {
        this.loadRequests();
        this.snackBar.open(
          this.translate.instant(`${I18N}.withdrawSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          const details = apiError?.details as { reason?: string } | undefined;
          if (err.status === 409 && details?.reason === 'part_of_split') {
            this.snackBar.open(
              this.translate.instant(`${I18N}.partOfSplitError`),
              undefined,
              { duration: 4000 },
            );
            return;
          }
        }
        this.handleError(err);
      },
    });
  }

  formatMoney(request: PurchaseRequest): string {
    return this.formatService.formatCurrencyAmount(request.estimated_total);
  }

  getBranchName(branchId: string): string {
    return this.branchNameById().get(branchId) ?? branchId;
  }

  private loadBranches(): Observable<BranchList> {
    return defer(() => {
      const HARD_CAP = 50;
      let pageCount = 0;

      return this.organisationApi.listBranches({ limit: 100 }).pipe(
        expand((res) => {
          pageCount++;
          if (res.next_cursor && pageCount < HARD_CAP) {
            return this.organisationApi.listBranches({ limit: 100, cursor: res.next_cursor });
          }
          return EMPTY;
        }),
        reduce(
          (acc: BranchList, res: BranchList) => ({
            items: [...acc.items, ...res.items],
            next_cursor: res.next_cursor,
          }),
          { items: [], next_cursor: null } as BranchList,
        ),
        catchError(() =>
          of<BranchList>({
            items: [],
            next_cursor: null,
          }),
        ),
      );
    });
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      if (apiError?.details?.['reason'] === 'purchase_order_exists') {
        this.errorMessage.set(this.translate.instant(`${I18N}.purchaseOrderExists`));
        this.errorTraceId.set(apiError?.trace_id ?? null);
        return;
      }
      if (apiError?.details?.['reason'] === 'part_of_split') {
        this.errorMessage.set(this.translate.instant(`${I18N}.partOfSplitError`));
        this.errorTraceId.set(apiError?.trace_id ?? null);
        return;
      }
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
  }
}
