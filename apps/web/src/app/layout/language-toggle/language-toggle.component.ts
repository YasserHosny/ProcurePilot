import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { TranslatePipe } from '@ngx-translate/core';

import { I18nService } from '../../core/i18n/i18n.service';

export interface LanguageToggleState {
  readonly lang: 'en' | 'ar';
  readonly labelKey: string;
  readonly titleKey: string;
}

@Component({
  selector: 'app-language-toggle',
  standalone: true,
  imports: [MatButtonModule, TranslatePipe],
  templateUrl: './language-toggle.component.html',
  styleUrl: './language-toggle.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LanguageToggleComponent {
  private readonly i18n = inject(I18nService);

  readonly currentLocale = this.i18n.currentLocale;

  readonly state = computed<LanguageToggleState>(() => {
    const isEn = this.currentLocale() === 'en';
    return {
      lang: isEn ? 'ar' : 'en',
      labelKey: isEn ? 'common.languageToggle.labelAr' : 'common.languageToggle.labelEn',
      titleKey: isEn ? 'common.languageToggle.switchToAr' : 'common.languageToggle.switchToEn',
    };
  });

  toggleLanguage(): void {
    const nextLocale = this.currentLocale() === 'en' ? 'ar' : 'en';
    this.i18n.setLocale(nextLocale).subscribe();
  }
}
