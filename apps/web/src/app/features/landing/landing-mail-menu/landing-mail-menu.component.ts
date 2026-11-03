import {
  ChangeDetectionStrategy,
  Component,
  ViewChild,
  computed,
  inject,
} from '@angular/core';
import { MatMenu, MatMenuModule } from '@angular/material/menu';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { environment } from '../../../../environments/environment';
import { I18nService } from '../../../core/i18n/i18n.service';

/**
 * The "Request pilot access" menu: one pilot-request draft, opened in Gmail, Outlook or the
 * visitor's mail app. mailto: only works where a mail app is set up, so webmail users get their
 * own compose links. Open it with `[matMenuTriggerFor]="mailMenu.menu"`.
 */
@Component({
  selector: 'app-landing-mail-menu',
  standalone: true,
  imports: [MatMenuModule, TranslatePipe],
  templateUrl: './landing-mail-menu.component.html',
  styles: ':host { display: none; }',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingMailMenuComponent {
  private readonly translate = inject(TranslateService);
  private readonly i18n = inject(I18nService);

  @ViewChild(MatMenu, { static: true }) menu!: MatMenu;

  private readonly draft = computed(() => {
    this.i18n.currentLocale();
    return {
      to: encodeURIComponent(environment.salesEmail),
      subject: encodeURIComponent(this.translate.instant('landing.pilot.emailSubject')),
      body: encodeURIComponent(this.translate.instant('landing.pilot.emailBody')),
    };
  });

  readonly gmailLink = computed(() => {
    const { to, subject, body } = this.draft();
    return `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${subject}&body=${body}`;
  });

  readonly outlookLink = computed(() => {
    const { to, subject, body } = this.draft();
    return `https://outlook.office.com/mail/deeplink/compose?to=${to}&subject=${subject}&body=${body}`;
  });

  readonly mailtoLink = computed(() => {
    const { subject, body } = this.draft();
    return `mailto:${environment.salesEmail}?subject=${subject}&body=${body}`;
  });
}
