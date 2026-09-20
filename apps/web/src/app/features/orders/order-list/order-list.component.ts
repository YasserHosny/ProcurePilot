import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { OrdersApiService, type OrderStatus, type PurchaseOrder } from '../orders-api';

@Component({
  selector: 'app-order-list',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './order-list.component.html',
  styleUrl: './order-list.component.scss',
})
export class OrderListComponent implements OnInit {
  private readonly ordersApi = inject(OrdersApiService);
  private readonly translate = inject(TranslateService);

  readonly orders = signal<PurchaseOrder[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly isLoading = signal(true);
  readonly isLoadingMore = signal(false);
  readonly errorMessage = signal<string | null>(null);

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

  getStatusLabel(status: OrderStatus): string {
    return this.translate.instant(`orders.status.${status}`);
  }
}
