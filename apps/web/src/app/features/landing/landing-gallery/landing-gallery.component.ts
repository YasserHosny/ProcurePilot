import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  afterRenderEffect,
  computed,
  effect,
  inject,
  model,
  signal,
  untracked,
  viewChild,
  viewChildren,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { I18nService } from '../../../core/i18n/i18n.service';
import {
  ScreenshotDialogComponent,
  ScreenshotDialogItem,
} from '../screenshot-dialog/screenshot-dialog.component';

export interface GalleryCard {
  readonly id: string;
  readonly file: string;
  readonly num: string;
  readonly numKey: string;
  readonly labelKey: string;
  readonly numberedLabelKey: string;
  readonly captionKey: string;
}

export type GalleryTab = GalleryCard;

export const GALLERY_CARDS: readonly GalleryCard[] = [
  {
    id: 'quotation-review',
    file: '01-quotation-review.jpg',
    num: '01',
    numKey: 'landing.gallery.screen1Num',
    labelKey: 'landing.gallery.screen1Label',
    numberedLabelKey: 'landing.gallery.screen1Numbered',
    captionKey: 'landing.gallery.screen1Caption',
  },
  {
    id: 'smart-compare',
    file: '02-smart-compare.jpg',
    num: '02',
    numKey: 'landing.gallery.screen2Num',
    labelKey: 'landing.gallery.screen2Label',
    numberedLabelKey: 'landing.gallery.screen2Numbered',
    captionKey: 'landing.gallery.screen2Caption',
  },
  {
    id: 'basket-split',
    file: '03-basket-split.jpg',
    num: '03',
    numKey: 'landing.gallery.screen3Num',
    labelKey: 'landing.gallery.screen3Label',
    numberedLabelKey: 'landing.gallery.screen3Numbered',
    captionKey: 'landing.gallery.screen3Caption',
  },
  {
    id: 'approval-queue',
    file: '04-approval-queue.jpg',
    num: '04',
    numKey: 'landing.gallery.screen4Num',
    labelKey: 'landing.gallery.screen4Label',
    numberedLabelKey: 'landing.gallery.screen4Numbered',
    captionKey: 'landing.gallery.screen4Caption',
  },
  {
    id: 'savings-ledger',
    file: '05-savings-ledger.jpg',
    num: '05',
    numKey: 'landing.gallery.screen5Num',
    labelKey: 'landing.gallery.screen5Label',
    numberedLabelKey: 'landing.gallery.screen5Numbered',
    captionKey: 'landing.gallery.screen5Caption',
  },
];

export const GALLERY_TABS = GALLERY_CARDS;

