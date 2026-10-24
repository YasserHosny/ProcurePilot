import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
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
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { RequestsApiService, type PurchaseRequest } from '../../requests/requests-api';
import { OrdersApiService, type OrderStatus, type PurchaseOrder } from '../orders-api';

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

  ngOnInit(): void {
    this.loadOrders();
  }

  loadOrders(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.ordersApi.listOrders().subscribe({
      next: (response) => {
        this.orders.set(response.items);
        this.nextCursor.set(response.next_cursor);
        this.isLoading.set(false);
      },
      error: () => {
        this.errorMessage.set(this.translate.instant('orders.loadError'));
        this.isLoading.set(false);
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) return;
    this.isLoadingMore.set(true);
    this.ordersApi.listOrders(cursor).subscribe({
      next: (response) => {
        this.orders.set([...this.orders(), ...response.items]);
        this.nextCursor.set(response.next_cursor);
        this.isLoadingMore.set(false);
      },
      error: () => {
        this.isLoadingMore.set(false);
        this.errorMessage.set(this.translate.instant('orders.loadError'));
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

  formatApprovedRequestMoney(request: PurchaseRequest): string {
    return this.formatService.formatCurrencyAmount(request.estimated_total);
  }

  getStatusLabel(status: OrderStatus): string {
    return this.translate.instant(`orders.status.${status}`);
  }
}
