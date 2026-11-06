import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, OnInit, ViewChild, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatOptionModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe,
TranslateService } from '@ngx-translate/core';
import { RoleDirective } from '../../../core/auth/role.directive';
import { EMPTY, Subject, defer, forkJoin, of, type Observable, type Subscription } from 'rxjs';
import { catchError, debounceTime, distinctUntilChanged, expand, map, reduce, switchMap } from 'rxjs/operators';

import type { ApiError, Branch, BranchList, PurchaseRequest } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import { OrganisationApiService } from '../../settings/organisation-api';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { RequestsApiService, type PurchaseRequestSort, type PurchaseRequestStatus } from '../requests-api';

const I18N = 'requests';

@Component({
  selector: 'app-request-list',
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatOptionModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
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
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  @ViewChild('searchInput', { read: ElementRef }) searchInput?: ElementRef<HTMLInputElement>;

  readonly isLoading = signal<boolean>(true);
  readonly isLoadingMore = signal<boolean>(false);
  readonly requests = signal<PurchaseRequest[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly statusFilter = signal<PurchaseRequestStatus | ''>('');
  readonly searchQuery = signal<string>('');
  readonly sortOption = signal<PurchaseRequestSort>('created_desc');
  readonly mineFilter = signal<boolean>(false);

  readonly hasActiveFilters = computed<boolean>(() => {
    return !!this.statusFilter() || !!this.searchQuery().trim() || this.mineFilter();
  });

  readonly searchText = signal('');
  readonly sortOptions: PurchaseRequestSort[] = [
    'created_desc', 'created_asc', 'required_by_asc', 'required_by_desc', 'total_desc', 'total_asc',
  ];
  private readonly searchSubject = new Subject<string>();
  private readonly reloadSubject = new Subject<Parameters<RequestsApiService['listRequests']>[0]>();
  private loadMoreSub?: Subscription;

  constructor() {
    this.searchSubject.pipe(
      map((value) => value.trim().slice(0, 100)),
      debounceTime(300),
      distinctUntilChanged((previous, current) => previous === current && current === this.searchQuery()),
      takeUntilDestroyed(),
    ).subscribe((value) => {
      if (value === this.searchQuery()) return;
      this.searchQuery.set(value);
      this.filtersChanged();
    });
    this.reloadSubject
      .pipe(
        switchMap((params) => {
          this.isLoading.set(true);
          this.errorMessage.set(null);
          this.errorTraceId.set(null);

          return forkJoin({
            requests: this.requestsApi.listRequests(params),
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
    'created',
    'requester',
    'lines',
    'branch',
    'supplier',
    'status',
    'estimatedTotal',
    'actions',
  ];

  ngOnInit(): void {
    let initialized = false;
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const status = params.get('status') as PurchaseRequestStatus | null;
      const validStatus = ['draft', 'submitted', 'approved', 'ordered', 'delivered', 'rejected', 'withdrawn'];
      const nextStatus = status && validStatus.includes(status) ? status : '';
      const q = (params.get('q') ?? '').trim().slice(0, 100);
      const rawSort = params.get('sort') as PurchaseRequestSort;
      const sort = this.sortOptions.includes(rawSort) ? rawSort : 'created_desc';
      const mine = params.get('mine') === 'true';
      const changed = nextStatus !== this.statusFilter() || q !== this.searchQuery()
        || sort !== this.sortOption() || mine !== this.mineFilter();
      if (initialized && !changed) return;
      if (initialized) this.searchSubject.next(q);
      this.statusFilter.set(nextStatus);
      this.searchQuery.set(q);
      this.searchText.set(q);
      this.sortOption.set(sort);
      this.mineFilter.set(mine);
      if (changed || !initialized) this.resetAndReload();
      initialized = true;
    });
  }

  private listParams(): Parameters<RequestsApiService['listRequests']>[0] {
    return {
      status: this.statusFilter() || undefined,
      ...(this.searchQuery() ? { q: this.searchQuery() } : {}),
      ...(this.sortOption() !== 'created_desc' ? { sort: this.sortOption() } : {}),
      ...(this.mineFilter() ? { mine: true } : {}),
    };
  }

  loadRequests(): void {
    this.loadMoreSub?.unsubscribe();
    this.isLoadingMore.set(false);
    this.reloadSubject.next(this.listParams());
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
        ...this.listParams(),
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

  private resetAndReload(): void {
    this.requests.set([]);
    this.nextCursor.set(null);
    this.loadRequests();
  }

  private filtersChanged(): void {
    this.resetAndReload();
    void this.router.navigate([], {
      queryParams: {
        status: this.statusFilter() || null,
        q: this.searchQuery() || null,
        sort: this.sortOption() === 'created_desc' ? null : this.sortOption(),
        mine: this.mineFilter() ? true : null,
      },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  onStatusFilterChange(value: PurchaseRequestStatus | ''): void {
    this.statusFilter.set(value);
    this.filtersChanged();
  }

  onSearchInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.searchText.set(value);
    this.searchSubject.next(value);
  }

  clearSearch(): void {
    this.searchText.set('');
    this.searchSubject.next('');
    if (this.searchQuery()) {
      this.searchQuery.set('');
      this.filtersChanged();
    }
    this.searchInput?.nativeElement.focus();
  }

  onSortChange(value: PurchaseRequestSort): void {
    this.sortOption.set(value);
    this.filtersChanged();
  }

  onMineToggleChange(checked: boolean): void {
    this.mineFilter.set(checked);
    this.filtersChanged();
  }

  clearFilter(): void {
    this.statusFilter.set('');
    this.searchQuery.set('');
    this.searchText.set('');
    this.searchSubject.next('');
    this.mineFilter.set(false);
    this.filtersChanged();
  }

  navigateToCreate(): void {
    this.router.navigate(['/requests/new']);
  }

  
  navigateToCreateOrder(request: PurchaseRequest): void {
    this.router.navigate(['/orders/new'], { queryParams: { source_request_id: request.id } });
  }

  formatCreated(value: string): string {
    return this.formatService.formatDate(value);
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
    return ['draft', 'submitted', 'approved', 'ordered'].includes(request.status);
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
