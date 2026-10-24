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

  it('renders 5 steps with numbered badges, labels, and captions', () => {
    const steps = fixture.debugElement.queryAll(By.css('.gallery-step'));
    expect(steps.length).toBe(5);

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const badge = step.query(By.css('.gallery-step-badge'));
      expect(badge).toBeTruthy();
      expect(badge.nativeElement.textContent.trim()).toBe(translate.instant(component.galleryCards[i].numKey));

      const label = step.query(By.css('.gallery-step-label'));
      expect(label).toBeTruthy();
      expect(label.nativeElement.textContent.trim()).toBe(translate.instant(component.galleryCards[i].labelKey));

      const caption = step.query(By.css('.gallery-step-caption'));
      expect(caption).toBeTruthy();
      expect(caption.nativeElement.textContent.trim()).toBe(translate.instant(component.galleryCards[i].captionKey));
    }
  });

  for (const locale of ['en', 'ar'] as const) {
    it(`renders a tablist with five localized tabs in ${locale}`, () => {
      i18nService.setLocale(locale);
      translate.use(locale);
      fixture.detectChanges();

      const tablist: HTMLElement = fixture.nativeElement.querySelector('ol.gallery-steps');
      expect(tablist).not.toBeNull();
      expect(tablist.getAttribute('role')).toBe('tablist');
      expect(tablist.getAttribute('aria-orientation')).toBe(component.ariaOrientation());

      const tabs = tablist.querySelectorAll('button.gallery-step-btn');
      expect(tabs.length).toBe(5);
      tabs.forEach((tab, index) => {
        expect(tab.getAttribute('role')).toBe('tab');
        expect(tab.getAttribute('id')).toBe(`gallery-tab-${index}`);
        expect(tab.getAttribute('aria-controls')).toBe('gallery-tabpanel');
        expect(tab.getAttribute('aria-selected')).toBe(index === 0 ? 'true' : 'false');
        expect(tab.getAttribute('tabindex')).toBe(index === 0 ? '0' : '-1');
      });

      const tabpanel: HTMLElement = fixture.nativeElement.querySelector('#gallery-tabpanel');
      expect(tabpanel).not.toBeNull();
      expect(tabpanel.getAttribute('role')).toBe('tabpanel');
      expect(tabpanel.getAttribute('aria-labelledby')).toBe('gallery-tab-0');

      const counter: HTMLElement = fixture.nativeElement.querySelector('.gallery-counter');
      expect(counter.textContent?.trim()).toBe(
        translate.instant('landing.gallery.counter', {
          n: translate.instant(component.galleryCards[0].numKey),
        })
      );
    });
  }

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

    const stepItems = fixture.debugElement.queryAll(By.css('.gallery-step'));
    expect(stepItems[0].nativeElement.classList).toContain('active');
    expect(stepBtns[0].nativeElement.getAttribute('aria-selected')).toBe('true');
    expect(stepBtns[1].nativeElement.getAttribute('aria-selected')).toBe('false');

    stepBtns[1].nativeElement.click();
    fixture.detectChanges();

    expect(component.activeCardIndex()).toBe(1);
    expect(stepItems[1].nativeElement.classList).toContain('active');
    expect(stepItems[0].nativeElement.classList).toContain('done');
    expect(stepBtns[1].nativeElement.getAttribute('aria-selected')).toBe('true');
    expect(stepBtns[0].nativeElement.getAttribute('aria-selected')).toBe('false');
  });

  it('moves active card with ArrowDown/Up and ArrowRight/Left (mirrored when dir=rtl)', () => {
    const getActiveBtn = () => fixture.debugElement.query(By.css('.gallery-step-btn[aria-selected="true"]'));

    expect(component.isRtl()).toBeFalse();
    expect(component.activeCardIndex()).toBe(0);

    // ArrowDown moves next
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowDown', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);

    // ArrowUp moves prev
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowUp', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    // ArrowRight moves next in LTR
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowRight', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);

    // ArrowLeft moves prev in LTR
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowLeft', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    // End jumps to last
    getActiveBtn().triggerEventHandler('keydown', { key: 'End', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(4);

    // Home jumps to first
    getActiveBtn().triggerEventHandler('keydown', { key: 'Home', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    // RTL switch
    i18nService.setLocale('ar');
    translate.use('ar');
    fixture.detectChanges();

    expect(component.isRtl()).toBeTrue();
    component.scrollToCard(1);
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);

    // In RTL: ArrowRight moves prev (1 -> 0)
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowRight', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(0);

    // In RTL: ArrowLeft moves next (0 -> 1)
    getActiveBtn().triggerEventHandler('keydown', { key: 'ArrowLeft', preventDefault: jasmine.createSpy() });
    fixture.detectChanges();
    expect(component.activeCardIndex()).toBe(1);
  });

  it('enlarge opens the dialog at the right index', () => {
    const enlargeBtn = fixture.debugElement.query(By.css('.gallery-enlarge-btn'));
    expect(enlargeBtn).toBeTruthy();

    component.scrollToCard(1);
    fixture.detectChanges();

    enlargeBtn.triggerEventHandler('click', { stopPropagation: jasmine.createSpy() });

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

  it('focusing the enlarge button and pressing Enter opens MatDialog exactly once', () => {
    const enlargeBtn = fixture.debugElement.query(By.css('.gallery-enlarge-btn'));
    expect(enlargeBtn).toBeTruthy();

    enlargeBtn.nativeElement.focus();

    // Pressing Enter on a focused button dispatches keydown (which bubbles to panel) and triggers click
    enlargeBtn.nativeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    enlargeBtn.nativeElement.click();
    fixture.detectChanges();

    expect(dialogSpy.open).toHaveBeenCalledTimes(1);
    expect(dialogSpy.open).toHaveBeenCalledWith(
      ScreenshotDialogComponent,
      jasmine.objectContaining({
        data: jasmine.objectContaining({
          initialIndex: 0,
        }),
        restoreFocus: true,
      })
    );
  });

  it('marks all list items with role="presentation" for tablist a11y', () => {
    const listItems = fixture.nativeElement.querySelectorAll('li.gallery-step');
    expect(listItems.length).toBe(5);
    listItems.forEach((li: HTMLElement) => {
      expect(li.getAttribute('role')).toBe('presentation');
    });
  });

  it('reflects layout orientation in aria-orientation attribute ("vertical" on desktop, "horizontal" on phone)', () => {
    const tablist: HTMLElement = fixture.nativeElement.querySelector('ol[role="tablist"]');

    component.isPhone.set(false);
    fixture.detectChanges();
    expect(tablist.getAttribute('aria-orientation')).toBe('vertical');

    component.isPhone.set(true);
    fixture.detectChanges();
    expect(tablist.getAttribute('aria-orientation')).toBe('horizontal');
  });

  it('updates aria-orientation via media query change listener and cleans up on destroy', () => {
    let changeHandler: ((e: MediaQueryListEvent) => void) | undefined;
    const mockMql = {
      matches: false,
      addEventListener: jasmine.createSpy('addEventListener').and.callFake((event: string, handler: (e: MediaQueryListEvent) => void) => {
        if (event === 'change') changeHandler = handler;
      }),
      removeEventListener: jasmine.createSpy('removeEventListener'),
    } as unknown as MediaQueryList;

    spyOn(window, 'matchMedia').and.returnValue(mockMql);

    const testFixture = TestBed.createComponent(LandingGalleryComponent);
    testFixture.detectChanges();
    const tablist: HTMLElement = testFixture.nativeElement.querySelector('ol[role="tablist"]');
    expect(tablist.getAttribute('aria-orientation')).toBe('vertical');
    expect(mockMql.addEventListener).toHaveBeenCalledWith('change', jasmine.any(Function));

    changeHandler?.({ matches: true } as MediaQueryListEvent);
    testFixture.detectChanges();
    expect(tablist.getAttribute('aria-orientation')).toBe('horizontal');

    testFixture.destroy();
    expect(mockMql.removeEventListener).toHaveBeenCalledWith('change', jasmine.any(Function));
  });
});
