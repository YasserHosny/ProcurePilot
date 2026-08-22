import { Component } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { BranchListComponent } from './branch-list/branch-list.component';
import { CostCentreListComponent } from './cost-centre-list/cost-centre-list.component';

/**
 * Interim composition: renders BranchListComponent and CostCentreListComponent directly until
 * US3 (budgets) lands and T042 replaces this with the full composed screen per FR-011.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [TranslatePipe, BranchListComponent, CostCentreListComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {}
