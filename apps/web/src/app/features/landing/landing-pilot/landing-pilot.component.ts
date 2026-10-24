import { Clipboard } from '@angular/cdk/clipboard';
import {
  ChangeDetectionStrategy,
  Component,
  OnDestroy,
  computed,
  inject,
  model,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { environment } from '../../../../environments/environment';
import { I18nService } from '../../../core/i18n/i18n.service';

export interface FaqItem {
  readonly id: string;
  readonly qKey: string;
  readonly aKey: string;
}

export const FAQ_ITEMS: readonly FaqItem[] = [
  { id: 'q1', qKey: 'landing.pilot.q1', aKey: 'landing.pilot.a1' },
  { id: 'q2', qKey: 'landing.pilot.q2', aKey: 'landing.pilot.a2' },
  { id: 'q3', qKey: 'landing.pilot.q3', aKey: 'landing.pilot.a3' },
  { id: 'q4', qKey: 'landing.pilot.q4', aKey: 'landing.pilot.a4' },
];

@Component({
  selector: 'app-landing-pilot',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: './landing-pilot.component.html',
  styleUrl: './landing-pilot.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingPilotComponent implements OnDestroy {
  private readonly translate = inject(TranslateService);
  private readonly clipboard = inject(Clipboard);
  readonly i18n = inject(I18nService);

  readonly supportEmail = environment.supportEmail;
  readonly faqItems = FAQ_ITEMS;
  readonly emailCopied = model<boolean>(false);
  private copyTimeoutId: ReturnType<typeof setTimeout> | null = null;

  readonly mailtoLink = computed(() => {
    this.i18n.currentLocale();
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

  ngOnDestroy(): void {
    if (this.copyTimeoutId) {
      clearTimeout(this.copyTimeoutId);
    }
  }
}
