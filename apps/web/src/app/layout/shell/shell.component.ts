import { Component, OnInit, ViewChild, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { BreakpointObserver } from '@angular/cdk/layout';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenav, MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { filter } from 'rxjs';

import type { Locale, Role, WorkspaceSummary } from '../../core/api/models';
import { RoleDirective } from '../../core/auth/role.directive';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
import { BrandLogoComponent } from '../brand-logo/brand-logo.component';
import { environment } from '../../../environments/environment';

export interface NavItem {
  route: string;
  labelKey: string;
  icon: string;
  exact?: boolean;
  roles?: Role | Role[];
  groupPrefix?: string;
}

export interface NavGroup {
  id: string;
  labelKey: string;
  items: NavItem[];
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    BrandLogoComponent,
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
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly breakpoint = inject(BreakpointObserver);
  readonly i18n = inject(I18nService);
  private readonly translate = inject(TranslateService);

  @ViewChild('sidenav') sidenav!: MatSidenav;

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;
  readonly currentLocale = this.i18n.currentLocale;
  readonly isRtl = this.i18n.isRtl;
  readonly supportMailto = `mailto:${environment.supportEmail}`;

  readonly isMobile = signal(false);
  readonly workspaces = signal<WorkspaceSummary[]>([]);
  readonly isSwitchingWorkspace = signal<boolean>(false);

  readonly sidenavMode = computed(() => this.isMobile() ? 'over' as const : 'side' as const);
  readonly sidenavOpened = computed(() => !this.isMobile());

  readonly userInitials = computed<string>(() => {
    const email = this.member()?.email;
    if (!email) return 'U';
    return email.substring(0, 2).toUpperCase();
  });

  private readonly storageKey = 'pp.sidebar.collapsed';
  readonly currentUrl = signal<string>(this.router.url || '');
  readonly collapsedGroups = signal<Set<string>>(this.readCollapsedStorage());

  readonly homeItem: NavItem = {
    route: '/home',
    labelKey: 'shell.navHome',
    icon: 'dashboard',
  };

  readonly navGroups: NavGroup[] = [
    {
      id: 'sourcing',
      labelKey: 'shell.sourcing',
      items: [
        { route: '/quotations', labelKey: 'shell.navQuotations', icon: 'receipt_long' },
        { route: '/matching', labelKey: 'shell.navMatching', icon: 'compare_arrows' },
        { route: '/rfq/history', labelKey: 'shell.navRfq', icon: 'history', groupPrefix: '/rfq' },
        { route: '/offers/compare', labelKey: 'shell.navCompare', icon: 'auto_awesome' },
        { route: '/offers/basket-split', labelKey: 'shell.navBasketSplit', icon: 'call_split' },
      ],
    },
    {
      id: 'purchasing',
      labelKey: 'shell.purchasing',
      items: [
        { route: '/requests', labelKey: 'shell.navRequests', icon: 'shopping_cart' },
        { route: '/approvals', labelKey: 'shell.navApprovals', icon: 'approval' },
        { route: '/orders', labelKey: 'shell.navOrders', icon: 'assignment' },
      ],
    },
    {
      id: 'catalogue',
      labelKey: 'shell.catalogue',
      items: [
        { route: '/products', labelKey: 'shell.navProducts', icon: 'inventory_2' },
        { route: '/suppliers', labelKey: 'shell.navSuppliers', icon: 'store' },
        { route: '/supplier-risk', labelKey: 'shell.navSupplierRisk', icon: 'shield' },
        { route: '/import', labelKey: 'shell.navImport', icon: 'upload_file', roles: ['owner', 'buyer'] },
      ],
    },
    {
      id: 'insight',
      labelKey: 'shell.insight',
      items: [
        { route: '/savings', labelKey: 'shell.navSavings', icon: 'savings' },
        { route: '/reports', labelKey: 'reports.nav', icon: 'assessment' },
        { route: '/forecasting', labelKey: 'shell.navForecasting', icon: 'trending_up', roles: ['owner', 'buyer'] },
        { route: '/alerts', labelKey: 'shell.navAlerts', icon: 'notifications' },
        { route: '/analyst', labelKey: 'shell.navAnalyst', icon: 'forum', exact: true, groupPrefix: '/analyst' },
        { route: '/analyst/history', labelKey: 'analyst.navHistory', icon: 'history' },
      ],
    },
    {
      id: 'setup',
      labelKey: 'shell.setup',
      items: [
        { route: '/team', labelKey: 'shell.navTeam', icon: 'group', roles: 'owner' },
        { route: '/settings', labelKey: 'shell.navSettings', icon: 'settings' },
        { route: '/ingestion', labelKey: 'ingestion.nav', icon: 'inbox' },
        { route: '/accounting', labelKey: 'accounting.nav', icon: 'account_balance' },
        { route: '/pos', labelKey: 'pos.nav', icon: 'point_of_sale' },
      ],
    },
  ];

  ngOnInit(): void {
    this.loadWorkspaces();

    this.breakpoint.observe('(max-width: 959px)').subscribe((result) => {
      this.isMobile.set(result.matches);
    });

    this.currentUrl.set(this.router.url || '');
    this.ensureActiveGroupExpanded();

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((event) => {
        this.currentUrl.set(event.urlAfterRedirects || event.url);
        if (this.isMobile() && this.sidenav?.opened) {
          this.sidenav.close();
        }
        this.ensureActiveGroupExpanded();
      });
  }

  isGroupActive(groupId: string): boolean {
    const group = this.navGroups.find((g) => g.id === groupId);
    if (!group) return false;
    const url = this.currentUrl() || this.router.url || '';
    const cleanUrl = url.split('?')[0].split('#')[0];
    return group.items.some((item) => {
      const prefix = item.groupPrefix ?? item.route;
      if (cleanUrl) {
        if (cleanUrl === prefix || cleanUrl.startsWith(prefix + '/')) {
          return true;
        }
      }
      try {
        if (this.router.isActive(item.route, {
          paths: item.exact ? 'exact' : 'subset',
          queryParams: 'ignored',
          fragment: 'ignored',
          matrixParams: 'ignored',
        })) {
          return true;
        }
      } catch {
        // Router might not have active route match in unit tests
      }
      return false;
    });
  }

  isGroupCollapsed(groupId: string): boolean {
    if (this.isGroupActive(groupId)) {
      return false;
    }
    return this.collapsedGroups().has(groupId);
  }

  toggleGroup(groupId: string): void {
    if (this.isGroupActive(groupId)) {
      // Disable collapse for the group containing the active route
      return;
    }
    const next = new Set(this.collapsedGroups());
    if (next.has(groupId)) {
      next.delete(groupId);
    } else {
      next.add(groupId);
    }
    this.collapsedGroups.set(next);
    this.writeCollapsedStorage(next);
  }

  private ensureActiveGroupExpanded(): void {
    for (const group of this.navGroups) {
      if (this.isGroupActive(group.id)) {
        if (this.collapsedGroups().has(group.id)) {
          const next = new Set(this.collapsedGroups());
          next.delete(group.id);
          this.collapsedGroups.set(next);
          this.writeCollapsedStorage(next);
        }
        break;
      }
    }
  }

  private readCollapsedStorage(): Set<string> {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (!raw) return new Set<string>();
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return new Set<string>(parsed.filter((item): item is string => typeof item === 'string'));
      }
    } catch {
      // Return default all expanded if storage unavailable
    }
    return new Set<string>();
  }

  private writeCollapsedStorage(collapsed: Set<string>): void {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(Array.from(collapsed)));
    } catch {
      // Silently handle quota or disabled storage
    }
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
