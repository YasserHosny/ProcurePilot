import {
  ChangeDetectionStrategy,
  Component,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { environment } from '../../../environments/environment';
import { I18nService } from '../../core/i18n/i18n.service';
import { BrandLogoComponent } from '../../layout/brand-logo/brand-logo.component';
import { LanguageToggleComponent } from '../../layout/language-toggle/language-toggle.component';
import { LandingEvidenceComponent } from './landing-evidence/landing-evidence.component';
import { LandingMailMenuComponent } from './landing-mail-menu/landing-mail-menu.component';
import {
  GALLERY_CARDS,
  type GalleryCard,
  LandingGalleryComponent,
} from './landing-gallery/landing-gallery.component';
import {
  FAQ_ITEMS,
  type FaqItem,
  LandingPilotComponent,
} from './landing-pilot/landing-pilot.component';

export { GALLERY_CARDS, FAQ_ITEMS };
export type { GalleryCard, FaqItem };
export type GalleryTab = GalleryCard;
export const GALLERY_TABS = GALLERY_CARDS;

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [
    BrandLogoComponent,
    LanguageToggleComponent,
    LandingGalleryComponent,
    LandingEvidenceComponent,
    LandingMailMenuComponent,
    LandingPilotComponent,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    TranslatePipe,
  ],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {
  private readonly translate = inject(TranslateService);
  readonly i18n = inject(I18nService);

  @ViewChild(LandingGalleryComponent) galleryComponent?: LandingGalleryComponent;
  @ViewChild(LandingPilotComponent) pilotComponent?: LandingPilotComponent;

  readonly salesEmail = environment.salesEmail;
  readonly salesMailto = `mailto:${environment.salesEmail}`;
  readonly currentLocale = this.i18n.currentLocale;
  readonly isRtl = this.i18n.isRtl;

  readonly activeCardIndex = signal(0);
  readonly emailCopied = signal(false);

  readonly galleryCards = GALLERY_CARDS;
  readonly galleryTabs = GALLERY_CARDS;
  readonly faqItems = FAQ_ITEMS;

  readonly demoLastQuoted = { amount: 2600.0, currency: 'EGP' };
  readonly demoPaid = { amount: 2040.0, currency: 'EGP' };
  readonly demoCalculated = { amount: 560.0, currency: 'EGP' };
  readonly demoVerified = { amount: 560.0, currency: 'EGP' };

  readonly heroImageSrc = computed(
    () => `/landing/${this.currentLocale()}/hero-recommendation.jpg`
  );
  readonly heroImageAlt = computed(() =>
    this.translate.instant('landing.hero.visualAlt')
  );

  scrollToCard(index: number): void {
    this.activeCardIndex.set(index);
    this.galleryComponent?.scrollToCard(index);
  }

  nextCard(): void {
    this.galleryComponent?.nextCard();
  }

  prevCard(): void {
    this.galleryComponent?.prevCard();
  }

  openEnlargeDialog(indexOrTab: number | GalleryCard): void {
    this.galleryComponent?.openEnlargeDialog(indexOrTab);
  }

  copyEmail(): void {
    this.pilotComponent?.copyEmail();
  }
}
