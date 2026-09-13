import { DecimalPipe, NgClass, NgFor, NgIf } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type { Product, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { navigateAlertAction } from '../alert-actions';
import type { Alert, AlertKind } from '../alerts-api';

@Component({
  selector: 'app-alerts-inbox',
  standalone: true,
  imports: [
    FormsModule,
    NgIf,
    NgFor,
    NgClass,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    DecimalPipe,
  ],
  templateUrl: './alerts-inbox.component.html',
  styleUrl: './alerts-inbox.component.scss',
})
export class AlertsInboxComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(false);
  readonly alerts = signal<Alert[]>([]);
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);
  readonly selectedKind = signal<AlertKind | ''>('');
  readonly dismissingAlertIds = signal<Set<string>>(new Set());

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly filteredAlerts = computed<readonly Alert[]>(() => {
    const list = this.alerts();
    const kind = this.selectedKind();
    if (!kind) return list;
    return list.filter((a) => a.kind === kind);
  });

  ngOnInit(): void {
    this.loadDropdownData();
    this.fetchAlerts();
  }

  loadDropdownData(): void {
    this.api.products({ limit: 100, status: 'active' }).subscribe({
      next: (res) => this.products.set(res.items),
      error: () => {
        // Fallback silently if product dropdown load fails
      },
    });
    this.api.suppliers({ limit: 100, status: 'active' }).subscribe({
      next: (res) => this.suppliers.set(res.items),
      error: () => {
        // Fallback silently if supplier dropdown load fails
      },
    });
  }

  fetchAlerts(): void {
    this.isLoading.set(true);
    this.api
      .getAlerts({
        kind: (this.selectedKind() as AlertKind) || undefined,
      })
      .subscribe({
        next: (res) => {
          this.alerts.set(res.items);
          this.isLoading.set(false);
        },
        error: () => {
          this.isLoading.set(false);
        },
      });
  }

  onKindFilterChange(kind: AlertKind | ''): void {
    this.selectedKind.set(kind);
    this.fetchAlerts();
  }

  dismissAlert(alert: Alert): void {
    if (!this.isWriter()) return;

    this.dismissingAlertIds.update((s) => new Set(s).add(alert.id));

    this.api.dismissAlert(alert.id).subscribe({
      next: () => {
        this.dismissingAlertIds.update((s) => {
          const next = new Set(s);
          next.delete(alert.id);
          return next;
        });
        // Remove from list
        this.alerts.update((list) => list.filter((a) => a.id !== alert.id));
        this.snackBar.open(
          this.translate.instant('alerts.card.dismissSuccess'),
          undefined,
          { duration: 3000 },
        );
      },
      error: () => {
        this.dismissingAlertIds.update((s) => {
          const next = new Set(s);
          next.delete(alert.id);
          return next;
        });
        this.snackBar.open('Unable to dismiss alert.', undefined, { duration: 3000 });
      },
    });
  }

  onActionClick(alert: Alert): void {
    navigateAlertAction(this.router, alert);
  }

  getProductName(productId: string): string {
    const p = this.products().find((prod) => prod.id === productId);
    return p ? p.tenant_name : productId;
  }

  getSupplierName(supplierId: string | null | undefined): string {
    if (!supplierId) return '—';
    const s = this.suppliers().find((supp) => supp.id === supplierId);
    return s ? s.name : supplierId;
  }

  getSeverityIcon(severity: string): string {
    switch (severity) {
      case 'critical':
        return 'error';
      case 'warning':
        return 'warning';
      case 'info':
      default:
        return 'info';
    }
  }

  getActionIcon(action: string): string {
    switch (action) {
      case 'compare_product':
        return 'compare_arrows';
      case 'review_supplier':
        return 'storefront';
      case 'view_price_history':
        return 'timeline';
      case 'inspect_scorecard':
        return 'fact_check';
      case 'review_quotation':
        return 'description';
      case 'view_delivery_issues':
        return 'local_shipping';
      default:
        return 'arrow_forward';
    }
  }
}
