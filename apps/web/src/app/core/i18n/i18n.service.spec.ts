import { Directionality } from '@angular/cdk/bidi';
import { computed, signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Locale, Me, Tenant } from '../api/models';
import { SessionService } from '../auth/session.service';
import { DirectionService } from './direction.service';
import {
  I18nService,
  I18N_LOCATION_PATHNAME,
  I18N_LOCATION_SEARCH,
  LOCALE_CHOSEN_STORAGE_KEY,
} from './i18n.service';

class FakeSessionService {
  readonly member: WritableSignal<Me | null> = signal<Me | null>(null);
  readonly currentMember = this.member.asReadonly();
  readonly isAuthenticated = computed(() => this.member() !== null);
  readonly activeLocale = computed<Locale>(
    () => this.member()?.preferred_locale ?? this.member()?.tenant.default_locale ?? 'en',
  );
}

const mockTenant: Tenant = {
  id: 'tenant-123',
  name: 'Acme Corp',
  slug: 'acme',
  region: 'me-central-1',
  currency: 'AED',
  tax_model: 'standard',
  default_locale: 'en',
  created_at: '2026-01-01T00:00:00Z',
};

const mockMember: Me = {
  id: 'user-123',
  email: 'test@example.com',
  role: 'buyer',
  preferred_locale: 'ar',
  mfa_enabled: false,
  tenant: mockTenant,
};

