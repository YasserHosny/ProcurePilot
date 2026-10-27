import { Injectable, InjectionToken, effect, inject, signal, untracked } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { ApiService } from '../api/api.service';
import type { Locale, Me } from '../api/models';
import { SessionService } from '../auth/session.service';
import { DirectionService } from './direction.service';

export const LOCALE_STORAGE_KEY = 'pp.locale';
export const LOCALE_CHOSEN_STORAGE_KEY = 'pp.locale.chosen';

export const I18N_LOCATION_SEARCH = new InjectionToken<() => string>(
  'I18N_LOCATION_SEARCH',
  {
    providedIn: 'root',
    factory: () => () => (typeof window !== 'undefined' ? window.location.search : ''),
  },
);

export const I18N_LOCATION_PATHNAME = new InjectionToken<() => string>(
  'I18N_LOCATION_PATHNAME',
  {
    providedIn: 'root',
    factory: () => () => (typeof window !== 'undefined' ? window.location.pathname : ''),
  },
);

function parseQueryLocale(search: string): Locale | null {
  try {
    const params = new URLSearchParams(search);
    const lang = params.get('lang')?.toLowerCase();
    if (lang === 'en' || lang === 'ar') {
      return lang;
    }
  } catch {
    // Ignore invalid search strings
  }
  return null;
}

@Injectable({ providedIn: 'root' })
export class I18nService {
  private readonly translate = inject(TranslateService);
  private readonly direction = inject(DirectionService);
  private readonly session = inject(SessionService);
  private readonly api = inject(ApiService);
  private readonly getLocationSearch =
    inject(I18N_LOCATION_SEARCH, { optional: true }) ??
    (() => (typeof window !== 'undefined' ? window.location.search : ''));
  private readonly getLocationPathname =
    inject(I18N_LOCATION_PATHNAME, { optional: true }) ??
    (() => (typeof window !== 'undefined' ? window.location.pathname : ''));

  private readonly localeSignal = signal<Locale>('en');

  /** The last locale the SESSION reported, so a user's own choice is not overwritten by it. */
  private lastSessionLocale: Locale | null = null;

  /** Tracks whether the session was authenticated on the previous effect run (PPS-86). */
  private wasAuthenticated = this.session.isAuthenticated();

  readonly currentLocale = this.localeSignal.asReadonly();
  readonly isRtl = this.direction.isRtl;

  constructor() {
    this.translate.addLangs(['en', 'ar']);
    this.translate.setFallbackLang('en');

    const queryLocale = parseQueryLocale(this.getLocationSearch());
    let initialLocale: Locale;

    if (queryLocale) {
      localStorage.setItem(LOCALE_CHOSEN_STORAGE_KEY, queryLocale);
      initialLocale = queryLocale;
    } else if (this.session.isAuthenticated()) {
      initialLocale = this.session.activeLocale();
    } else {
      const pathname = this.getLocationPathname();
      const isDefaultArabicRoute =
        pathname === '/' || pathname === '' || pathname === '/auth/sign-in';
      if (isDefaultArabicRoute) {
        const chosen = localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY) as Locale | null;
        initialLocale = chosen === 'en' || chosen === 'ar' ? chosen : 'ar';
      } else {
        const stored = localStorage.getItem(LOCALE_STORAGE_KEY) as Locale | null;
        initialLocale = stored === 'ar' || stored === 'en' ? stored : 'en';
      }
    }

    this.applyLocale(initialLocale);

    this.lastSessionLocale = this.session.isAuthenticated()
      ? this.session.activeLocale()
      : initialLocale;

    // Adopt the session's locale when the SESSION changes — sign-in, session restore, workspace
    // switch — and never merely because the local choice differs from it.
    //
    // The previous version compared against localeSignal() and so re-ran on every local change:
    // choosing Arabic set the signal, the effect woke, saw the server still said 'en', and
    // immediately applied 'en' again. The language switcher appeared completely dead — no error,
    // no flicker, nothing — because the revert happened in the same tick. Tracking the last value
    // the session reported means a user's explicit choice is never fought by a stale one.
    //
    // PPS-86: On a signed-out → signed-in transition, honour any explicit guest choice
    // (pp.locale.chosen) only on interactive sign-in (not background/restore session load).
    // If it differs from the account's activeLocale, persist it to the server.
    effect(() => {
      const isAuth = this.session.isAuthenticated();
      const wasAuth = this.wasAuthenticated;
      this.wasAuthenticated = isAuth;

      if (!isAuth) {
        return;
      }

      const active = this.session.activeLocale();

      if (!wasAuth && untracked(this.session.signedInInteractively)) {
        const chosen = localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY) as Locale | null;
        if ((chosen === 'en' || chosen === 'ar') && chosen !== active) {
          this.setLocale(chosen, true).subscribe();
          return;
        }
      }

      if (active && active !== this.lastSessionLocale) {
        this.lastSessionLocale = active;
        if (active !== untracked(this.localeSignal)) {
          this.applyLocale(active);
        }
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
    // Claim the choice before applying it: the server round-trip below is asynchronous, and
    // without this the session effect would still be holding the old value.
    this.lastSessionLocale = locale;
    localStorage.setItem(LOCALE_CHOSEN_STORAGE_KEY, locale);
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
