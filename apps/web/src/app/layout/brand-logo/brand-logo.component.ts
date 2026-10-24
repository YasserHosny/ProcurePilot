import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

/** Below this height the full lockup is unreadable: the brand rules call for the mark alone. */
const MIN_LOCKUP_HEIGHT_PX = 24;

/**
 * The Converge logo (docs/brand/README.md): the horizontal lockup, in Arabic when the language is
 * Arabic, or the mark alone below 24 px. It is an <img>, so it never mirrors in RTL: the arrow
 * means "forward", not reading direction.
 */
@Component({
  selector: 'app-brand-logo',
  imports: [TranslatePipe],
  templateUrl: './brand-logo.component.html',
  styleUrl: './brand-logo.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BrandLogoComponent {
  private readonly translate = inject(TranslateService);

  /** Rendered height in CSS pixels; the width follows the artwork. */
  readonly height = input<number>(28);

  readonly src = computed(() => {
    if (this.height() < MIN_LOCKUP_HEIGHT_PX) {
      return 'assets/brand/procurepilot-mark.svg';
    }
    return this.translate.currentLang() === 'ar'
      ? 'assets/brand/procurepilot-arabic-horizontal.svg'
      : 'assets/brand/procurepilot-horizontal.svg';
  });
}
