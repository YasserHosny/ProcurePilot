import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../core/api/api.service';
import type { ConfigOptions, ReferenceOption, Role } from '../../core/api/models';
import { RoleDirective } from '../../core/auth/role.directive';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';

export interface HomeModuleCard {
  readonly key: string;
  readonly route: string;
  readonly icon: string;
  readonly titleKey: string;
  readonly descriptionKey: string;
  readonly roles?: readonly Role[];
}

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatIconModule, TranslatePipe, RoleDirective],
  templateUrl: './home.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './home.component.scss',
})
export class HomeComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);
  private readonly i18n = inject(I18nService);

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;
  readonly configOptions = signal<ConfigOptions | null>(null);

  /**
   * Main procurement module links matching the sidebar icons and role restrictions
   * in shell.component.html.
   */
  readonly modules: readonly HomeModuleCard[] = [
    {
      key: 'quotations',
      route: '/quotations',
      icon: 'receipt_long',
      titleKey: 'home.modules.quotations.title',
      descriptionKey: 'home.modules.quotations.description',
    },
    {
      key: 'rfq',
      route: '/rfq/history',
      icon: 'history',
      titleKey: 'home.modules.rfq.title',
      descriptionKey: 'home.modules.rfq.description',
    },
    {
      key: 'compare',
      route: '/offers/compare',
      icon: 'auto_awesome',
      titleKey: 'home.modules.compare.title',
      descriptionKey: 'home.modules.compare.description',
    },
    {
      key: 'requests',
      route: '/requests',
      icon: 'shopping_cart',
      titleKey: 'home.modules.requests.title',
      descriptionKey: 'home.modules.requests.description',
    },
    {
      key: 'approvals',
      route: '/approvals',
      icon: 'approval',
      titleKey: 'home.modules.approvals.title',
      descriptionKey: 'home.modules.approvals.description',
    },
    {
      key: 'orders',
      route: '/orders',
      icon: 'assignment',
      titleKey: 'home.modules.orders.title',
      descriptionKey: 'home.modules.orders.description',
    },
    {
      key: 'savings',
      route: '/savings',
      icon: 'payments',
      titleKey: 'home.modules.savings.title',
      descriptionKey: 'home.modules.savings.description',
    },
    {
      key: 'analyst',
      route: '/analyst',
      icon: 'forum',
      titleKey: 'home.modules.analyst.title',
      descriptionKey: 'home.modules.analyst.description',
    },
    {
      key: 'products',
      route: '/products',
      icon: 'inventory_2',
      titleKey: 'home.modules.products.title',
      descriptionKey: 'home.modules.products.description',
    },
    {
      key: 'suppliers',
      route: '/suppliers',
      icon: 'store',
      titleKey: 'home.modules.suppliers.title',
      descriptionKey: 'home.modules.suppliers.description',
    },
  ];

  readonly regionLabel = computed<string>(() => {
    const code = this.tenant()?.region;
    if (!code) return '';
    return this.resolveOptionLabel(this.configOptions()?.regions, code);
  });

  readonly taxModelLabel = computed<string>(() => {
    const code = this.tenant()?.tax_model;
    if (!code) return '';
    return this.resolveOptionLabel(this.configOptions()?.tax_models, code);
  });

  ngOnInit(): void {
    this.api.configOptions().subscribe({
      next: (options) => this.configOptions.set(options),
      error: () => this.configOptions.set(null),
    });
  }

  formatRole(role: Role | null | undefined): string {
    if (!role) return '';
    return this.translate.instant(`common.roles.${role}`);
  }

  private resolveOptionLabel(
    items: readonly ReferenceOption[] | undefined,
    code: string,
  ): string {
    const match = items?.find((item) => item.code === code);
    if (!match) return code;
    return this.i18n.currentLocale() === 'ar' ? match.label_ar : match.label_en;
  }
}
