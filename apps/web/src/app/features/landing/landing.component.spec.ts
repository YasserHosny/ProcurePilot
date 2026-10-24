import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../packages/i18n/en.json';
import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { LandingComponent } from './landing.component';
import { ScreenshotDialogComponent } from './screenshot-dialog/screenshot-dialog.component';

describe('LandingComponent', () => {
  let component: LandingComponent;
  let fixture: ComponentFixture<LandingComponent>;
  let translate: TranslateService;
  let i18nService: I18nService;
  let dialogSpy: jasmine.SpyObj<MatDialog>;

  beforeEach(async () => {
    localStorage.clear();
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({} as MatDialogRef<unknown, unknown>);

    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [
        provideRouter([]),
        provideTranslateService(),
      ],
    })
      .overrideComponent(LandingComponent, {
        set: {
          providers: [{ provide: MatDialog, useValue: dialogSpy }],
        },
      })
      .compileComponents();

    translate = TestBed.inject(TranslateService);
    i18nService = TestBed.inject(I18nService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(LandingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('establishes hero CTA hierarchy with request access as primary button and mailto with encoded subject', () => {
    const primaryBtn = fixture.debugElement.query(By.css('.hero-primary-btn'));
    expect(primaryBtn).toBeTruthy();
    expect(primaryBtn.nativeElement.textContent.trim()).toBe('Request pilot access');

    const href = primaryBtn.nativeElement.getAttribute('href');
    expect(href).toContain(`mailto:${environment.supportEmail}`);
    expect(href).toContain('subject=ProcurePilot%20pilot%20access%20request');

    const secondaryBtn = fixture.debugElement.query(By.css('.hero-secondary-btn'));
    expect(secondaryBtn).toBeTruthy();
    expect(secondaryBtn.nativeElement.textContent.trim()).toBe('Explore product screens');
    expect(secondaryBtn.nativeElement.getAttribute('href')).toBe('#gallery');
  });

  it('points all Iron Systems links to https://www.iron-sys.com/ with rel noopener', () => {
    const ironLinks = fixture.debugElement.queryAll(By.css('a[href="https://www.iron-sys.com/"]'));
    expect(ironLinks.length).toBeGreaterThanOrEqual(3);
    for (const link of ironLinks) {
      expect(link.nativeElement.getAttribute('rel')).toContain('noopener');
      expect(link.nativeElement.getAttribute('target')).toBe('_blank');
    }
  });

  it('renders five gallery tabs', () => {
    const tabs = fixture.debugElement.queryAll(By.css('.gallery-tab-group .mat-mdc-tab'));
    expect(tabs.length).toBe(5);
  });

  it('switches gallery and preview image src between /landing/en/ and /landing/ar/ with the locale', () => {
    expect(component.currentLocale()).toBe('en');
    let heroImg = fixture.debugElement.query(By.css('.hero-preview-image'));
    expect(heroImg.nativeElement.getAttribute('src')).toBe('/landing/en/02-smart-compare.jpg');

    let galleryImg = fixture.debugElement.query(By.css('.gallery-image'));
    expect(galleryImg.nativeElement.getAttribute('src')).toBe('/landing/en/01-quotation-review.jpg');

    i18nService.setLocale('ar');
    translate.use('ar');
    fixture.detectChanges();

    expect(component.currentLocale()).toBe('ar');
    heroImg = fixture.debugElement.query(By.css('.hero-preview-image'));
    expect(heroImg.nativeElement.getAttribute('src')).toBe('/landing/ar/02-smart-compare.jpg');

    galleryImg = fixture.debugElement.query(By.css('.gallery-image'));
    expect(galleryImg.nativeElement.getAttribute('src')).toBe('/landing/ar/01-quotation-review.jpg');
  });

  it('opens MatDialog when clicking enlarge screenshot button', () => {
    const enlargeBtn = fixture.debugElement.query(By.css('.enlarge-button'));
    expect(enlargeBtn).toBeTruthy();
    enlargeBtn.triggerEventHandler('click', null);

    expect(dialogSpy.open).toHaveBeenCalledWith(
      ScreenshotDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          src: '/landing/en/01-quotation-review.jpg',
        }),
        restoreFocus: true,
      })
    );
  });

  it('renders Q&A with 4 items using native details and summary', () => {
    const faqRows = fixture.debugElement.queryAll(By.css('.faq-row'));
    expect(faqRows.length).toBe(4);
    for (const row of faqRows) {
      expect(row.nativeElement.tagName.toLowerCase()).toBe('details');
      const summary = row.query(By.css('summary'));
      expect(summary).toBeTruthy();
      const answer = row.query(By.css('.faq-answer'));
      expect(answer).toBeTruthy();
    }
  });

  it('points the sign-in links to /auth/sign-in', () => {
    const headerSignIn = fixture.debugElement.query(By.css('.header-signin-btn'));
    expect(headerSignIn).toBeTruthy();
    expect(
      headerSignIn.nativeElement.getAttribute('routerLink') ??
        headerSignIn.nativeElement.getAttribute('href')
    ).toMatch(/\/auth\/sign-in/);

    const footerSignIn = fixture.debugElement.query(By.css('.footer-signin-link'));
    expect(footerSignIn).toBeTruthy();
    expect(
      footerSignIn.nativeElement.getAttribute('routerLink') ??
        footerSignIn.nativeElement.getAttribute('href')
    ).toMatch(/\/auth\/sign-in/);
  });

  it('renders the footer with support mailto, maker link, and copyright line', () => {
    const supportLink = fixture.debugElement.query(By.css('.footer-support-link'));
    expect(supportLink).toBeTruthy();
    expect(supportLink.nativeElement.getAttribute('href')).toBe(`mailto:${environment.supportEmail}`);
    expect(supportLink.nativeElement.textContent).toContain(environment.supportEmail);

    const copyright = fixture.debugElement.query(By.css('.footer-copyright'));
    expect(copyright).toBeTruthy();
    expect(copyright.nativeElement.textContent.trim()).toBe('© 2026 ProcurePilot. All rights reserved.');
  });
});
