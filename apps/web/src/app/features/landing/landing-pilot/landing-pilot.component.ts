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
import { MatMenuModule } from '@angular/material/menu';
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
  imports: [MatButtonModule, MatIconModule, MatMenuModule, TranslatePipe],
  templateUrl: './landing-pilot.component.html',
  styleUrl: './landing-pilot.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingPilotComponent implements OnDestroy {
  private readonly translate = inject(TranslateService);
  private readonly clipboard = inject(Clipboard);
  readonly i18n = inject(I18nService);

  readonly salesEmail = environment.salesEmail;
  readonly faqItems = FAQ_ITEMS;
  readonly emailCopied = model<boolean>(false);
  private copyTimeoutId: ReturnType<typeof setTimeout> | null = null;

  private readonly emailDraft = computed(() => {
    this.i18n.currentLocale();
    return {
      to: encodeURIComponent(this.salesEmail),
      subject: encodeURIComponent(this.translate.instant('landing.pilot.emailSubject')),
      body: encodeURIComponent(this.translate.instant('landing.pilot.emailBody')),
    };
  });

  // mailto: only works where a mail app is set up, so webmail users get their own compose links.
  readonly mailtoLink = computed(() => {
    const { subject, body } = this.emailDraft();
    return `mailto:${this.salesEmail}?subject=${subject}&body=${body}`;
  });

  readonly gmailLink = computed(() => {
    const { to, subject, body } = this.emailDraft();
    return `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${subject}&body=${body}`;
  });

  readonly outlookLink = computed(() => {
    const { to, subject, body } = this.emailDraft();
    return `https://outlook.office.com/mail/deeplink/compose?to=${to}&subject=${subject}&body=${body}`;
  });

  readonly whatsappLink = computed(() => {
    this.i18n.currentLocale();
    const text = this.translate.instant('landing.pilot.whatsappMessage');
    return `https://wa.me/${environment.salesWhatsapp}?text=${encodeURIComponent(text)}`;
  });

  copyEmail(): void {
    this.clipboard.copy(this.salesEmail);
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
