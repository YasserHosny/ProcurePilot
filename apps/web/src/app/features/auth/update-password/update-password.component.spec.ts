import { HttpErrorResponse } from '@angular/common/http';
import { Location } from '@angular/common';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import { UpdatePasswordComponent } from './update-password.component';

describe('UpdatePasswordComponent (PP-28)', () => {
  let fixture: ComponentFixture<UpdatePasswordComponent>;
  let component: UpdatePasswordComponent;
  let api: jasmine.SpyObj<ApiService>;
  let location: jasmine.SpyObj<Location>;

  const RECOVERY_FRAGMENT =
    'access_token=recovery-access&expires_in=3600&refresh_token=recovery-refresh&token_type=bearer&type=recovery';

  async function setup(fragment: string | null): Promise<void> {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['updatePassword']);
    location = jasmine.createSpyObj<Location>('Location', ['replaceState']);

    await TestBed.configureTestingModule({
      imports: [UpdatePasswordComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ApiService, useValue: api },
        { provide: Location, useValue: location },
        { provide: ActivatedRoute, useValue: { snapshot: { fragment } } },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(UpdatePasswordComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  function fill(password: string, confirm = password): void {
    component.form.setValue({ password, confirm });
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('reads the recovery link and clears its tokens from the address bar', async () => {
    await setup(RECOVERY_FRAGMENT);

    expect(component.state()).toBe('form');
    expect(location.replaceState).toHaveBeenCalledWith('/auth/update-password');
  });

  it('shows the expired-link state when the link has no recovery session', async () => {
    await setup(null);

    expect(component.state()).toBe('invalid');
    expect(text()).toContain(enCatalog.auth.update.invalidTitle);
  });

  it('shows the expired-link state when Supabase reports an error in the link', async () => {
    await setup('error=access_denied&error_code=otp_expired&error_description=Email+link+expired');

    expect(component.state()).toBe('invalid');
  });

  it('does not submit when the passwords differ or are too short', async () => {
    await setup(RECOVERY_FRAGMENT);

    fill('a-new-long-password', 'something-else-long');
    component.onSubmit();
    fill('short');
    component.onSubmit();

    expect(api.updatePassword).not.toHaveBeenCalled();
  });

  it('sets the password with the recovery session and shows success', async () => {
    await setup(RECOVERY_FRAGMENT);
    api.updatePassword.and.returnValue(of(undefined));

    fill('a-new-long-password');
    component.onSubmit();
    fixture.detectChanges();

    expect(api.updatePassword).toHaveBeenCalledWith(
      'recovery-access',
      'recovery-refresh',
      'a-new-long-password',
    );
    expect(component.state()).toBe('done');
    expect(text()).toContain(enCatalog.auth.update.successTitle);
  });

  it('switches to the expired-link state when the API rejects the session', async () => {
    await setup(RECOVERY_FRAGMENT);
    api.updatePassword.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 401, error: { code: 'auth.unauthenticated' } })),
    );

    fill('a-new-long-password');
    component.onSubmit();

    expect(component.state()).toBe('invalid');
  });

  it('explains a password Supabase refuses as the same as before', async () => {
    await setup(RECOVERY_FRAGMENT);
    api.updatePassword.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 422,
            error: { code: 'validation.invalid_value', details: { reason: 'same_password' } },
          }),
      ),
    );

    fill('a-new-long-password');
    component.onSubmit();

    expect(component.state()).toBe('form');
    expect(component.errorMessage()).toBe(enCatalog.auth.update.samePasswordError);
  });
});
