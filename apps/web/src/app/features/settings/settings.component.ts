import { Component } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { BranchListComponent } from './branch-list/branch-list.component';
import { BudgetListComponent } from './budget-list/budget-list.component';
import { CostCentreListComponent } from './cost-centre-list/cost-centre-list.component';

/**
 * Interim composition: renders all three list components directly until T042 (Phase 7)
 * replaces this with the full composed screen per FR-011. All of US1-US3 now land here.
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