describe('I18nService', () => {
  let fakeSession: FakeSessionService;
  let apiSpy: jasmine.SpyObj<ApiService>;
  let currentSearch: string;
  let currentPathname: string;

  beforeEach(() => {
    localStorage.clear();
    fakeSession = new FakeSessionService();
    apiSpy = jasmine.createSpyObj<ApiService>('ApiService', ['updateMe']);
    apiSpy.updateMe.and.returnValue(of(mockMember));
    currentSearch = '';
    currentPathname = '/auth/sign-in';

    TestBed.configureTestingModule({
      providers: [
        provideTranslateService(),
        Directionality,
        DirectionService,
        I18nService,
        { provide: SessionService, useValue: fakeSession },
        { provide: ApiService, useValue: apiSpy },
        { provide: I18N_LOCATION_SEARCH, useValue: () => currentSearch },
        { provide: I18N_LOCATION_PATHNAME, useValue: () => currentPathname },
      ],
    });
  });

  afterEach(() => {
    localStorage.clear();
    const dirService = TestBed.inject(DirectionService);
    dirService.setDirection('ltr', 'en');
  });

  it('preserves guest Arabic preference after construction and effects flush', () => {
    localStorage.setItem('pp.locale', 'ar');
    const service = TestBed.inject(I18nService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
  });

  it('adopts preferred locale when a guest signs in', () => {
    localStorage.setItem('pp.locale', 'en');
    localStorage.setItem(LOCALE_CHOSEN_STORAGE_KEY, 'en');
    const service = TestBed.inject(I18nService);

    TestBed.flushEffects();
    expect(service.currentLocale()).toBe('en');

    fakeSession.member.set(mockMember);
    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
  });

  it('does not call updateMe when setLocale is called as a guest', () => {
    const service = TestBed.inject(I18nService);

    service.setLocale('ar');

    expect(apiSpy.updateMe).not.toHaveBeenCalled();
    expect(service.currentLocale()).toBe('ar');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
  });

  it('applies Arabic locale, rtl direction, and persists to localStorage when guest opens with ?lang=ar', () => {
    currentSearch = '?lang=ar';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(service.isRtl()).toBeTrue();
    expect(dirService.currentDirection()).toBe('rtl');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
    expect(apiSpy.updateMe).not.toHaveBeenCalled();
  });

  it('overrides stored Arabic locale with English when guest opens with ?lang=en (case-insensitive)', () => {
    localStorage.setItem('pp.locale', 'ar');
    currentSearch = '?lang=EN';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(localStorage.getItem('pp.locale')).toBe('en');
    expect(apiSpy.updateMe).not.toHaveBeenCalled();
  });

  it('ignores unsupported lang parameter like ?lang=fr and preserves default or stored locale', () => {
    localStorage.setItem('pp.locale', 'ar');
    currentSearch = '?lang=fr';
    const service = TestBed.inject(I18nService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
  });

  it('applies English without persisting to server when signed-in user with session locale ar opens with ?lang=en', () => {
    fakeSession.member.set(mockMember);
    expect(fakeSession.isAuthenticated()).toBeTrue();
    expect(fakeSession.activeLocale()).toBe('ar');

    currentSearch = '?lang=en';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(apiSpy.updateMe).not.toHaveBeenCalled();
  });

  it('defaults to Arabic with rtl direction for a guest on / with nothing stored', () => {
    currentPathname = '/';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(service.isRtl()).toBeTrue();
    expect(dirService.currentDirection()).toBe('rtl');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBeNull();
  });

  it('defaults to Arabic for a guest on / when a stale pp.locale=en exists without explicit choice', () => {
    localStorage.setItem('pp.locale', 'en');
    currentPathname = '/';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(service.isRtl()).toBeTrue();
    expect(dirService.currentDirection()).toBe('rtl');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBeNull();
  });

  it('yields English on reload for a guest on / after explicit setLocale(en)', () => {
    currentPathname = '/';
    const service = TestBed.inject(I18nService);
    service.setLocale('en');

    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBe('en');
    expect(localStorage.getItem('pp.locale')).toBe('en');

    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideTranslateService(),
        Directionality,
        DirectionService,
        I18nService,
        { provide: SessionService, useValue: fakeSession },
        { provide: ApiService, useValue: apiSpy },
        { provide: I18N_LOCATION_SEARCH, useValue: () => currentSearch },
        { provide: I18N_LOCATION_PATHNAME, useValue: () => currentPathname },
      ],
    });

    const reloadedService = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);
    TestBed.flushEffects();

    expect(reloadedService.currentLocale()).toBe('en');
    expect(reloadedService.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
  });

  it('applies English and records explicit choice when guest opens /?lang=en', () => {
    currentPathname = '/';
    currentSearch = '?lang=en';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(localStorage.getItem('pp.locale')).toBe('en');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBe('en');
  });

  it('defaults to Arabic with rtl direction for a guest on /auth/sign-in with nothing stored', () => {
    currentPathname = '/auth/sign-in';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(service.isRtl()).toBeTrue();
    expect(dirService.currentDirection()).toBe('rtl');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBeNull();
  });

  it('defaults to Arabic for a guest on /auth/sign-in when a stale pp.locale=en exists without explicit choice', () => {
    localStorage.setItem('pp.locale', 'en');
    currentPathname = '/auth/sign-in';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('ar');
    expect(service.isRtl()).toBeTrue();
    expect(dirService.currentDirection()).toBe('rtl');
    expect(localStorage.getItem('pp.locale')).toBe('ar');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBeNull();
  });

  it('yields English for a guest on /auth/sign-in when pp.locale.chosen=en exists', () => {
    localStorage.setItem(LOCALE_CHOSEN_STORAGE_KEY, 'en');
    localStorage.setItem('pp.locale', 'en');
    currentPathname = '/auth/sign-in';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(localStorage.getItem('pp.locale')).toBe('en');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBe('en');
  });

  it('applies English and records explicit choice when guest opens /auth/sign-in?lang=en', () => {
    currentPathname = '/auth/sign-in';
    currentSearch = '?lang=en';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(localStorage.getItem('pp.locale')).toBe('en');
    expect(localStorage.getItem(LOCALE_CHOSEN_STORAGE_KEY)).toBe('en');
  });

  it('defaults to English with ltr direction for a guest on other routes (e.g. /onboarding/signup) with nothing stored', () => {
    currentPathname = '/onboarding/signup';
    const service = TestBed.inject(I18nService);
    const dirService = TestBed.inject(DirectionService);

    TestBed.flushEffects();

    expect(service.currentLocale()).toBe('en');
    expect(service.isRtl()).toBeFalse();
    expect(dirService.currentDirection()).toBe('ltr');
    expect(localStorage.getItem('pp.locale')).toBe('en');
  });
});
