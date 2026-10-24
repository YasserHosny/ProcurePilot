import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  QueryList,
  ViewChild,
  ViewChildren,
  inject,
  model,
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
    labelKey: 'landing.gallery.screen1Label',
    numberedLabelKey: 'landing.gallery.screen1Numbered',
    captionKey: 'landing.gallery.screen1Caption',
  },
  {
    id: 'smart-compare',
    file: '02-smart-compare.jpg',
    num: '02',
    labelKey: 'landing.gallery.screen2Label',
    numberedLabelKey: 'landing.gallery.screen2Numbered',
    captionKey: 'landing.gallery.screen2Caption',
  },
  {
    id: 'basket-split',
    file: '03-basket-split.jpg',
    num: '03',
    labelKey: 'landing.gallery.screen3Label',
    numberedLabelKey: 'landing.gallery.screen3Numbered',
    captionKey: 'landing.gallery.screen3Caption',
  },
  {
    id: 'approval-queue',
    file: '04-approval-queue.jpg',
    num: '04',
    labelKey: 'landing.gallery.screen4Label',
    numberedLabelKey: 'landing.gallery.screen4Numbered',
    captionKey: 'landing.gallery.screen4Caption',
  },
  {
    id: 'savings-ledger',
    file: '05-savings-ledger.jpg',
    num: '05',
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
export class LandingGalleryComponent implements AfterViewInit, OnDestroy {
  private readonly translate = inject(TranslateService);
  private readonly dialog = inject(MatDialog);
  readonly i18n = inject(I18nService);

  @ViewChild('railEl') railRef?: ElementRef<HTMLElement>;
  @ViewChildren('cardEl') cardElements?: QueryList<ElementRef<HTMLElement>>;

  readonly galleryCards = GALLERY_CARDS;
  readonly activeCardIndex = model<number>(0);
  readonly currentLocale = this.i18n.currentLocale;
  readonly isRtl = this.i18n.isRtl;

  private observer: IntersectionObserver | null = null;

  ngAfterViewInit(): void {
    if (typeof IntersectionObserver !== 'undefined' && this.railRef?.nativeElement) {
      this.observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
              const idxStr = entry.target.getAttribute('data-index');
              if (idxStr !== null) {
                const idx = parseInt(idxStr, 10);
                if (!isNaN(idx) && idx !== this.activeCardIndex()) {
                  this.activeCardIndex.set(idx);
                }
              }
            }
          }
        },
        {
          root: this.railRef.nativeElement,
          threshold: 0.6,
        }
      );

      this.cardElements?.forEach((el) => {
        this.observer?.observe(el.nativeElement);
      });
    }
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  scrollToCard(index: number): void {
    if (index < 0 || index >= this.galleryCards.length) {
      return;
    }
    this.activeCardIndex.set(index);
    const cardEl = this.cardElements?.get(index)?.nativeElement;
    if (cardEl) {
      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      cardEl.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        inline: 'start',
        block: 'nearest',
      });
    }
  }

  nextCard(): void {
    const nextIdx = Math.min(this.activeCardIndex() + 1, this.galleryCards.length - 1);
    this.scrollToCard(nextIdx);
  }

  prevCard(): void {
    const prevIdx = Math.max(this.activeCardIndex() - 1, 0);
    this.scrollToCard(prevIdx);
  }

  onRailKeydown(event: KeyboardEvent): void {
    const isRtl = this.isRtl();
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      if (isRtl) {
        this.prevCard();
      } else {
        this.nextCard();
      }
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      if (isRtl) {
        this.nextCard();
      } else {
        this.prevCard();
      }
    } else if (event.key === 'Home') {
      event.preventDefault();
      this.scrollToCard(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      this.scrollToCard(this.galleryCards.length - 1);
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

  getCardAriaLabel(index: number, card: GalleryCard): string {
    const label = this.translate.instant(card.labelKey);
    return this.translate.instant('landing.gallery.cardAriaLabel', {
      n: index + 1,
      label,
    });
  }
}
