import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { By } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n/i18n.service';
import { ScreenshotDialogComponent } from '../screenshot-dialog/screenshot-dialog.component';
import { LandingGalleryComponent } from './landing-gallery.component';

describe('LandingGalleryComponent', () => {
  let component: LandingGalleryComponent;
  let fixture: ComponentFixture<LandingGalleryComponent>;
  let translate: TranslateService;
  let i18nService: I18nService;
  let dialogSpy: jasmine.SpyObj<MatDialog>;

  beforeEach(async () => {
    localStorage.clear();
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({} as MatDialogRef<unknown, unknown>);

    await TestBed.configureTestingModule({
      imports: [LandingGalleryComponent],
      providers: [provideTranslateService()],
    })
      .overrideComponent(LandingGalleryComponent, {
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

    fixture = TestBed.createComponent(LandingGalleryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  for (const initialIndex of [0, 2]) {
    it(`does not scroll on first mobile render with initial index ${initialIndex}`, async () => {
      fixture.destroy();
      spyOn(window, 'matchMedia').and.returnValue({ matches: true } as MediaQueryList);
      const navScrollTo = spyOn(Element.prototype, 'scrollTo');
      const windowScrollTo = spyOn(window, 'scrollTo');
      const scrollIntoView = spyOn(Element.prototype, 'scrollIntoView');

      fixture = TestBed.createComponent(LandingGalleryComponent);
      fixture.componentRef.setInput('activeCardIndex', initialIndex);
      fixture.detectChanges();
      await fixture.whenStable();

      expect(navScrollTo).not.toHaveBeenCalled();
      expect(windowScrollTo).not.toHaveBeenCalled();
      expect(scrollIntoView).not.toHaveBeenCalled();
    });
  }

  it('does not scroll the nav or window when locale changes on mobile', async () => {
    spyOn(window, 'matchMedia').and.returnValue({ matches: true } as MediaQueryList);
    const nav: HTMLElement = fixture.nativeElement.querySelector('.gallery-step-index');
    const navScrollTo = spyOn(nav, 'scrollTo');
    const windowScrollTo = spyOn(window, 'scrollTo');
    const scrollIntoView = spyOn(Element.prototype, 'scrollIntoView');

    i18nService.setLocale('ar');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(navScrollTo).not.toHaveBeenCalled();

    // An actual index change scrolls only the nav, then a locale change must leave it alone.
    component.activeCardIndex.set(1);
    fixture.detectChanges();
    await fixture.whenStable();
    expect(navScrollTo).toHaveBeenCalledTimes(1);
    navScrollTo.calls.reset();

    i18nService.setLocale('en');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(navScrollTo).not.toHaveBeenCalled();
    expect(windowScrollTo).not.toHaveBeenCalled();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  for (const locale of ['en', 'ar'] as const) {
    it(`scrolls only the mobile step nav using ${locale} offsets when the index changes`, async () => {
      spyOn(window, 'matchMedia').and.returnValue({ matches: true } as MediaQueryList);
      i18nService.setLocale(locale);
      fixture.detectChanges();
      await fixture.whenStable();

      const nav: HTMLElement = fixture.nativeElement.querySelector('.gallery-step-index');
      const step: HTMLElement = fixture.nativeElement.querySelectorAll('.gallery-step-btn')[1];
      spyOnProperty(nav, 'clientWidth', 'get').and.returnValue(320);
      spyOnProperty(step, 'offsetLeft', 'get').and.returnValue(locale === 'ar' ? -100 : 240);
      spyOnProperty(step, 'offsetWidth', 'get').and.returnValue(80);
      const navScrollTo: jasmine.Spy<(options: ScrollToOptions) => void> = spyOn(nav, 'scrollTo');
      const windowScrollTo = spyOn(window, 'scrollTo');
      const scrollIntoView = spyOn(Element.prototype, 'scrollIntoView');

      component.activeCardIndex.set(1);
      fixture.detectChanges();
      await fixture.whenStable();
      expect(navScrollTo).toHaveBeenCalledOnceWith({
        left: locale === 'ar' ? -340 : 240,
        behavior: 'instant',
      });

      component.activeCardIndex.set(1);
      fixture.detectChanges();
      await fixture.whenStable();
      expect(navScrollTo).toHaveBeenCalledTimes(1);
      expect(windowScrollTo).not.toHaveBeenCalled();
      expect(scrollIntoView).not.toHaveBeenCalled();
    });
  }

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
});
