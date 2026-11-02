import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { SignupComponent } from './signup.component';

describe('SignupComponent', () => {
  let component: SignupComponent;
  let fixture: ComponentFixture<SignupComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let sessionStub: {
    adopt: jasmine.Spy;
    isAuthenticated: ReturnType<typeof signal<boolean>>;
    currentMember: ReturnType<typeof signal<null>>;
    role: ReturnType<typeof signal<null>>;
    tenant: ReturnType<typeof signal<null>>;
    activeLocale: ReturnType<typeof signal<string>>;
    hasRole: jasmine.Spy;
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['configOptions', 'signup']);
    apiService.configOptions.and.returnValue(
      of({
        regions: [{ code: 'EG', label_en: 'Egypt', label_ar: 'مصر' }],
        currencies: [{ code: 'EGP', label_en: 'Egyptian Pound', label_ar: 'جنيه مصري' }],
        tax_models: [{ code: 'standard', label_en: 'Standard', label_ar: 'قياسي' }],
      }),
    );
    sessionStub = {
      adopt: jasmine.createSpy('adopt'),
      isAuthenticated: signal(false),
      currentMember: signal(null),
      role: signal(null),
      tenant: signal(null),
      activeLocale: signal('en'),
      hasRole: jasmine.createSpy('hasRole').and.returnValue(false),
    };

    await TestBed.configureTestingModule({
      imports: [SignupComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionStub },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: {
                get: () => null,
              },
            },
          },
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(SignupComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('creates the signup component', () => {
    expect(component).toBeTruthy();
  });

  it('renders legal signup notice near submit button with terms and privacy links', () => {
    const notice = fixture.debugElement.query(By.css('.signup-legal-notice'));
    expect(notice).toBeTruthy();

    const termsLink = notice.query(By.css('a[routerLink="/terms"]'));
    expect(termsLink).toBeTruthy();
    expect(termsLink.nativeElement.getAttribute('target')).toBe('_blank');
    expect(termsLink.nativeElement.getAttribute('rel')).toContain('noopener');
    expect(termsLink.nativeElement.textContent.trim()).toBe('Terms of Service');

    const privacyLink = notice.query(By.css('a[routerLink="/privacy"]'));
    expect(privacyLink).toBeTruthy();
    expect(privacyLink.nativeElement.getAttribute('target')).toBe('_blank');
    expect(privacyLink.nativeElement.getAttribute('rel')).toContain('noopener');
    expect(privacyLink.nativeElement.textContent.trim()).toBe('Privacy Policy');
  });

  it('requires display_name and is invalid without it', () => {
    component.form.patchValue({
      invitation_token: 'valid-invitation-token-123456789012',
      business_name: 'Acme Corp',
      email: 'owner@example.com',
      password: 'password123456',
      region: 'EG',
      currency: 'EGP',
      tax_model: 'standard',
    });

    // display_name is empty by default
    expect(component.form.controls.display_name.valid).toBeFalse();
    expect(component.form.valid).toBeFalse();

    component.form.patchValue({ display_name: 'Alice Owner' });
    expect(component.form.controls.display_name.valid).toBeTrue();
    expect(component.form.valid).toBeTrue();
  });

  it('submits trimmed display_name in signup request body', () => {
    component.form.patchValue({
      invitation_token: 'valid-invitation-token-123456789012',
      business_name: 'Acme Corp',
      display_name: '  Alice Owner  ',
      email: 'owner@example.com',
      password: 'password123456',
      region: 'EG',
      currency: 'EGP',
      tax_model: 'standard',
    });

    apiService.signup.and.returnValue(
      of({
        access_token: 'access-1',
        refresh_token: 'refresh-1',
        expires_in: 3600,
        user: {
          id: 'u1',
          email: 'owner@example.com',
          role: 'owner',
          preferred_locale: 'en',
          mfa_enabled: false,
          tenant: {
            id: 't1',
            name: 'Acme Corp',
            slug: 'acme-corp',
            region: 'EG',
            currency: 'EGP',
            tax_model: 'standard',
            default_locale: 'en',
            created_at: '2026-08-20T10:00:00Z',
          },
          display_name: 'Alice Owner',
        },
      }),
    );

    component.onSubmit();

    expect(apiService.signup).toHaveBeenCalledWith(
      jasmine.objectContaining({
        display_name: 'Alice Owner',
      }),
    );
  });
});
