import { TestBed } from '@angular/core/testing';
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
