import { Clipboard } from '@angular/cdk/clipboard';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
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
    expect(secondaryBtn.nativeElement.textContent.trim()).toBe('See the product screens');
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

  it('rail renders 5 cards with numbered labels and captions', () => {
    const cards = fixture.debugElement.queryAll(By.css('.gallery-card'));
    expect(cards.length).toBe(5);
    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const numLabel = card.query(By.css('.gallery-card-numbered-label'));
      expect(numLabel).toBeTruthy();
      expect(numLabel.nativeElement.textContent).toContain(component.galleryCards[i].num);

      const caption = card.query(By.css('.gallery-caption-sentence'));
      expect(caption).toBeTruthy();
      expect(caption.nativeElement.textContent.trim().length).toBeGreaterThan(0);
    }
  });

  it('disables next/prev at ends', () => {
    const prevBtn = fixture.debugElement.query(By.css('.gallery-nav-btn.prev-btn'));
    const nextBtn = fixture.debugElement.query(By.css('.gallery-nav-btn.next-btn'));

    expect(component.activeCardIndex()).toBe(0);
    expect(prevBtn.nativeElement.disabled).toBeTrue();
    expect(nextBtn.nativeElement.disabled).toBeFalse();

    component.scrollToCard(4);
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(4);
    expect(prevBtn.nativeElement.disabled).toBeFalse();
    expect(nextBtn.nativeElement.disabled).toBeTrue();
  });

  it('step index marks the active card and clicking scrolls to it', () => {
    const stepBtns = fixture.debugElement.queryAll(By.css('.gallery-step-btn'));
    expect(stepBtns.length).toBe(5);

    expect(stepBtns[0].nativeElement.classList).toContain('active');
    expect(stepBtns[0].nativeElement.getAttribute('aria-current')).toBe('true');
    expect(stepBtns[1].nativeElement.classList).not.toContain('active');

    stepBtns[1].nativeElement.click();
    fixture.detectChanges();

    expect(component.activeCardIndex()).toBe(1);
    expect(stepBtns[1].nativeElement.classList).toContain('active');
    expect(stepBtns[1].nativeElement.getAttribute('aria-current')).toBe('true');
    expect(stepBtns[0].nativeElement.classList).not.toContain('active');
  });

  it('moves active card with ArrowRight/Left (mirrored when dir=rtl)', () => {
    const rail = fixture.debugElement.query(By.css('.gallery-rail'));

    expect(component.isRtl()).toBeFalse();
    expect(component.activeCardIndex()).toBe(0);

    rail.triggerEventHandler('keydown', { key: 'ArrowRight', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);

    rail.triggerEventHandler('keydown', { key: 'ArrowLeft', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    i18nService.setLocale('ar');
    translate.use('ar');
    fixture.detectChanges();

    expect(component.isRtl()).toBeTrue();
    component.scrollToCard(1);
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);

    // In RTL: ArrowRight moves prev (1 -> 0)
    rail.triggerEventHandler('keydown', { key: 'ArrowRight', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    // In RTL: ArrowLeft moves next (0 -> 1)
    rail.triggerEventHandler('keydown', { key: 'ArrowLeft', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);
  });

  it('switches hero image src between /landing/en/ and /landing/ar/ with the locale', () => {
    expect(component.currentLocale()).toBe('en');
    let heroImg = fixture.debugElement.query(By.css('.hero-preview-image'));
    expect(heroImg.nativeElement.getAttribute('src')).toBe('/landing/en/hero-recommendation.jpg');

    i18nService.setLocale('ar');
    translate.use('ar');
    fixture.detectChanges();

    expect(component.currentLocale()).toBe('ar');
    heroImg = fixture.debugElement.query(By.css('.hero-preview-image'));
    expect(heroImg.nativeElement.getAttribute('src')).toBe('/landing/ar/hero-recommendation.jpg');
  });

  it('enlarge opens the dialog at the right index and dialog prev/next change the image', () => {
    const cardEnlargeBtns = fixture.debugElement.queryAll(By.css('.gallery-enlarge-btn'));
    expect(cardEnlargeBtns.length).toBe(5);

    cardEnlargeBtns[1].triggerEventHandler('click', null);

    expect(dialogSpy.open).toHaveBeenCalledWith(
      ScreenshotDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          initialIndex: 1,
        }),
        restoreFocus: true,
      })
    );
  });

  it('copy-email uses Clipboard and announces "Copied"', fakeAsync(() => {
    const clipboard = TestBed.inject(Clipboard);
    const copySpy = spyOn(clipboard, 'copy').and.returnValue(true);

    const copyBtn = fixture.debugElement.query(By.css('.copy-email-btn'));
    expect(copyBtn).toBeTruthy();

    copyBtn.triggerEventHandler('click', null);
    fixture.detectChanges();

    expect(copySpy).toHaveBeenCalledWith(environment.supportEmail);
    expect(component.emailCopied()).toBeTrue();

    const liveRegion = fixture.debugElement.query(By.css('[aria-live="polite"]'));
    expect(liveRegion.nativeElement.textContent.trim()).toBe('Copied');
    expect(copyBtn.nativeElement.textContent).toContain('Copied');

    tick(2000);
    fixture.detectChanges();
    expect(component.emailCopied()).toBeFalse();
  }));

  it('evidence excerpt shows the four rows with the verified row marked', () => {
    const excerptRows = fixture.debugElement.queryAll(By.css('.excerpt-row'));
    expect(excerptRows.length).toBe(4);

    const verifiedRow = fixture.debugElement.query(By.css('.excerpt-row.verified-row'));
    expect(verifiedRow).toBeTruthy();

    const verifiedChip = verifiedRow.query(By.css('.excerpt-chip.verified'));
    expect(verifiedChip).toBeTruthy();
    expect(verifiedChip.nativeElement.textContent.trim()).toBe('Verified');
    expect(verifiedRow.nativeElement.textContent).toContain('560.00');
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
