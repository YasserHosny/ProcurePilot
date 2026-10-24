import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService } from '@ngx-translate/core';

import { I18nService } from '../../../core/i18n/i18n.service';
import {
  ScreenshotDialogComponent,
  ScreenshotDialogData,
  ScreenshotDialogItem,
} from './screenshot-dialog.component';

describe('ScreenshotDialogComponent', () => {
  let component: ScreenshotDialogComponent;
  let fixture: ComponentFixture<ScreenshotDialogComponent>;
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<ScreenshotDialogComponent>>;

  const mockData = {
    src: '/landing/en/01-quotation-review.jpg',
    alt: 'Demonstration screen: Quotation review',
    caption: 'Check extracted details beside the source document.',
  };

  const multiItems: ScreenshotDialogItem[] = [
    {
      id: '01',
      src: '/landing/en/01-quotation-review.jpg',
      alt: 'Demonstration screen: Quotation review',
      caption: 'Quotation review caption',
    },
    {
      id: '02',
      src: '/landing/en/02-smart-compare.jpg',
      alt: 'Demonstration screen: Smart Compare',
      caption: 'Smart Compare caption',
    },
    {
      id: '03',
      src: '/landing/en/03-basket-split.jpg',
      alt: 'Demonstration screen: Basket split',
      caption: 'Basket split caption',
    },
  ];

  async function createComponent(data: ScreenshotDialogData) {
    dialogRefSpy = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [ScreenshotDialogComponent],
      providers: [
        provideTranslateService(),
        { provide: MAT_DIALOG_DATA, useValue: data },
        { provide: MatDialogRef, useValue: dialogRefSpy },
        I18nService,
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ScreenshotDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  describe('with single item (backward compatibility)', () => {
    beforeEach(async () => {
      await createComponent(mockData);
    });

    it('creates the dialog', () => {
      expect(component).toBeTruthy();
    });

    it('renders image with provided src and alt', () => {
      const img: HTMLImageElement = fixture.nativeElement.querySelector('.dialog-image');
      expect(img).toBeTruthy();
      expect(img.getAttribute('src')).toBe(mockData.src);
      expect(img.alt).toBe(mockData.alt);
    });

    it('renders caption text', () => {
      const captionEl = fixture.nativeElement.querySelector('.dialog-caption');
      expect(captionEl.textContent.trim()).toBe(mockData.caption);
    });

    it('closes the dialog when close button is clicked', () => {
      const closeBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.dialog-close-btn');
      closeBtn.click();
      expect(dialogRefSpy.close).toHaveBeenCalled();
    });
  });

  describe('with multiple items (lightbox mode)', () => {
    beforeEach(async () => {
      await createComponent({
        items: multiItems,
        initialIndex: 1,
      });
    });

    it('initializes at the requested initialIndex', () => {
      expect(component.currentIndex()).toBe(1);
      const img: HTMLImageElement = fixture.nativeElement.querySelector('.dialog-image');
      expect(img.getAttribute('src')).toBe(multiItems[1].src);
      const captionEl = fixture.nativeElement.querySelector('.dialog-caption');
      expect(captionEl.textContent.trim()).toBe(multiItems[1].caption);
    });

    it('moves to next and previous items via buttons', () => {
      const nextBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.next-btn');
      const prevBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.prev-btn');

      // Click next -> index 2
      nextBtn.click();
      fixture.detectChanges();
      expect(component.currentIndex()).toBe(2);
      let img: HTMLImageElement = fixture.nativeElement.querySelector('.dialog-image');
      expect(img.getAttribute('src')).toBe(multiItems[2].src);
      expect(nextBtn.getAttribute('aria-disabled')).toBe('true');

      // Click prev -> index 1
      prevBtn.click();
      fixture.detectChanges();
      expect(component.currentIndex()).toBe(1);

      // Click prev -> index 0
      prevBtn.click();
      fixture.detectChanges();
      expect(component.currentIndex()).toBe(0);
      img = fixture.nativeElement.querySelector('.dialog-image');
      expect(img.getAttribute('src')).toBe(multiItems[0].src);
      expect(prevBtn.getAttribute('aria-disabled')).toBe('true');
    });

    for (const direction of ['next', 'prev'] as const) {
      it(`keeps ${direction} focusable and focused at the end without moving out of range`, () => {
        const button: HTMLButtonElement = fixture.nativeElement.querySelector(`.${direction}-btn`);
        button.focus();
        expect(document.activeElement).toBe(button);

        button.click();
        fixture.detectChanges();

        const endIndex = direction === 'next' ? multiItems.length - 1 : 0;
        expect(component.currentIndex()).toBe(endIndex);
        expect(button.getAttribute('aria-disabled')).toBe('true');
        expect(button.disabled).toBeFalse();
        expect(button.tabIndex).toBeGreaterThanOrEqual(0);
        expect(document.activeElement).toBe(button);

        button.blur();
        button.focus();
        expect(document.activeElement).toBe(button);
        button.click();
        fixture.detectChanges();
        expect(component.currentIndex()).toBe(endIndex);
      });
    }

    it('supports ArrowRight and ArrowLeft keyboard navigation', () => {
      const eventRight = new KeyboardEvent('keydown', { key: 'ArrowRight' });
      component.handleKeyDown(eventRight);
      fixture.detectChanges();
      expect(component.currentIndex()).toBe(2);

      const eventLeft = new KeyboardEvent('keydown', { key: 'ArrowLeft' });
      component.handleKeyDown(eventLeft);
      fixture.detectChanges();
      expect(component.currentIndex()).toBe(1);
    });
  });
});
