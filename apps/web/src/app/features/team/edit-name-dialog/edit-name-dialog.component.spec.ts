import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { Member } from '../../../core/api/models';
import {
  EditNameDialogComponent,
  type EditNameDialogData,
} from './edit-name-dialog.component';

describe('EditNameDialogComponent (PPS-125)', () => {
  let component: EditNameDialogComponent;
  let fixture: ComponentFixture<EditNameDialogComponent>;
  let dialogRef: jasmine.SpyObj<MatDialogRef<EditNameDialogComponent>>;

  const mockMember: Member = {
    id: 'm1',
    email: 'member@example.com',
    role: 'buyer',
    status: 'active',
    mfa_enabled: false,
    created_at: '2026-08-20T10:00:00Z',
    display_name: 'Existing Name',
  };

  const dialogData: EditNameDialogData = {
    member: mockMember,
  };

  beforeEach(async () => {
    dialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [EditNameDialogComponent],
      providers: [
        provideNoopAnimations(),
        provideTranslateService(),
        { provide: MAT_DIALOG_DATA, useValue: dialogData },
        { provide: MatDialogRef, useValue: dialogRef },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(EditNameDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize and prefill display_name from member data', () => {
    expect(component.form.controls.display_name.value).toBe('Existing Name');
    expect(component.form.valid).toBeTrue();
  });

  it('should be invalid when display_name is empty or whitespace-only (blank name cannot be saved)', () => {
    component.form.controls.display_name.setValue('');
    expect(component.form.valid).toBeFalse();

    component.form.controls.display_name.setValue('    ');
    expect(component.form.valid).toBeFalse();

    // Verify onConfirm will not close the dialog when blank
    component.onConfirm();
    expect(dialogRef.close).not.toHaveBeenCalled();
  });

  it('should be invalid when display_name exceeds 100 characters', () => {
    component.form.controls.display_name.setValue('a'.repeat(101));
    expect(component.form.valid).toBeFalse();

    component.form.controls.display_name.setValue('a'.repeat(100));
    expect(component.form.valid).toBeTrue();
  });

  it('should trim display_name and close dialog with trimmed result on confirm', () => {
    component.form.controls.display_name.setValue('   Nadia Mansour   ');
    expect(component.form.valid).toBeTrue();

    component.onConfirm();
    expect(dialogRef.close).toHaveBeenCalledWith({ displayName: 'Nadia Mansour' });
  });

  it('should close dialog without result on cancel', () => {
    component.onCancel();
    expect(dialogRef.close).toHaveBeenCalledWith();
  });
});
