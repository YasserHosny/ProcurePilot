import { Injectable, effect, inject, signal } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { ApiService } from '../api/api.service';
import type { Locale, Me } from '../api/models';
import { SessionService } from '../auth/session.service';
import { DirectionService } from './direction.service';

const LOCALE_STORAGE_KEY = 'pp.locale';

@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly translate = inject(TranslateService);
  private readonly direction = inject(DirectionService);
  private readonly session = inject(SessionService);
  private readonly api = inject(ApiService);

  private readonly localeSignal = signal<Locale>('en');

  readonly currentLocale = this.localeSignal.asReadonly();
  readonly isRtl = this.direction.isRtl;

  constructor() {
    this.translate.addLangs(['en', 'ar']);
    this.translate.setDefaultLang('en');

    // Restore guest preference or default
    const storedLocale = (localStorage.getItem(LOCALE_STORAGE_KEY) as Locale | null) ?? 'en';
    const initialLocale = this.session.isAuthenticated()
      ? this.session.activeLocale()
      : storedLocale;

    this.applyLocale(initialLocale);

    // Reactively synchronise when session/member updates (e.g. login, session restore)
    effect(() => {
      const active = this.session.activeLocale();
      if (active && active !== this.localeSignal()) {
        this.applyLocale(active);
      }
    });
  }

  /**
   * Sets the active language, updates text direction, and persists the choice.
   *
   * If authenticated, persists to the database via updateMe ({ preferred_locale }).
   * Always persists to localStorage to support guest screens and reloads.
   */
  setLocale(locale: Locale, persistToServer = true): Observable<Me | null> {
    this.applyLocale(locale);

    if (persistToServer && this.session.isAuthenticated()) {
      return this.api.updateMe({ preferred_locale: locale }).pipe(
        map((updated) => updated),
        catchError((err) => {
          console.error('[i18n] Failed to persist preferred_locale to server', err);
          return of(null);
        }),
      );
    }

    return of(null);
  }

  private applyLocale(locale: Locale): void {
    this.localeSignal.set(locale);
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    this.translate.use(locale);
    const dir = locale === 'ar' ? 'rtl' : 'ltr';
    this.direction.setDirection(dir, locale);
  }
}
