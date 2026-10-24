import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { BrandLogoComponent } from '../../layout/brand-logo/brand-logo.component';
import { LanguageToggleComponent } from '../../layout/language-toggle/language-toggle.component';
import { ScreenshotDialogComponent } from './screenshot-dialog/screenshot-dialog.component';

export interface GalleryTab {
  readonly id: string;
  readonly file: string;
  readonly labelKey: string;
  readonly captionKey: string;
}

export interface FaqItem {
  readonly id: string;
  readonly qKey: string;
  readonly aKey: string;
}

export const GALLERY_TABS: readonly GalleryTab[] = [
  {
    id: 'quotation-review',
    file: '01-quotation-review.jpg',
    labelKey: 'landing.gallery.tabQuotationReview',
    captionKey: 'landing.gallery.captionQuotationReview',
  },
  {
    id: 'smart-compare',
    file: '02-smart-compare.jpg',
    labelKey: 'landing.gallery.tabSmartCompare',
    captionKey: 'landing.gallery.captionSmartCompare',
  },
  {
    id: 'basket-split',
    file: '03-basket-split.jpg',
    labelKey: 'landing.gallery.tabBasketSplit',
    captionKey: 'landing.gallery.captionBasketSplit',
  },
  {
    id: 'approval-queue',
    file: '04-approval-queue.jpg',
    labelKey: 'landing.gallery.tabApprovalQueue',
    captionKey: 'landing.gallery.captionApprovalQueue',
  },
  {
    id: 'savings-ledger',
    file: '05-savings-ledger.jpg',
    labelKey: 'landing.gallery.tabSavingsLedger',
    captionKey: 'landing.gallery.captionSavingsLedger',
  },
];

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
    MatTabsModule,
    MatDialogModule,
    TranslatePipe,
  ],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {
  private readonly translate = inject(TranslateService);
  private readonly dialog = inject(MatDialog);
  readonly i18n = inject(I18nService);

  readonly supportEmail = environment.supportEmail;
  readonly supportMailto = `mailto:${environment.supportEmail}`;
  readonly currentLocale = this.i18n.currentLocale;
  readonly selectedTabIndex = signal(0);

  readonly galleryTabs = GALLERY_TABS;
  readonly faqItems = FAQ_ITEMS;

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

  readonly heroImageSrc = computed(() => `/landing/${this.currentLocale()}/02-smart-compare.jpg`);
  readonly heroImageAlt = computed(() => {
    const prefix = this.translate.instant('landing.gallery.altPrefix');
    const caption = this.translate.instant('landing.gallery.captionSmartCompare');
    return `${prefix}${caption}`;
  });

  openEnlargeDialog(tab: GalleryTab): void {
    const caption = this.translate.instant(tab.captionKey);
    const altPrefix = this.translate.instant('landing.gallery.altPrefix');
    this.dialog.open(ScreenshotDialogComponent, {
      data: {
        src: `/landing/${this.currentLocale()}/${tab.file}`,
        alt: `${altPrefix}${caption}`,
        caption,
      },
      restoreFocus: true,
      maxWidth: '95vw',
      panelClass: 'screenshot-dialog-panel',
    });
  }
}
