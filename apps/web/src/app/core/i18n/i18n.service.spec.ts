import { Directionality } from '@angular/cdk/bidi';
import { computed, DOCUMENT, signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Locale, Me, Tenant } from '../api/models';
import { SessionService } from '../auth/session.service';
import { DirectionService } from './direction.service';
import { I18nService } from './i18n.service';

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

  beforeEach(() => {
    localStorage.clear();
    fakeSession = new FakeSessionService();
    apiSpy = jasmine.createSpyObj<ApiService>('ApiService', ['updateMe']);
    apiSpy.updateMe.and.returnValue(of(mockMember));

    TestBed.configureTestingModule({
      providers: [
        provideTranslateService(),
        Directionality,
        DirectionService,
        I18nService,
        { provide: SessionService, useValue: fakeSession },
        { provide: ApiService, useValue: apiSpy },
      ],
    });
  });

  afterEach(() => {
    localStorage.clear();
    const doc = TestBed.inject(DOCUMENT);
    doc.documentElement.setAttribute('dir', 'ltr');
    doc.documentElement.setAttribute('lang', 'en');
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
});
