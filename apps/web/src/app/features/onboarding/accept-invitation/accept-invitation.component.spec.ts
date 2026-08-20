import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Session } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { AcceptInvitationComponent } from './accept-invitation.component';

describe('AcceptInvitationComponent (T059)', () => {
  let component: AcceptInvitationComponent;
  let fixture: ComponentFixture<AcceptInvitationComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let sessionService: jasmine.SpyObj<SessionService>;
  let router: Router;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['acceptInvitation']);
    sessionService = jasmine.createSpyObj('SessionService', ['adopt']);

    await TestBed.configureTestingModule({
      imports: [AcceptInvitationComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: {
                get: (key: string) => (key === 'token' ? 'token_abc12345678901234567890' : null),
              },
            },
          },
        },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(AcceptInvitationComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize token from route query params', () => {
    expect(component.form.controls.token.value).toBe('token_abc12345678901234567890');
  });

  it('should require password in new account mode and omit in existing account mode', () => {
    expect(component.accountMode()).toBe('new');
    expect(component.form.controls.password.validator).not.toBeNull();

    component.onAccountModeChange('existing');
    expect(component.accountMode()).toBe('existing');
    expect(component.form.controls.password.validator).toBeNull();
  });

  it('should call api.acceptInvitation, adopt session and navigate on success', () => {
    const mockSession: Session = {
      access_token: 'acc_123',
      refresh_token: 'ref_123',
      expires_in: 3600,
      user: {
        id: 'u_123',
        email: 'colleague@example.com',
        role: 'buyer',
        preferred_locale: 'en',
        mfa_enabled: false,
        tenant: {
          id: 't_123',
          name: 'Acme',
          slug: 'acme',
          region: 'GB',
          currency: 'GBP',
          tax_model: 'uk_vat_standard',
          default_locale: 'en',
          created_at: '2026-08-20T10:00:00Z',
        },
      },
    };

    apiService.acceptInvitation.and.returnValue(of(mockSession));

    component.form.controls.password.setValue('SuperSecretPassword123!');
    component.onSubmit();

    expect(apiService.acceptInvitation).toHaveBeenCalledWith(
      'token_abc12345678901234567890',
      'SuperSecretPassword123!',
    );
    expect(sessionService.adopt).toHaveBeenCalledWith(mockSession);
    expect(router.navigate).toHaveBeenCalledWith(['/home']);
  });

  it('should display error alert when invitation is 403 (invalid, expired or revoked)', () => {
    const error403 = new HttpErrorResponse({
      status: 403,
      error: {
        code: 'invalid_invitation',
        message: 'Token expired',
        trace_id: 'tr_403',
      },
    });

    apiService.acceptInvitation.and.returnValue(throwError(() => error403));

    component.form.controls.password.setValue('SuperSecretPassword123!');
    component.onSubmit();

    expect(component.errorAlert()?.title).toContain('Invitation Refused');
    expect(component.errorAlert()?.traceId).toBe('tr_403');
  });
});
