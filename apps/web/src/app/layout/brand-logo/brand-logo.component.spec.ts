import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../packages/i18n/en.json';
import { BrandLogoComponent } from './brand-logo.component';

describe('BrandLogoComponent', () => {
  let fixture: ComponentFixture<BrandLogoComponent>;
  let translate: TranslateService;

  const img = (): HTMLImageElement =>
    (fixture.nativeElement as HTMLElement).querySelector('img') as HTMLImageElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BrandLogoComponent],
      providers: [provideTranslateService()],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
    fixture = TestBed.createComponent(BrandLogoComponent);
  });

  it('shows the English horizontal lockup with its alt text from i18n', () => {
    fixture.detectChanges();

    expect(img().getAttribute('src')).toBe('assets/brand/procurepilot-horizontal.svg');
    expect(img().alt).toBe('ProcurePilot');
    expect(img().style.blockSize).toBe('28px');
  });

  it('swaps a rendered logo to the Arabic lockup and alt text when the language changes', () => {
    fixture.detectChanges();
    expect(img().getAttribute('src')).toBe('assets/brand/procurepilot-horizontal.svg');

    translate.use('ar');
    fixture.detectChanges();

    expect(img().getAttribute('src')).toBe('assets/brand/procurepilot-arabic-horizontal.svg');
    expect(img().alt).toBe('بروكيور بايلوت');
  });

  it('uses the mark alone below 24 px', () => {
    fixture.componentRef.setInput('height', 20);
    fixture.detectChanges();

    expect(img().getAttribute('src')).toBe('assets/brand/procurepilot-mark.svg');
  });

  describe('in a right-to-left page', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('dir');
    });

    it('is never mirrored', () => {
      // The global stylesheet (loaded by Karma) mirrors directional icons under [dir='rtl'];
      // the arrow in the mark means "forward", so the logo must stay as drawn.
      document.documentElement.dir = 'rtl';
      translate.use('ar');
      fixture.detectChanges();

      expect(getComputedStyle(img()).transform).toBe('none');
      expect(getComputedStyle(fixture.nativeElement as HTMLElement).transform).toBe('none');
    });
  });
});