@Component({
  selector: 'app-landing-gallery',
  standalone: true,
  imports: [
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './landing-gallery.component.html',
  styleUrl: './landing-gallery.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingGalleryComponent implements OnDestroy {
  private readonly translate = inject(TranslateService);
  private readonly dialog = inject(MatDialog);
  readonly i18n = inject(I18nService);

  readonly galleryCards = GALLERY_CARDS;
  readonly activeCardIndex = model<number>(0);
  readonly outgoingCard = signal<GalleryCard | null>(null);
  readonly currentLocale = this.i18n.currentLocale;
  readonly isRtl = this.i18n.isRtl;
  readonly isPhone = signal<boolean>(false);
  readonly ariaOrientation = computed<'vertical' | 'horizontal'>(() =>
    this.isPhone() ? 'horizontal' : 'vertical'
  );

  private readonly stepList = viewChild<ElementRef<HTMLElement>>('stepListEl');
  private readonly stepElements = viewChildren<ElementRef<HTMLButtonElement>>('stepEl');

  private fadeTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private mediaQueryList: MediaQueryList | null = null;
  private mediaQueryListener: ((event: MediaQueryListEvent) => void) | null = null;

  constructor() {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      this.mediaQueryList = window.matchMedia('(max-width: 820px)');
      this.isPhone.set(Boolean(this.mediaQueryList?.matches));
      this.mediaQueryListener = (event: MediaQueryListEvent) => {
        this.isPhone.set(event.matches);
      };
      this.mediaQueryList.addEventListener?.('change', this.mediaQueryListener);
    }
    let previousFadeIndex: number | undefined;
    effect(() => {
      const index = this.activeCardIndex();
      const isInitial = previousFadeIndex === undefined;
      const changed = !isInitial && previousFadeIndex !== index;
      const oldIndex = previousFadeIndex;
      previousFadeIndex = index;

      if (!changed || oldIndex === undefined) return;

      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (this.fadeTimeoutId) {
        clearTimeout(this.fadeTimeoutId);
        this.fadeTimeoutId = null;
      }

      if (!prefersReducedMotion) {
        this.outgoingCard.set(this.galleryCards[oldIndex]);
        this.fadeTimeoutId = setTimeout(() => {
          this.outgoingCard.set(null);
          this.fadeTimeoutId = null;
        }, 360);
      } else {
        this.outgoingCard.set(null);
      }
    });

    let previousMobileScrollIndex: number | undefined;
    afterRenderEffect(() => {
      const index = this.activeCardIndex();
      const changed = previousMobileScrollIndex !== undefined && previousMobileScrollIndex !== index;
      previousMobileScrollIndex = index;
      if (!changed) return;

      // Only card changes scroll the nav on phone (max-width: 820px); first render,
      // locale changes, and view-query changes must not scroll. Never scrolls the window.
      // Compute from layout bounding boxes so offsetParent nesting cannot break alignment.
      untracked(() => {
        const nav = this.stepList()?.nativeElement;
        const activeStep = this.stepElements()[index]?.nativeElement;
        if (nav && activeStep && typeof window !== 'undefined' && window.matchMedia('(max-width: 820px)').matches) {
          const nb = nav.getBoundingClientRect();
          const ab = activeStep.getBoundingClientRect();
          const delta = this.isRtl() ? ab.right - nb.right : ab.left - nb.left;
          nav.scrollBy({ left: delta, behavior: 'instant' });
        }
      });
    });
  }

  ngOnDestroy(): void {
    if (this.fadeTimeoutId) {
      clearTimeout(this.fadeTimeoutId);
      this.fadeTimeoutId = null;
    }
    if (this.mediaQueryList && this.mediaQueryListener) {
      this.mediaQueryList.removeEventListener?.('change', this.mediaQueryListener);
      this.mediaQueryListener = null;
      this.mediaQueryList = null;
    }
  }

  scrollToCard(index: number): void {
    if (index < 0 || index >= this.galleryCards.length) {
      return;
    }
    this.activeCardIndex.set(index);
  }

  nextCard(): void {
    const nextIdx = Math.min(this.activeCardIndex() + 1, this.galleryCards.length - 1);
    this.scrollToCard(nextIdx);
  }

  prevCard(): void {
    const prevIdx = Math.max(this.activeCardIndex() - 1, 0);
    this.scrollToCard(prevIdx);
  }

  onStepsKeydown(event: KeyboardEvent): void {
    const currentIndex = this.activeCardIndex();
    const isRtl = this.isRtl();
    let targetIndex: number | null = null;

    if (event.key === 'ArrowDown') {
      targetIndex = Math.min(currentIndex + 1, this.galleryCards.length - 1);
    } else if (event.key === 'ArrowUp') {
      targetIndex = Math.max(currentIndex - 1, 0);
    } else if (event.key === 'ArrowRight') {
      targetIndex = isRtl
        ? Math.max(currentIndex - 1, 0)
        : Math.min(currentIndex + 1, this.galleryCards.length - 1);
    } else if (event.key === 'ArrowLeft') {
      targetIndex = isRtl
        ? Math.min(currentIndex + 1, this.galleryCards.length - 1)
        : Math.max(currentIndex - 1, 0);
    } else if (event.key === 'Home') {
      targetIndex = 0;
    } else if (event.key === 'End') {
      targetIndex = this.galleryCards.length - 1;
    }

    if (targetIndex !== null) {
      event.preventDefault();
      this.scrollToCard(targetIndex);
      this.stepElements()[targetIndex]?.nativeElement.focus();
    }
  }

  openEnlargeDialog(indexOrTab: number | GalleryCard): void {
    const index = typeof indexOrTab === 'number'
      ? indexOrTab
      : this.galleryCards.findIndex((c) => c.id === indexOrTab.id);
    const safeIndex = index >= 0 ? index : 0;

    const items: ScreenshotDialogItem[] = this.galleryCards.map((card) => {
      const caption = this.translate.instant(card.captionKey);
      const altPrefix = this.translate.instant('landing.gallery.altPrefix');
      return {
        id: card.id,
        src: `/landing/${this.currentLocale()}/${card.file}`,
        alt: `${altPrefix}${caption}`,
        caption,
      };
    });

    const activeItem = items[safeIndex];

    this.dialog.open(ScreenshotDialogComponent, {
      data: {
        items,
        initialIndex: safeIndex,
        src: activeItem.src,
        alt: activeItem.alt,
        caption: activeItem.caption,
      },
      restoreFocus: true,
      maxWidth: '95vw',
      panelClass: 'screenshot-dialog-panel',
    });
  }
}
