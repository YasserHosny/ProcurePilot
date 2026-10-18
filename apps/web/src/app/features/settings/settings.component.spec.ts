import { CUSTOM_ELEMENTS_SCHEMA, signal } from '@angular/core';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { TranslateModule, TranslatePipe, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { ApiService } from '../../core/api/api.service';
import type { Role, Tenant } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n/i18n.service';
import { SettingsComponent } from './settings.component';

const tenant: Tenant = {
  id: 't1',
  name: 'Sanad',
  slug: 'sanad',
  region: 'EG',
  currency: 'EGP',
  tax_model: 'eg_vat',
  default_locale: 'en',
  created_at: '2026-10-01T00:00:00Z',
};

describe('SettingsComponent workspace language (finding 37)', () => {
  let fixture: ComponentFixture<SettingsComponent>;
  let component: SettingsComponent;
  let api: jasmine.SpyObj<ApiService>;
  const currentTenant = signal<Tenant | null>(tenant);
  const role = signal<Role>('owner');
  let session: {
    tenant: typeof currentTenant;
    homeCurrency: () => string;
    hasRole: (r: Role) => boolean;
    updateTenant: jasmine.Spy;
  };

  async function create(): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [SettingsComponent, TranslateModule.forRoot(), NoopAnimationsModule],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: session },
        { provide: I18nService, useValue: { currentLocale: () => 'en' } },
      ],
    })
      // The organisation sections (branches, cost centres, ...) have their own specs.
      .overrideComponent(SettingsComponent, {
        set: {
          imports: [MatFormFieldModule, MatSelectModule, MatButtonModule, TranslatePipe],
          schemas: [CUSTOM_ELEMENTS_SCHEMA],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(SettingsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  beforeEach(() => {
    currentTenant.set(tenant);
    role.set('owner');
    api = jasmine.createSpyObj('ApiService', ['configOptions', 'updateTenant']);
    api.configOptions.and.returnValue(of({ regions: [], currencies: [], tax_models: [] }));
    api.updateTenant.and.returnValue(of({ ...tenant, default_locale: 'ar' }));
    session = {
      tenant: currentTenant,
      homeCurrency: () => 'EGP',
      hasRole: (r: Role) => r === role(),
      updateTenant: jasmine.createSpy('updateTenant').and.callFake((next: Tenant) => currentTenant.set(next)),
    };
  });

  it('starts from the workspace language and only saves a change', async () => {
    await create();
    const save = (): HTMLButtonElement =>
      fixture.nativeElement.querySelector('[data-testid="workspace-language-save"]');
    expect(component.selectedLocale()).toBe('en');
    expect(save().disabled).toBeTrue();

    component.selectedLocale.set('ar');
    fixture.detectChanges();
    expect(save().disabled).toBeFalse();
    save().click();

    expect(api.updateTenant).toHaveBeenCalledOnceWith({ default_locale: 'ar' });
    expect(session.updateTenant).toHaveBeenCalledWith({ ...tenant, default_locale: 'ar' });
    expect(component.workspaceLocale()).toBe('ar');
  });

  it('explains what the language is used for', async () => {
    await create();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Workspace language');
    expect(text).toContain('RFQ emails to suppliers');
  });

  it('shows an error and keeps the old language when saving fails', async () => {
    api.updateTenant.and.returnValue(throwError(() => new Error('boom')));
    await create();
    component.selectedLocale.set('ar');
    component.saveLocale();
    fixture.detectChanges();

    expect(component.localeError()).toBeTrue();
    expect(session.updateTenant).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('The workspace language could not be saved');
  });

  it('shows non-owners the language read-only and never saves', async () => {
    role.set('buyer');
    await create();
    expect(fixture.nativeElement.querySelector('[data-testid="workspace-language-select"]')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Workspace language: English');

    component.selectedLocale.set('ar');
    component.saveLocale();
    expect(api.updateTenant).not.toHaveBeenCalled();
  });
});
