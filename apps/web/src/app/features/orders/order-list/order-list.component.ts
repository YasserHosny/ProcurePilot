import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RoleDirective } from '../../../core/auth/role.directive';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { RequestsApiService, type PurchaseRequest } from '../../requests/requests-api';
import { OrdersApiService, type OrderListQuery, type OrderStatus, type PurchaseOrder } from '../orders-api';

@Component({
  selector: 'app-order-list',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatMenuModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    RoleDirective,
  ],
  templateUrl: './order-list.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './order-list.component.scss',
})
export class OrderListComponent implements OnInit {
  private readonly ordersApi = inject(OrdersApiService);
  private readonly requestsApi = inject(RequestsApiService);
  private readonly formatService = inject(FormatService);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);

  readonly orders = signal<PurchaseOrder[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly isLoading = signal(true);
  readonly isLoadingMore = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly approvedRequests = signal<PurchaseRequest[]>([]);
  readonly isLoadingApprovedRequests = signal(false);
  readonly totalCount = signal<number | null>(null);
  readonly loadMoreError = signal(false);
  // Bumped on every fresh query so a slow answer to an earlier one is dropped.
  private generation = 0;

  readonly search = signal('');
  readonly statusFilter = signal('all');
  readonly sortKey = signal('created_at:desc');
  readonly statusOptions = ['all', 'draft', 'submitted', 'confirmed', 'partially_received', 'received', 'closed', 'cancelled'] as const;
  readonly sortOptions = [
    'created_at:desc', 'created_at:asc', 'order_date:desc', 'order_date:asc',
    'total:desc', 'total:asc', 'order_number:asc', 'order_number:desc',
  ] as const;

  /** True when any filter narrows the list, so an empty result means «no match», not «no orders». */
  readonly filtersActive = computed(() => this.search().trim() !== '' || this.statusFilter() !== 'all');

  private query(): OrderListQuery {
    const [sort, dir] = this.sortKey().split(':') as [string, 'asc' | 'desc'];
    return {
      q: this.search().trim() || undefined,
      status: this.statusFilter() === 'all' ? undefined : this.statusFilter(),
      sort: this.sortKey() === 'created_at:desc' ? undefined : sort,
      dir: this.sortKey() === 'created_at:desc' ? undefined : dir,
    };
  }

  onSearchInput(event: Event): void {
    this.search.set((event.target as HTMLInputElement).value);
  }

  onSearchSubmit(event: Event): void {
    event.preventDefault();
    this.loadOrders();
  }

  onStatusChange(event: Event): void {
    this.statusFilter.set((event.target as HTMLSelectElement).value);
    this.loadOrders();
  }

  onSortChange(event: Event): void {
    this.sortKey.set((event.target as HTMLSelectElement).value);
    this.loadOrders();
  }

  getSortLabel(key: string): string {
    return this.translate.instant(`orders.sort.${key.replace(':', '_')}`);
  }

  ngOnInit(): void {
    this.loadOrders();
  }

  loadOrders(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.loadMoreError.set(false);
    this.isLoadingMore.set(false);
    const generation = ++this.generation;
    this.ordersApi.listOrders(undefined, this.query()).subscribe({
      next: (response) => {
        if (generation !== this.generation) return;
        this.orders.set(response.items);
        this.nextCursor.set(response.next_cursor);
        this.totalCount.set(response.total_count ?? null);
        this.isLoading.set(false);
      },
      error: () => {
        if (generation !== this.generation) return;
        this.errorMessage.set(this.translate.instant('orders.loadError'));
        this.isLoading.set(false);
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) return;
    this.isLoadingMore.set(true);
    this.loadMoreError.set(false);
    const generation = this.generation;
    this.ordersApi.listOrders(cursor, this.query()).subscribe({
      next: (response) => {
        if (generation !== this.generation) return;
        // An order created between two page loads shifts the offset and repeats a row.
        const known = new Set(this.orders().map((order) => order.id));
        this.orders.set([...this.orders(), ...response.items.filter((order) => !known.has(order.id))]);
        this.nextCursor.set(response.next_cursor);
        this.totalCount.set(response.total_count ?? this.totalCount());
        this.isLoadingMore.set(false);
      },
      error: () => {
        if (generation !== this.generation) return;
        this.isLoadingMore.set(false);
        this.loadMoreError.set(true);
      },
    });
  }

  loadApprovedRequests(): void {
    this.isLoadingApprovedRequests.set(true);
    this.requestsApi.listRequests({ eligible_for_order: true, limit: 100 }).subscribe({
      next: (response) => {
        this.approvedRequests.set(
          response.items.filter(
            (request) =>
              request.approval_step?.status === 'approved' &&
              Boolean(request.approval_step.decided_by_membership_id) &&
              Boolean(request.approval_step.decided_at),
          ),
        );
        this.isLoadingApprovedRequests.set(false);
      },
      error: () => {
        this.approvedRequests.set([]);
        this.isLoadingApprovedRequests.set(false);
      },
    });
  }

  createFromApprovedRequest(request: PurchaseRequest): void {
    this.router.navigate(['/orders/new'], { queryParams: { source_request_id: request.id } });
  }

  formatRequiredBy(value: string | null | undefined): string {
    return this.formatService.formatDate(parseIsoDateLocal(value));
  }

  approvedRequestSupplier(request: PurchaseRequest): string {
    return request.source?.supplier_name ?? '';
  }

  formatApprovedRequestMoney(request: PurchaseRequest): string {
    return this.formatService.formatCurrencyAmount(request.estimated_total);
  }

  getStatusLabel(status: OrderStatus): string {
    return this.translate.instant(`orders.status.${status}`);
  }
}
