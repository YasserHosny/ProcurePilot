import { Component } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { BranchListComponent } from './branch-list/branch-list.component';

/**
 * Interim composition: renders BranchListComponent directly until US2/US3 (cost centres,
 * budgets) land and T042 replaces this with the full composed screen per FR-011.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [TranslatePipe, BranchListComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {}
