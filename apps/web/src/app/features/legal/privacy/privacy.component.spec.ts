import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n/i18n.service';
import { PrivacyComponent } from './privacy.component';

describe('PrivacyComponent', () => {
  let component: PrivacyComponent;
  let fixture: ComponentFixture<PrivacyComponent>;
  let translate: TranslateService;
  let i18nService: I18nService;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [PrivacyComponent],
      providers: [
        provideRouter([]),
        provideTranslateService(),
      ],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    i18nService = TestBed.inject(I18nService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(PrivacyComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('renders the header with brand logo linking to / and language toggle', () => {
    const brandLink = fixture.debugElement.query(By.css('.brand-link'));
    expect(brandLink).toBeTruthy();
    expect(
      brandLink.nativeElement.getAttribute('routerLink') ?? brandLink.nativeElement.getAttribute('href')
    ).toBe('/');

    const langToggle = fixture.debugElement.query(By.css('app-language-toggle'));
    expect(langToggle).toBeTruthy();
  });

  it('renders title, updated date, intro, and all 10 sections in English', () => {
    const title = fixture.debugElement.query(By.css('.legal-title'));
    expect(title).toBeTruthy();
    expect(title.nativeElement.textContent.trim()).toBe('Privacy Policy');

    const updated = fixture.debugElement.query(By.css('.legal-updated'));
    expect(updated).toBeTruthy();
    expect(updated.nativeElement.textContent.trim()).toBe(enCatalog.legal.updated);

    const intro = fixture.debugElement.query(By.css('.legal-intro'));
    expect(intro).toBeTruthy();
    expect(intro.nativeElement.textContent.trim()).toBe(enCatalog.legal.privacy.intro);

    const sections = fixture.debugElement.queryAll(By.css('.legal-section'));
    expect(sections.length).toBe(10);

    const headings = fixture.debugElement.queryAll(By.css('.section-heading'));
    expect(headings.length).toBe(10);
    expect(headings[0].nativeElement.textContent.trim()).toBe(enCatalog.legal.privacy.sections.s01.heading);
    expect(headings[9].nativeElement.textContent.trim()).toBe(enCatalog.legal.privacy.sections.s10.heading);

    const paragraphs = fixture.debugElement.queryAll(By.css('.section-paragraph'));
    expect(paragraphs.length).toBeGreaterThan(10);

    const backLinks = fixture.debugElement.queryAll(By.css('.back-link'));
    expect(backLinks.length).toBeGreaterThanOrEqual(1);
    for (const link of backLinks) {
      expect(
        link.nativeElement.getAttribute('routerLink') ?? link.nativeElement.getAttribute('href')
      ).toBe('/');
      expect(link.nativeElement.textContent).toContain('Back to ProcurePilot');
    }
  });

  it('switches to Arabic and renders Arabic title and sections', () => {
    i18nService.setLocale('ar');
    translate.use('ar');
    fixture.detectChanges();

    const title = fixture.debugElement.query(By.css('.legal-title'));
    expect(title.nativeElement.textContent.trim()).toBe('سياسة الخصوصية');

    const updated = fixture.debugElement.query(By.css('.legal-updated'));
    expect(updated.nativeElement.textContent.trim()).toBe(arCatalog.legal.updated);

    const headings = fixture.debugElement.queryAll(By.css('.section-heading'));
    expect(headings.length).toBe(10);
    expect(headings[0].nativeElement.textContent.trim()).toBe(arCatalog.legal.privacy.sections.s01.heading);
  });
});
