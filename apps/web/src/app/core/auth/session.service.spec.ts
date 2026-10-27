import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiService } from '../api/api.service';
import { SessionService } from './session.service';
import type { Session } from '../api/models';

describe('SessionService home currency', () => {
  let service: SessionService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: {} }] });
    service = TestBed.inject(SessionService);
  });

  it('is undefined until a tenant is loaded', () => {
    expect(service.homeCurrency()).toBeUndefined();
  });

  it('reads the existing tenant currency from the adopted session', () => {
    const session = {
      access_token: 'token', refresh_token: 'refresh', expires_in: 3600, token_type: 'bearer',
      user: {
        id: 'member', email: 'owner@example.com', role: 'owner', preferred_locale: null, mfa_enabled: false,
        tenant: { id: 'tenant', name: 'Pilot', slug: 'pilot', region: 'EG', currency: 'EGP', tax_model: 'standard', default_locale: 'en', created_at: '' },
      },
    } as Session;
    service.adopt(session);
    expect(service.homeCurrency()).toBe('EGP');
  });
});

describe('SessionService signedInInteractively', () => {
  let service: SessionService;
  let apiSpy: jasmine.SpyObj<ApiService>;

  const mockSession = {
    access_token: 'token',
    refresh_token: 'refresh',
    expires_in: 3600,
    token_type: 'bearer',
    user: {
      id: 'member',
      email: 'owner@example.com',
      role: 'owner',
      preferred_locale: null,
      mfa_enabled: false,
      tenant: {
        id: 'tenant',
        name: 'Pilot',
        slug: 'pilot',
        region: 'EG',
        currency: 'EGP',
        tax_model: 'standard',
        default_locale: 'en',
        created_at: '',
      },
    },
  } as Session;

  beforeEach(() => {
    apiSpy = jasmine.createSpyObj<ApiService>('ApiService', ['login', 'me']);
    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: apiSpy }] });
    service = TestBed.inject(SessionService);
  });

  it('starts false when unauthenticated', () => {
    expect(service.signedInInteractively()).toBeFalse();
  });

  it('sets signedInInteractively true on login', () => {
    apiSpy.login.and.returnValue(of(mockSession));
    service.login('test@example.com', 'password').subscribe();
    expect(service.signedInInteractively()).toBeTrue();
  });

  it('sets signedInInteractively false on restore', () => {
    apiSpy.me.and.returnValue(of(mockSession.user));
    service.adopt(mockSession, true);
    expect(service.signedInInteractively()).toBeTrue();

    service.restore().subscribe();
    expect(service.signedInInteractively()).toBeFalse();
  });

  it('sets signedInInteractively false on logout', () => {
    service.adopt(mockSession, true);
    expect(service.signedInInteractively()).toBeTrue();

    service.logout();
    expect(service.signedInInteractively()).toBeFalse();
  });

  it('defaults to false when adopt is called without interactive flag', () => {
    service.adopt(mockSession);
    expect(service.signedInInteractively()).toBeFalse();
  });
});
