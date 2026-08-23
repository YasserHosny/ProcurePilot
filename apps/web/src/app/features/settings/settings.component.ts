import { Component } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { BranchListComponent } from './branch-list/branch-list.component';
import { BudgetListComponent } from './budget-list/budget-list.component';
import { CostCentreListComponent } from './cost-centre-list/cost-centre-list.component';

/**
 * The organisation settings screen (FR-011): branches, cost centres, and budgets managed from
 * one place. Each section is a fully independent feature component (its own data loading, its
 * own owner-gated write actions) — this shell only composes them and provides the page-level
 * title and spacing.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    TranslatePipe,
    BranchListComponent,
    CostCentreListComponent,
    BudgetListComponent,
  ],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {}
