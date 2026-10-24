import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
import { ShellComponent } from './shell.component';

describe('ShellComponent account menu', () => {
  let fixture: ComponentFixture<ShellComponent>;

  beforeEach(async () => {
    const session = {
      currentMember: signal({ email: 'buyer@example.test', role: 'buyer' }),
      tenant: signal(null),
      role: signal('buyer'),
      workspaces: () => of({ items: [] }),
      logout: jasmine.createSpy('logout'),
    };
    const i18n = {
      currentLocale: signal('en'),
      setLocale: () => of(undefined),
    };

    await TestBed.configureTestingModule({
      imports: [ShellComponent, TranslateModule.forRoot()],
      providers: [
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
      `[aria-label="${enCatalog.shell.accountMenuLabel}"]`,
    );
    trigger!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    const link = document.querySelector<HTMLAnchorElement>('a[mat-menu-item][href^="mailto:"]');
    expect(link).not.toBeNull();
    expect(link!.getAttribute('href')).toBe('mailto:support@iron-sys.com');
    expect(link!.textContent).toContain(enCatalog.shell.contactSupport);
  });
});
