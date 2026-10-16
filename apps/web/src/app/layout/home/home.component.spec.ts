import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import arCatalog from '../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../packages/i18n/en.json';
import { ApiService } from '../../core/api/api.service';
import type { ConfigOptions, Locale, Me, Role, Tenant } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { I18nService } from '../../core/i18n';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  let fixture: ComponentFixture<HomeComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let localeSignal: ReturnType<typeof signal<Locale>>;
  let tenantSignal: ReturnType<typeof signal<Tenant | null>>;
  let roleSignal: ReturnType<typeof signal<Role | null>>;

  const mockConfigOptions: ConfigOptions = {
    regions: [
      { code: 'eg_cairo', label_en: 'Egypt (Cairo)', label_ar: 'مصر (القاهرة)' },
      { code: 'sa_riyadh', label_en: 'Saudi Arabia (Riyadh)', label_ar: 'السعودية (الرياض)' },
    ],
    currencies: [{ code: 'EGP', label_en: 'Egyptian Pound (EGP)', label_ar: 'جنيه مصري (EGP)' }],
    tax_models: [
      {
        code: 'eg_vat_standard',
        label_en: 'Egypt VAT Standard (14%)',
        label_ar: 'ضريبة القيمة المضافة المصرية (14%)',
      },
    ],
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', ['configOptions']);
    apiService.configOptions.and.returnValue(of(mockConfigOptions));

    localeSignal = signal<Locale>('en');
    roleSignal = signal<Role | null>('owner');
    const initialTenant: Tenant = {
      id: 'tenant-123',
      name: 'Acme Hospitality',
      slug: 'acme-hospitality',
      region: 'eg_cairo',
      currency: 'EGP',
      tax_model: 'eg_vat_standard',
      default_locale: 'en',
      created_at: '2026-01-01T00:00:00Z',
    };
    tenantSignal = signal<Tenant | null>(initialTenant);

    const mockMemberSignal = signal<Me | null>({
      id: 'member-1',
      email: 'owner@acme.example',
      role: 'owner',
      mfa_enabled: true,
      preferred_locale: 'en',
      tenant: initialTenant,
    });

    const mockSession = {
      role: roleSignal,
      currentMember: mockMemberSignal,
      tenant: tenantSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = roleSignal();
        return current !== null && roles.includes(current);
      },
    };

    const mockI18n = {
      currentLocale: localeSignal,
    };

    await TestBed.configureTestingModule({
      imports: [HomeComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        { provide: I18nService, useValue: mockI18n },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
  });

  it('renders no "Chunk" or "المرحلة 4" text in English or Arabic', () => {
    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();

    const enText = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(enText).not.toMatch(/chunk|المرحلة\s*4/i);

    const translate = TestBed.inject(TranslateService);
    translate.use('ar');
    localeSignal.set('ar');
    fixture.detectChanges();

    const arText = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(arText).not.toMatch(/chunk|المرحلة\s*4/i);
  });

  it('renders module links with expected hrefs', () => {
    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();

    const links = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLAnchorElement>('.module-card'),
    );
    const hrefs = links.map((a) => a.getAttribute('href'));

    expect(hrefs).toEqual([
      '/quotations',
      '/rfq/history',
      '/offers/compare',
      '/requests',
      '/approvals',
      '/orders',
      '/savings',
      '/analyst',
      '/products',
      '/suppliers',
    ]);
  });

  it('displays localized region and tax model labels and falls back to code on unknown or error', () => {
    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const regionEl = el.querySelector('[data-testid="home-region-value"]');
    const taxEl = el.querySelector('[data-testid="home-tax-model-value"]');

    expect(regionEl?.textContent?.trim()).toBe('Egypt (Cairo)');
    expect(taxEl?.textContent?.trim()).toBe('Egypt VAT Standard (14%)');

    localeSignal.set('ar');
    fixture.detectChanges();

    expect(regionEl?.textContent?.trim()).toBe('مصر (القاهرة)');
    expect(taxEl?.textContent?.trim()).toBe('ضريبة القيمة المضافة المصرية (14%)');

    // Unknown codes fall back to raw code
    tenantSignal.set({
      id: 'tenant-123',
      name: 'Acme Hospitality',
      slug: 'acme-hospitality',
      region: 'unknown_region',
      currency: 'EGP',
      tax_model: 'custom_tax_code',
      default_locale: 'en',
      created_at: '2026-01-01T00:00:00Z',
    });
    fixture.detectChanges();

    expect(regionEl?.textContent?.trim()).toBe('unknown_region');
    expect(taxEl?.textContent?.trim()).toBe('custom_tax_code');
  });

  it('falls back to raw region and tax_model codes when configOptions call fails', () => {
    apiService.configOptions.and.returnValue(throwError(() => new Error('Network error')));

    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const regionEl = el.querySelector('[data-testid="home-region-value"]');
    const taxEl = el.querySelector('[data-testid="home-tax-model-value"]');

    expect(regionEl?.textContent?.trim()).toBe('eg_cairo');
    expect(taxEl?.textContent?.trim()).toBe('eg_vat_standard');
  });
});
