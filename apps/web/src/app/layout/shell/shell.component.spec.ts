import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
import { ShellComponent } from './shell.component';

describe('ShellComponent account menu', () => {
  let fixture: ComponentFixture<ShellComponent>;
  const tenant = signal<{ name: string } | null>(null);

  beforeEach(async () => {
    tenant.set(null);
    const session = {
      currentMember: signal({ email: 'buyer@example.test', role: 'buyer' }),
      tenant,
      role: signal('buyer'),
      workspaces: () => of({ items: [] }),
      logout: jasmine.createSpy('logout'),
    };
    const i18n = {
      currentLocale: signal('en'),
      setLocale: () => of(undefined),
    };

    await TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([]),
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
});
