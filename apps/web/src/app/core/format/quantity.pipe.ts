import { Pipe, PipeTransform } from '@angular/core';

import { LocaleReactiveFormatPipe } from './locale-reactive-format.pipe';

/**
 * Quantity without trailing zeros and with locale digits (`100.000000` -> `100` / `١٠٠`).
 *
 * Example: {{ line.quantity | formatQuantity }}
 */
@Pipe({
  name: 'formatQuantity',
  standalone: true,
  // Impure so a language switch re-renders without a reload (the quantity input itself does not change).
  pure: false,
})
export class FormatQuantityPipe extends LocaleReactiveFormatPipe implements PipeTransform {
  private lastValue: number | string | null | undefined;
  private hasLast = false;

  transform(value: number | string | null | undefined, localeOverride?: string): string {
    const argsMatch = this.hasLast && this.lastValue === value;

    const result = this.memoisedOrCompute(localeOverride, argsMatch, () =>
      this.formatService.formatExactQuantity(value, localeOverride),
    );
    this.hasLast = true;
    this.lastValue = value;
    return result;
  }
}
