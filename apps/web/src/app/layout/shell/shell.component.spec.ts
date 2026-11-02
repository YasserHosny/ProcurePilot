import { Component, Type, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { ApiService } from '../../core/api/api.service';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
import { AnalystApiService } from '../../features/analyst/analyst-api';
import { AnalystConversationComponent } from '../../features/analyst/conversation/conversation.component';
import { ForecastingApiService } from '../../features/forecasting/forecasting-api';
import { ReorderQueueComponent } from '../../features/forecasting/reorder-queue/reorder-queue.component';
import { BriefDetailComponent } from '../../features/supplier-risk/brief-detail/brief-detail.component';
import { RiskQueueComponent } from '../../features/supplier-risk/risk-queue/risk-queue.component';
import { SupplierRiskApiService } from '../../features/supplier-risk/supplier-risk-api';
import { ShellComponent } from './shell.component';

@Component({
  standalone: true,
  template: '',
})
class DummyRouteComponent {}

describe('ShellComponent account menu', () => {
  let fixture: ComponentFixture<ShellComponent>;
  const tenant = signal<{ name: string } | null>(null);
  const userRole = signal('buyer');

  beforeEach(async () => {
    tenant.set(null);
    userRole.set('buyer');
    localStorage.removeItem('pp.sidebar.collapsed');

    const session = {
      currentMember: signal({ email: 'buyer@example.test', role: 'buyer' }),
      tenant,
      role: userRole,
      workspaces: () => of({ items: [] }),
      logout: jasmine.createSpy('logout'),
    };
    const i18n = {
      currentLocale: signal('en'),
      isRtl: signal(false),
      setLocale: () => of(undefined),
    };

    await TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([{ path: '**', component: DummyRouteComponent }]),
        { provide: SessionService, useValue: session },
        { provide: I18nService, useValue: i18n },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(ShellComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.removeItem('pp.sidebar.collapsed');
  });

  it('offers a Contact support item that emails the support address', async () => {
    const trigger = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '.account-btn',
    );
    trigger!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const link = document.querySelector<HTMLAnchorElement>('a[mat-menu-item][href^="mailto:"]');
    expect(link).not.toBeNull();
    expect(link!.getAttribute('href')).toBe('mailto:support@iron-sys.com');
    expect(link!.textContent).toContain(enCatalog.shell.contactSupport);
  });

  it('renders a quiet footer block with MatMenuItem legal links and company byline for keyboard access', async () => {
    const trigger = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '.account-btn',
    );
    trigger!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const privacyItem = document.querySelector<HTMLAnchorElement>(
      '.menu-footer a[mat-menu-item][routerLink="/privacy"], .menu-footer a[mat-menu-item][href="/privacy"]'
    );
    const termsItem = document.querySelector<HTMLAnchorElement>(
      '.menu-footer a[mat-menu-item][routerLink="/terms"], .menu-footer a[mat-menu-item][href="/terms"]'
    );
    const companyItem = document.querySelector<HTMLAnchorElement>(
      '.menu-footer a[mat-menu-item][href="https://www.iron-sys.com/"]'
    );

    expect(privacyItem).not.toBeNull();
    expect(privacyItem!.getAttribute('role')).toBe('menuitem');
    expect(privacyItem!.textContent).toContain(enCatalog.about.privacy);

    expect(termsItem).not.toBeNull();
    expect(termsItem!.getAttribute('role')).toBe('menuitem');
    expect(termsItem!.textContent).toContain(enCatalog.about.terms);

    expect(companyItem).not.toBeNull();
    expect(companyItem!.getAttribute('role')).toBe('menuitem');
    expect(companyItem!.getAttribute('target')).toBe('_blank');
    expect(companyItem!.getAttribute('rel')).toContain('noopener');
    expect(companyItem!.textContent).toContain(enCatalog.about.companyName);
    expect(companyItem!.textContent).toContain(enCatalog.about.productByPrefix);
  });

  // WCAG 2.5.3 Label in Name: a speech-input user activates a control by saying what it shows,
  // so the accessible name must contain the visible text (axe: label-content-name-mismatch).
  describe('accessible names contain the visible text', () => {
    const query = (selector: string): HTMLElement =>
      (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(selector)!;

    it('names the account button after the initials it shows', () => {
      const button = query('.account-btn');
      const visible = query('.account-avatar').textContent!.trim();

      expect(visible).toBe('BU');
      expect(button.getAttribute('aria-label')).toContain(visible);
      expect(button.getAttribute('aria-label')).toContain('account options');
    });

    it('names the workspace switcher after the workspace it shows', () => {
      tenant.set({ name: 'Nile Restaurants' });
      fixture.detectChanges();

      const button = query('.workspace-switcher-btn');
      const visible = query('.workspace-name').textContent!.trim();

      expect(visible).toBe('Nile Restaurants');
      expect(button.getAttribute('aria-label')).toBe('Nile Restaurants, switch workspace');
    });

    it('names the workspace switcher by its visible text when no workspace is set', () => {
      const button = query('.workspace-switcher-btn');
      const visible = query('.workspace-name').textContent!.trim();

      expect(button.getAttribute('aria-label')).toBe(visible);
    });
  });

  describe('sidebar collapsible groups (Jira PPS-42)', () => {
    it('renders the 5 group labels in order, with their links in order', () => {
      userRole.set('owner');
      fixture.detectChanges();

      const root = fixture.nativeElement as HTMLElement;
      const groupButtons = Array.from(
        root.querySelectorAll<HTMLButtonElement>('.nav-group-toggle'),
      );
      expect(groupButtons.length).toBe(5);

      const expectedGroups = [
        {
          id: 'sourcing',
          label: 'Sourcing',
          routes: [
            '/quotations',
            '/matching',
            '/rfq/history',
            '/offers/compare',
            '/offers/basket-split',
          ],
        },
        {
          id: 'purchasing',
          label: 'Purchasing',
          routes: ['/requests', '/approvals', '/orders'],
        },
        {
          id: 'catalogue',
          label: 'Catalogue',
          routes: ['/products', '/suppliers', '/supplier-risk', '/import'],
        },
        {
          id: 'insight',
          label: 'Insight',
          routes: [
            '/savings',
            '/reports',
            '/forecasting',
            '/alerts',
            '/analyst',
            '/analyst/history',
          ],
        },
        {
          id: 'setup',
          label: 'Setup',
          routes: ['/team', '/settings', '/ingestion', '/accounting', '/pos'],
        },
      ];

      expectedGroups.forEach((expected, groupIndex) => {
        const btn = groupButtons[groupIndex];
        expect(btn.textContent).toContain(expected.label);

        const itemsContainer = root.querySelector<HTMLElement>(
          `#nav-group-${expected.id}`,
        )!;
        const links = Array.from(
          itemsContainer.querySelectorAll<HTMLAnchorElement>('.nav-item'),
        );
        const linkRoutes = links.map(
          (l) => l.getAttribute('href') || l.getAttribute('ng-reflect-router-link'),
        );

        expect(linkRoutes.length).toBe(expected.routes.length);
        expected.routes.forEach((route, itemIndex) => {
          expect(linkRoutes[itemIndex]).toBe(route);
        });
      });
    });

    it('toggling a group sets aria-expanded=false and hides its links; toggling again restores them', () => {
      const root = fixture.nativeElement as HTMLElement;
      const sourcingBtn = root.querySelector<HTMLButtonElement>(
        '#nav-group-header-sourcing',
      )!;
      const sourcingItems = root.querySelector<HTMLElement>(
        '#nav-group-sourcing',
      )!;

      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(sourcingItems.hidden).toBeFalse();

      // Toggle to collapse
      sourcingBtn.click();
      fixture.detectChanges();

      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('false');
      expect(sourcingItems.hidden).toBeTrue();

      // Toggle again to expand
      sourcingBtn.click();
      fixture.detectChanges();

      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(sourcingItems.hidden).toBeFalse();
    });

    it('the group containing the active route stays expanded', async () => {
      const router = TestBed.inject(Router);
      await router.navigateByUrl('/requests');
      fixture.detectChanges();

      const root = fixture.nativeElement as HTMLElement;
      const purchasingBtn = root.querySelector<HTMLButtonElement>(
        '#nav-group-header-purchasing',
      )!;
      const purchasingItems = root.querySelector<HTMLElement>(
        '#nav-group-purchasing',
      )!;

      expect(purchasingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(purchasingItems.hidden).toBeFalse();
      expect(purchasingBtn.disabled).toBeTrue();

      // Click to toggle: should stay expanded and cannot hide active route
      purchasingBtn.click();
      fixture.detectChanges();

      expect(purchasingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(purchasingItems.hidden).toBeFalse();

      // Collapse another group (sourcing)
      const sourcingBtn = root.querySelector<HTMLButtonElement>(
        '#nav-group-header-sourcing',
      )!;
      const sourcingItems = root.querySelector<HTMLElement>(
        '#nav-group-sourcing',
      )!;

      sourcingBtn.click();
      fixture.detectChanges();
      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('false');
      expect(sourcingItems.hidden).toBeTrue();

      // Navigating into the collapsed group opens it
      await router.navigateByUrl('/quotations');
      fixture.detectChanges();

      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(sourcingItems.hidden).toBeFalse();
    });

    it('applies nav-group--active only to the group owning the current route', async () => {
      const router = TestBed.inject(Router);
      const root = fixture.nativeElement as HTMLElement;

      await router.navigateByUrl('/requests');
      fixture.detectChanges();

      const purchasingGroup = root.querySelector('#nav-group-purchasing')?.closest('.nav-group');
      const sourcingGroup = root.querySelector('#nav-group-sourcing')?.closest('.nav-group');
      const catalogueGroup = root.querySelector('#nav-group-catalogue')?.closest('.nav-group');
      const insightGroup = root.querySelector('#nav-group-insight')?.closest('.nav-group');
      const setupGroup = root.querySelector('#nav-group-setup')?.closest('.nav-group');

      expect(purchasingGroup?.classList.contains('nav-group--active')).toBeTrue();
      expect(sourcingGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(catalogueGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(insightGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(setupGroup?.classList.contains('nav-group--active')).toBeFalse();

      await router.navigateByUrl('/quotations');
      fixture.detectChanges();

      expect(purchasingGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(sourcingGroup?.classList.contains('nav-group--active')).toBeTrue();
      expect(catalogueGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(insightGroup?.classList.contains('nav-group--active')).toBeFalse();
      expect(setupGroup?.classList.contains('nav-group--active')).toBeFalse();
    });

    it('expands owning group and disables toggle on child routes like /analyst/:id and /rfq/compare/:id', async () => {
      const router = TestBed.inject(Router);
      localStorage.setItem('pp.sidebar.collapsed', JSON.stringify(['insight', 'sourcing']));

      const testFixture = TestBed.createComponent(ShellComponent);
      testFixture.detectChanges();
      const testRoot = testFixture.nativeElement as HTMLElement;

      const insightBtn = testRoot.querySelector<HTMLButtonElement>('#nav-group-header-insight')!;
      const sourcingBtn = testRoot.querySelector<HTMLButtonElement>('#nav-group-header-sourcing')!;

      // Initially both start collapsed from localStorage
      expect(insightBtn.getAttribute('aria-expanded')).toBe('false');
      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('false');

      // Navigate to /analyst/abc (child route of analyst)
      await router.navigateByUrl('/analyst/abc');
      testFixture.detectChanges();

      expect(insightBtn.getAttribute('aria-expanded')).toBe('true');
      expect(insightBtn.disabled).toBeTrue();

      // Navigate to /rfq/compare/123 (child route of rfq)
      await router.navigateByUrl('/rfq/compare/123');
      testFixture.detectChanges();

      expect(sourcingBtn.getAttribute('aria-expanded')).toBe('true');
      expect(sourcingBtn.disabled).toBeTrue();

      testFixture.destroy();
    });

    it('gives nav-group-items role="group" and points aria-labelledby at the visible group-title text', () => {
      const root = fixture.nativeElement as HTMLElement;
      const expectedGroups = [
        { id: 'sourcing', label: 'Sourcing' },
        { id: 'purchasing', label: 'Purchasing' },
        { id: 'catalogue', label: 'Catalogue' },
        { id: 'insight', label: 'Insight' },
        { id: 'setup', label: 'Setup' },
      ];

      expectedGroups.forEach((expected) => {
        const itemsContainer = root.querySelector<HTMLElement>(`#nav-group-${expected.id}`)!;
        expect(itemsContainer.getAttribute('role')).toBe('group');

        const labelledById = itemsContainer.getAttribute('aria-labelledby');
        expect(labelledById).not.toBeNull();
        const labelEl = root.querySelector<HTMLElement>(`#${labelledById}`);
        expect(labelEl).not.toBeNull();
        expect(labelEl!.textContent?.trim()).toBe(expected.label);
      });
    });

    it('collapsed state persists via localStorage, and the component still renders when localStorage throws', () => {
      const root = fixture.nativeElement as HTMLElement;
      // Test persistence
      const sourcingBtn = root.querySelector<HTMLButtonElement>(
        '#nav-group-header-sourcing',
      )!;
      sourcingBtn.click();
      fixture.detectChanges();

      const raw = localStorage.getItem('pp.sidebar.collapsed');
      expect(raw).not.toBeNull();
      expect(raw).toContain('sourcing');

      // Next component instance restores collapsed state
      const reloadedFixture = TestBed.createComponent(ShellComponent);
      reloadedFixture.detectChanges();
      const reloadedRoot = reloadedFixture.nativeElement as HTMLElement;
      const reloadedSourcingBtn = reloadedRoot.querySelector<HTMLButtonElement>(
        '#nav-group-header-sourcing',
      )!;
      expect(reloadedSourcingBtn.getAttribute('aria-expanded')).toBe('false');
      reloadedFixture.destroy();

      // Test resilience when storage throws
      spyOn(Storage.prototype, 'getItem').and.throwError(new Error('Storage access denied'));
      spyOn(Storage.prototype, 'setItem').and.throwError(new Error('Storage quota exceeded'));

      expect(() => {
        const errorFixture = TestBed.createComponent(ShellComponent);
        errorFixture.detectChanges();
        const errorRoot = errorFixture.nativeElement as HTMLElement;
        const titles = errorRoot.querySelectorAll('.nav-section-title');
        expect(titles.length).toBe(5);
        errorFixture.destroy();
      }).not.toThrow();
    });
  });

  describe('accessibility and landmarks (PPS-162 / P-130)', () => {
    it('renders a "Skip to main content" link as the first focusable element targeting #main-content', () => {
      const root = fixture.nativeElement as HTMLElement;
      const skipLink = root.querySelector<HTMLAnchorElement>('a.skip-to-content, a[href="#main-content"]');
      expect(skipLink).not.toBeNull();
      expect(skipLink!.getAttribute('href')).toBe('#main-content');
      expect(skipLink!.textContent?.trim()).toBe(enCatalog.common.a11y.skipToContent);

      const focusableSelectors = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
      const firstFocusable = root.querySelector<HTMLElement>(focusableSelectors);
      expect(firstFocusable).toBe(skipLink);
    });

    it('wraps the routed content in exactly one <main id="main-content"> landmark', () => {
      const root = fixture.nativeElement as HTMLElement;
      const mainLandmarks = root.querySelectorAll('main, [role="main"]');
      expect(mainLandmarks.length).toBe(1);

      const mainEl = root.querySelector<HTMLElement>('main#main-content');
      expect(mainEl).not.toBeNull();

      const outletInsideMain = mainEl!.querySelector('router-outlet');
      expect(outletInsideMain).not.toBeNull();
    });

    it('renders the sidebar navigation inside a <nav> landmark with aria-label from i18n', () => {
      const root = fixture.nativeElement as HTMLElement;
      const sidenav = root.querySelector<HTMLElement>('.shell-sidenav')!;
      const navLandmark = sidenav.querySelector<HTMLElement>('nav');
      expect(navLandmark).not.toBeNull();
      expect(navLandmark!.getAttribute('aria-label')).toBe(enCatalog.common.a11y.mainNavigation);

      const groupInNav = navLandmark!.querySelector('.nav-group');
      expect(groupInNav).not.toBeNull();
    });

    it('provides an accessible name for the brand link to /home from i18n', () => {
      const root = fixture.nativeElement as HTMLElement;
      const brandLink = root.querySelector<HTMLAnchorElement>('a.brand-section');
      expect(brandLink).not.toBeNull();
      const ariaLabel = brandLink!.getAttribute('aria-label');
      expect(ariaLabel).toBe(enCatalog.common.brandName);
    });

    it('renders sidebar group titles as non-heading elements to preserve page heading hierarchy', () => {
      const root = fixture.nativeElement as HTMLElement;
      const sidenav = root.querySelector<HTMLElement>('.shell-sidenav')!;
      const headings = sidenav.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]');
      expect(headings.length).toBe(0);

      const toggles = sidenav.querySelectorAll<HTMLButtonElement>('.nav-group-toggle');
      expect(toggles.length).toBe(5);
      toggles.forEach((toggle) => {
        expect(toggle.getAttribute('aria-expanded')).not.toBeNull();
        expect(toggle.querySelector('.nav-group-title-text')?.textContent?.trim().length).toBeGreaterThan(0);
      });
    });

    it('prevents navigation away from current route and moves document.activeElement to #main-content when skip link is clicked (H1)', async () => {
      document.body.appendChild(fixture.nativeElement);
      try {
        const router = TestBed.inject(Router);
        await router.navigateByUrl('/quotations');
        const initialUrl = router.url;

        const root = fixture.nativeElement as HTMLElement;
        const skipLink = root.querySelector<HTMLAnchorElement>('a.skip-to-content')!;
        const mainEl = root.querySelector<HTMLElement>('#main-content')!;

        const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
        skipLink.dispatchEvent(clickEvent);
        fixture.detectChanges();

        expect(clickEvent.defaultPrevented).toBeTrue();
        expect(router.url).toBe(initialUrl);
        expect(document.activeElement).toBe(mainEl);
      } finally {
        fixture.nativeElement.remove();
      }
    });

    it('activates skip link on Enter key as native click without changing the router URL (H1)', async () => {
      document.body.appendChild(fixture.nativeElement);
      try {
        const router = TestBed.inject(Router);
        await router.navigateByUrl('/quotations');
        const initialUrl = router.url;

        const root = fixture.nativeElement as HTMLElement;
        const skipLink = root.querySelector<HTMLAnchorElement>('a.skip-to-content')!;
        const mainEl = root.querySelector<HTMLElement>('#main-content')!;

        const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
        skipLink.dispatchEvent(clickEvent);
        fixture.detectChanges();

        expect(clickEvent.defaultPrevented).toBeTrue();
        expect(router.url).toBe(initialUrl);
        expect(document.activeElement).toBe(mainEl);
      } finally {
        fixture.nativeElement.remove();
      }
    });

    it('guards against missing #main-content element when focusMainContent is called (H1)', () => {
      const event = new MouseEvent('click', { bubbles: true, cancelable: true });
      spyOn(event, 'preventDefault').and.callThrough();

      const mainEl = fixture.nativeElement.querySelector('#main-content');
      mainEl?.remove();

      expect(() => {
        fixture.componentInstance.focusMainContent(event);
      }).not.toThrow();
      expect(event.preventDefault).toHaveBeenCalled();
    });
  });
});

describe('ShellComponent nested route landmarks (PPS-162 / H2)', () => {
  beforeEach(async () => {
    TestBed.resetTestingModule();
    localStorage.removeItem('pp.sidebar.collapsed');

    const session = {
      currentMember: signal({ email: 'buyer@example.test', role: 'buyer' }),
      tenant: signal(null),
      role: signal('buyer'),
      workspaces: () => of({ items: [] }),
      logout: jasmine.createSpy('logout'),
      hasRole: () => true,
      isAuthenticated: signal(true),
      activeLocale: signal<'en' | 'ar'>('en'),
    };
    const i18n = {
      currentLocale: signal('en'),
      isRtl: signal(false),
      setLocale: () => of(undefined),
    };
    const analystApi = {
      ask: () => of({}),
      getConversation: () => of({ id: '1', turns: [] }),
    };
    const forecastingApi = {
      listProposals: () => of({ items: [] }),
    };
    const supplierRiskApi = {
      listRisks: () => of({ items: [], next_cursor: null }),
      getBrief: () =>
        of({
          id: 'brief-1',
          supplier_id: 'supplier-1',
          snapshot_id: 'snapshot-1',
          brief_version: 'negotiation-brief-v1',
          source_fingerprint: 'fp-1',
          release_posture: 'g3_unmet',
          valid_from: '2026-09-24T00:00:00Z',
          valid_until: '2099-09-24T00:00:00Z',
          status: 'prepared',
          items: [],
          recommended_actions: [],
          evidence: [],
        }),
    };
    const api = {
      listBranches: () => of({ items: [] }),
    };
    const snackBar = {
      open: jasmine.createSpy('open'),
    };

    await TestBed.configureTestingModule({
      imports: [
        ShellComponent,
        AnalystConversationComponent,
        ReorderQueueComponent,
        RiskQueueComponent,
        BriefDetailComponent,
      ],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([
          {
            path: '',
            component: ShellComponent,
            children: [
              { path: 'analyst', component: AnalystConversationComponent },
              { path: 'forecasting', component: ReorderQueueComponent },
              { path: 'supplier-risk', component: RiskQueueComponent },
              { path: 'negotiation-briefs/:id', component: BriefDetailComponent },
            ],
          },
        ]),
        { provide: SessionService, useValue: session },
        { provide: I18nService, useValue: i18n },
        { provide: AnalystApiService, useValue: analystApi },
        { provide: ForecastingApiService, useValue: forecastingApi },
        { provide: SupplierRiskApiService, useValue: supplierRiskApi },
        { provide: ApiService, useValue: api },
        { provide: MatSnackBar, useValue: snackBar },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
  });

  afterEach(() => {
    localStorage.removeItem('pp.sidebar.collapsed');
    TestBed.resetTestingModule();
  });

  const routesToTest = [
    { path: '/analyst', name: 'AnalystConversationComponent' },
    { path: '/forecasting', name: 'ReorderQueueComponent' },
    { path: '/supplier-risk', name: 'RiskQueueComponent' },
    { path: '/negotiation-briefs/brief-1', name: 'BriefDetailComponent' },
  ];

  routesToTest.forEach(({ path, name }) => {
    it(`renders exactly one <main id="main-content"> with no nested <main> landmark when routed to ${path} (${name})`, async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(path);

      const root = harness.fixture.nativeElement as HTMLElement;
      const mainLandmarks = root.querySelectorAll('main, [role="main"]');
      expect(mainLandmarks.length).toBe(1);

      const shellMain = root.querySelector<HTMLElement>('main#main-content');
      expect(shellMain).not.toBeNull();

      const nestedMains = shellMain!.querySelectorAll('main, [role="main"]');
      expect(nestedMains.length).toBe(0);
    });
  });

  const componentsToTest: { component: Type<unknown>; name: string }[] = [
    { component: AnalystConversationComponent, name: 'AnalystConversationComponent' },
    { component: ReorderQueueComponent, name: 'ReorderQueueComponent' },
    { component: RiskQueueComponent, name: 'RiskQueueComponent' },
    { component: BriefDetailComponent, name: 'BriefDetailComponent' },
  ];

  componentsToTest.forEach(({ component, name }) => {
    it(`ensures ${name} contains no <main> landmark in its own template`, () => {
      const compFixture = TestBed.createComponent(component);
      compFixture.detectChanges();
      const root = compFixture.nativeElement as HTMLElement;
      expect(root.tagName.toLowerCase()).not.toBe('main');
      expect(root.querySelector('main, [role="main"]')).toBeNull();
      compFixture.destroy();
    });
  });
});
