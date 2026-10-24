import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { I18nService } from '../../../core/i18n/i18n.service';

@Component({
  selector: 'app-landing-evidence',
  standalone: true,
  imports: [TranslatePipe, FormatMoneyPipe],
  templateUrl: './landing-evidence.component.html',
  styleUrl: './landing-evidence.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingEvidenceComponent {
  readonly i18n = inject(I18nService);
  readonly currentLocale = this.i18n.currentLocale;

  readonly demoLastQuoted = { amount: 2600.0, currency: 'EGP' };
  readonly demoPaid = { amount: 2040.0, currency: 'EGP' };
  readonly demoCalculated = { amount: 560.0, currency: 'EGP' };
  readonly demoVerified = { amount: 560.0, currency: 'EGP' };
}
