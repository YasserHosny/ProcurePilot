import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TermsComponent } from './terms.component';

describe('TermsComponent', () => {
  let component: TermsComponent;
  let fixture: ComponentFixture<TermsComponent>;
  let translate: TranslateService;
  let i18nService: I18nService;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [TermsComponent],
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

    fixture = TestBed.createComponent(TermsComponent);
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

  it('renders title, updated date, intro, and all 11 sections in English', () => {
    const title = fixture.debugElement.query(By.css('.legal-title'));
    expect(title).toBeTruthy();
    expect(title.nativeElement.textContent.trim()).toBe('Terms of Service');

    const updated = fixture.debugElement.query(By.css('.legal-updated'));
    expect(updated).toBeTruthy();
    expect(updated.nativeElement.textContent.trim()).toBe(enCatalog.legal.updated);

    const intro = fixture.debugElement.query(By.css('.legal-intro'));
    expect(intro).toBeTruthy();
    expect(intro.nativeElement.textContent.trim()).toBe(enCatalog.legal.terms.intro);

    const sections = fixture.debugElement.queryAll(By.css('.legal-section'));
    expect(sections.length).toBe(11);

    const headings = fixture.debugElement.queryAll(By.css('.section-heading'));
    expect(headings.length).toBe(11);
    expect(headings[0].nativeElement.textContent.trim()).toBe(enCatalog.legal.terms.sections.s01.heading);
    expect(headings[10].nativeElement.textContent.trim()).toBe(enCatalog.legal.terms.sections.s11.heading);

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
    expect(title.nativeElement.textContent.trim()).toBe('شروط الخدمة');

    const updated = fixture.debugElement.query(By.css('.legal-updated'));
    expect(updated.nativeElement.textContent.trim()).toBe(arCatalog.legal.updated);

    const headings = fixture.debugElement.queryAll(By.css('.section-heading'));
    expect(headings.length).toBe(11);
    expect(headings[0].nativeElement.textContent.trim()).toBe(arCatalog.legal.terms.sections.s01.heading);
  });
});
