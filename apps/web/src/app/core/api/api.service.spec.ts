import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { ApiService } from './api.service';

describe('ApiService - Member display names (PPS-125)', () => {
  let service: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ApiService,
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('renameMember PATCHes /api/v1/members/{id} with display_name', () => {
    service.renameMember('mem-1', 'Nadia Mansour').subscribe();

    const req = http.expectOne('/api/v1/members/mem-1');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ display_name: 'Nadia Mansour' });
    req.flush({
      id: 'mem-1',
      email: 'nadia@example.com',
      role: 'buyer',
      status: 'active',
      mfa_enabled: false,
      created_at: '2026-08-20T10:00:00Z',
      display_name: 'Nadia Mansour',
    });
  });

  it('invite sends display_name when non-blank', () => {
    service.invite('bob@example.com', 'buyer', 'Bob Smith').subscribe();

    const req = http.expectOne('/api/v1/invitations');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      email: 'bob@example.com',
      role: 'buyer',
      display_name: 'Bob Smith',
    });
    req.flush({
      id: 'inv-1',
      email: 'bob@example.com',
      role: 'buyer',
      status: 'pending',
      expires_at: '2026-08-27T10:00:00Z',
      display_name: 'Bob Smith',
    });
  });

  it('invite omits display_name when blank or null', () => {
    service.invite('bob@example.com', 'buyer', '   ').subscribe();

    const req = http.expectOne('/api/v1/invitations');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      email: 'bob@example.com',
      role: 'buyer',
    });
    expect((req.request.body as Record<string, unknown>)['display_name']).toBeUndefined();
    req.flush({
      id: 'inv-2',
      email: 'bob@example.com',
      role: 'buyer',
      status: 'pending',
      expires_at: '2026-08-27T10:00:00Z',
    });
  });

  it('signup passes display_name when provided', () => {
    service
      .signup({
        invitation_token: 'valid-invitation-token-123456789012',
        business_name: 'Acme Corp',
        display_name: 'Alice Owner',
        email: 'alice@example.com',
        password: 'password123456',
        region: 'EG',
        currency: 'EGP',
        tax_model: 'standard',
      })
      .subscribe();

    const req = http.expectOne('/api/v1/auth/signup');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.display_name).toBe('Alice Owner');
    req.flush({});
  });
});
