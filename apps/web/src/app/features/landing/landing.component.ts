import { Clipboard } from '@angular/cdk/clipboard';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  QueryList,
  ViewChild,
  ViewChildren,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { environment } from '../../../environments/environment';
import { FormatMoneyPipe } from '../../core/format/money.pipe';
import { I18nService } from '../../core/i18n/i18n.service';
import { BrandLogoComponent } from '../../layout/brand-logo/brand-logo.component';
import { LanguageToggleComponent } from '../../layout/language-toggle/language-toggle.component';
import {
  ScreenshotDialogComponent,
  ScreenshotDialogItem,
} from './screenshot-dialog/screenshot-dialog.component';

export interface GalleryCard {
  readonly id: string;
  readonly file: string;
  readonly num: string;
  readonly labelKey: string;
  readonly numberedLabelKey: string;
  readonly captionKey: string;
}

export type GalleryTab = GalleryCard;

export interface FaqItem {
  readonly id: string;
  readonly qKey: string;
  readonly aKey: string;
}

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

export const FAQ_ITEMS: readonly FaqItem[] = [
  { id: 'q1', qKey: 'landing.pilot.q1', aKey: 'landing.pilot.a1' },
  { id: 'q2', qKey: 'landing.pilot.q2', aKey: 'landing.pilot.a2' },
  { id: 'q3', qKey: 'landing.pilot.q3', aKey: 'landing.pilot.a3' },
  { id: 'q4', qKey: 'landing.pilot.q4', aKey: 'landing.pilot.a4' },
];

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [
    BrandLogoComponent,
    LanguageToggleComponent,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatDialogModule,
    TranslatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent implements AfterViewInit, OnDestroy {
  private readonly translate = inject(TranslateService);
  private readonly dialog = inject(MatDialog);
  private readonly clipboard = inject(Clipboard);
  readonly i18n = inject(I18nService);

  @ViewChild('railEl') railRef?: ElementRef<HTMLElement>;
  @ViewChildren('cardEl') cardElements?: QueryList<ElementRef<HTMLElement>>;

  readonly supportEmail = environment.supportEmail;
  readonly supportMailto = `mailto:${environment.supportEmail}`;
  readonly currentLocale = this.i18n.currentLocale;
  readonly isRtl = this.i18n.isRtl;

  readonly activeCardIndex = signal(0);
  readonly emailCopied = signal(false);
  private copyTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private observer: IntersectionObserver | null = null;

  readonly galleryCards = GALLERY_CARDS;
  readonly galleryTabs = GALLERY_CARDS;
  readonly faqItems = FAQ_ITEMS;

  readonly demoLastQuoted = { amount: 2600.0, currency: 'EGP' };
  readonly demoPaid = { amount: 2040.0, currency: 'EGP' };
  readonly demoCalculated = { amount: 560.0, currency: 'EGP' };
  readonly demoVerified = { amount: 560.0, currency: 'EGP' };

  readonly mailtoLink = computed(() => {
    this.currentLocale();
    const subject = this.translate.instant('landing.pilot.emailSubject');
    const body = this.translate.instant('landing.pilot.emailBody');
    const queryParts: string[] = [];
    if (subject) {
      queryParts.push(`subject=${encodeURIComponent(subject)}`);
    }
    if (body) {
      queryParts.push(`body=${encodeURIComponent(body)}`);
    }
    const query = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
    return `mailto:${this.supportEmail}${query}`;
  });

  readonly heroImageSrc = computed(
    () => `/landing/${this.currentLocale()}/hero-recommendation.jpg`
  );
  readonly heroImageAlt = computed(() =>
    this.translate.instant('landing.hero.visualAlt')
  );

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
    if (this.copyTimeoutId) {
      clearTimeout(this.copyTimeoutId);
    }
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

  copyEmail(): void {
    this.clipboard.copy(this.supportEmail);
    this.emailCopied.set(true);
    if (this.copyTimeoutId) {
      clearTimeout(this.copyTimeoutId);
    }
    this.copyTimeoutId = setTimeout(() => {
      this.emailCopied.set(false);
    }, 2000);
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
