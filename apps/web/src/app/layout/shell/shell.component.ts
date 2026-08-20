import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import type { Role, WorkspaceSummary } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { SHELL_STRINGS } from './shell.strings';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatSidenavModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatDividerModule,
    MatTooltipModule,
    MatListModule,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly strings = SHELL_STRINGS;

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;

  readonly workspaces = signal<WorkspaceSummary[]>([]);
  readonly isSwitchingWorkspace = signal<boolean>(false);

  readonly userInitials = computed<string>(() => {
    const email = this.member()?.email;
    if (!email) return 'U';
    return email.substring(0, 2).toUpperCase();
  });

  ngOnInit(): void {
    this.loadWorkspaces();
  }

  loadWorkspaces(): void {
    this.session.workspaces().subscribe({
      next: (res) => {
        this.workspaces.set(res.items);
      },
      error: () => {
        // Silently retain current workspace if list fails
      },
    });
  }

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

  onSwitchWorkspace(tenantId: string): void {
    this.isSwitchingWorkspace.set(true);
    this.session.switchWorkspace(tenantId).subscribe({
      next: () => {
        this.isSwitchingWorkspace.set(false);
        this.loadWorkspaces();
      },
      error: () => {
        this.isSwitchingWorkspace.set(false);
      },
    });
  }

  onSignOut(): void {
    this.session.logout();
    void this.router.navigate(['/auth/sign-in']);
  }
}
