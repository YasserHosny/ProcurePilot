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
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { Locale, Role, WorkspaceSummary } from '../../core/api/models';
import { RoleDirective } from '../../core/auth/role.directive';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';

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
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  readonly i18n = inject(I18nService);
  private readonly translate = inject(TranslateService);

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;
  readonly currentLocale = this.i18n.currentLocale;

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
    return this.translate.instant(`common.roles.${role}`);
  }

  onSelectLanguage(lang: Locale): void {
    // MUST subscribe. setLocale applies the language immediately but returns a cold observable
    // for the PATCH /me that persists the choice, and an unsubscribed HttpClient observable never
    // issues its request. Without this the switch looked like it worked — the UI flipped to
    // Arabic and RTL — and then reverted on the next reload, because the server had never been
    // told and still reported 'en'.
    this.i18n.setLocale(lang).subscribe();
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
