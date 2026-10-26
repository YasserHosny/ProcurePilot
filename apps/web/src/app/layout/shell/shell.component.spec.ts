import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
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

  it('renders a quiet footer block with legal links and company byline', async () => {
    const trigger = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '.account-btn',
    );
    trigger!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const privacyLink = document.querySelector<HTMLAnchorElement>('.menu-footer a[routerLink="/privacy"], .menu-footer a[href="/privacy"]');
    const termsLink = document.querySelector<HTMLAnchorElement>('.menu-footer a[routerLink="/terms"], .menu-footer a[href="/terms"]');
    expect(privacyLink).not.toBeNull();
    expect(privacyLink!.textContent).toContain(enCatalog.about.privacy);
    expect(termsLink).not.toBeNull();
    expect(termsLink!.textContent).toContain(enCatalog.about.terms);

    const makerLink = document.querySelector<HTMLAnchorElement>('.menu-maker-link');
    expect(makerLink).not.toBeNull();
    expect(makerLink!.getAttribute('href')).toBe('https://www.iron-sys.com/');
    expect(makerLink!.getAttribute('target')).toBe('_blank');
    expect(makerLink!.getAttribute('rel')).toContain('noopener');
    expect(makerLink!.textContent).toContain(enCatalog.about.companyName);

    const footerBlock = document.querySelector<HTMLElement>('.menu-footer');
    expect(footerBlock).not.toBeNull();
    expect(footerBlock!.textContent).toContain(enCatalog.about.productByPrefix);
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
});
