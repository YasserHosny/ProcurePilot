import { Component, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

import type { Role } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { HOME_STRINGS } from './home.strings';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  private readonly session = inject(SessionService);

  readonly strings = HOME_STRINGS;

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;

  formatRole(role: Role | null | undefined): string {
    if (!role) return '';
    switch (role) {
      case 'owner':
        return this.strings.roleOwner;
      case 'buyer':
        return this.strings.roleBuyer;
      case 'branch_manager':
        return this.strings.roleBranchManager;
      case 'approver':
        return this.strings.roleApprover;
      case 'viewer':
        return this.strings.roleViewer;
    }
  }
}
