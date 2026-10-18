import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiService } from '../../core/api/api.service';
import type { Locale, ReferenceOption } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n/i18n.service';

import { BranchListComponent } from './branch-list/branch-list.component';
import { BudgetListComponent } from './budget-list/budget-list.component';
import { CostCentreListComponent } from './cost-centre-list/cost-centre-list.component';
import { DelegationListComponent } from './delegation-list/delegation-list.component';
import { ThresholdRuleListComponent } from './threshold-rule-list/threshold-rule-list.component';

/**
 * The organisation settings screen (FR-011): branches, cost centres, budgets, threshold
 * rules, and approval delegations managed from one place. Each section is a fully independent
 * feature component (its own data loading, its own owner-gated write actions) — this shell
 * only composes them and provides the page-level title and spacing.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatButtonModule,
    TranslatePipe,
    BranchListComponent,
    CostCentreListComponent,
    BudgetListComponent,
    ThresholdRuleListComponent,
    DelegationListComponent,
  ],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly session = inject(SessionService);
  private readonly i18n = inject(I18nService);
  readonly currencies = signal<readonly ReferenceOption[]>([]);
  readonly selectedCurrency = signal('');
  readonly saving = signal(false);
  readonly locales: readonly Locale[] = ['en', 'ar'];
  readonly selectedLocale = signal<Locale>('en');
  readonly savingLocale = signal(false);
  readonly localeError = signal(false);

  ngOnInit(): void {
    this.selectedCurrency.set(this.session.homeCurrency() ?? '');
    this.selectedLocale.set(this.workspaceLocale());
    this.api.configOptions().subscribe((config) => this.currencies.set(config.currencies));
  }

  currencyLabel(option: ReferenceOption): string {
    return `${(this.i18n.currentLocale() === 'ar' ? option.label_ar : option.label_en) || option.code} (${option.code})`;
  }

  /** The workspace default language: RFQ emails to suppliers go out in it (finding 37). */
  workspaceLocale(): Locale {
    return this.session.tenant()?.default_locale ?? 'en';
  }

  saveLocale(): void {
    if (!this.session.hasRole('owner') || this.selectedLocale() === this.workspaceLocale()) return;
    this.savingLocale.set(true);
    this.localeError.set(false);
    this.api.updateTenant({ default_locale: this.selectedLocale() }).subscribe({
      next: (tenant) => { this.session.updateTenant(tenant); this.savingLocale.set(false); },
      error: () => { this.savingLocale.set(false); this.localeError.set(true); },
    });
  }

  saveCurrency(): void {
    if (!this.session.hasRole('owner') || !this.selectedCurrency()) return;
    this.saving.set(true);
    this.api.updateTenant({ currency: this.selectedCurrency() }).subscribe({
      next: (tenant) => { this.session.updateTenant(tenant); this.saving.set(false); },
      error: () => this.saving.set(false),
    });
  }
}
