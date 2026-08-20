import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Invitation } from '../../../core/api/models';
import { InviteDialogComponent } from './invite-dialog.component';

describe('InviteDialogComponent (T058)', () => {
  let component: InviteDialogComponent;
  let fixture: ComponentFixture<InviteDialogComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let dialogRef: jasmine.SpyObj<MatDialogRef<InviteDialogComponent, boolean>>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['invite']);
    dialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [InviteDialogComponent, TranslateModule.forRoot()],
      providers: [
        { provide: ApiService, useValue: apiService },
        { provide: MatDialogRef, useValue: dialogRef },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(InviteDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should validate email and role', () => {
    expect(component.form.valid).toBeFalse();

    component.form.controls.email.setValue('invalid-email');
    expect(component.form.valid).toBeFalse();

    component.form.controls.email.setValue('valid@example.com');
    expect(component.form.valid).toBeTrue();
  });

  it('should call api.invite and display created token on success', () => {
    const mockInvitation = {
      id: 'inv_123',
      email: 'newbie@example.com',
      role: 'buyer',
      status: 'pending',
      expires_at: '2026-08-27T10:00:00Z',
      token: 'tok_12345678901234567890123456789012',
    } as Invitation & { token: string };

    apiService.invite.and.returnValue(of(mockInvitation));

    component.form.controls.email.setValue('newbie@example.com');
    component.form.controls.role.setValue('buyer');
    component.onSubmit();

    expect(apiService.invite).toHaveBeenCalledWith('newbie@example.com', 'buyer');
    expect(component.createdResult()?.token).toBe('tok_12345678901234567890123456789012');
    expect(component.createdResult()?.inviteUrl).toContain('/onboarding/accept-invitation?token=');
  });

  it('should handle 409 conflict error when email is already invited', () => {
    const error409 = new HttpErrorResponse({
      status: 409,
      error: { code: 'already_invited', message: 'Already pending' },
    });
    apiService.invite.and.returnValue(throwError(() => error409));

    component.form.controls.email.setValue('existing@example.com');
    component.onSubmit();

    expect(component.errorMessage()).toContain('already pending');
  });
});
