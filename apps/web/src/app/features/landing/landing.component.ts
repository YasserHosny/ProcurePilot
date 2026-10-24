import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { environment } from '../../../environments/environment';
import { BrandLogoComponent } from '../../layout/brand-logo/brand-logo.component';
import { LanguageToggleComponent } from '../../layout/language-toggle/language-toggle.component';

export interface ScreenshotCard {
  readonly src: string;
  readonly alt: string;
  readonly captionKey: string;
}

// Screenshot cards for the product preview gallery.
// PPS-36 fills this array once final UI captures are ready.
export const SCREENSHOT_CARDS: readonly ScreenshotCard[] = [];

@Component({
  selector: 'app-landing',
  standalone: true,
  imports: [
    BrandLogoComponent,
    LanguageToggleComponent,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {
  readonly supportMailto = `mailto:${environment.supportEmail}`;
  readonly screenshotCards = signal<readonly ScreenshotCard[]>(SCREENSHOT_CARDS);
  readonly activeScreenshot = signal<ScreenshotCard | null>(null);

  openModal(card: ScreenshotCard): void {
    this.activeScreenshot.set(card);
  }

  closeModal(): void {
    this.activeScreenshot.set(null);
  }

  onBackdropClick(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      this.closeModal();
    }
  }
}
