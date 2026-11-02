import { Pipe, PipeTransform } from '@angular/core';

import { LocaleReactiveFormatPipe } from './locale-reactive-format.pipe';

/**
 * Pipe to format Date objects or ISO date strings with locale sensitivity.
 *
 * Example: {{ item.created_at | formatDate }}
 */
@Pipe({
  name: 'formatDate',
  standalone: true,
  // Impure so a language switch re-renders without a reload (the date input itself does not change).
  pure: false,
})
export class FormatDatePipe extends LocaleReactiveFormatPipe implements PipeTransform {
  private lastValue: string | Date | number | null | undefined;
  private lastOptions: Intl.DateTimeFormatOptions | undefined;
  private hasLast = false;

  transform(
    value: string | Date | number | null | undefined,
    options?: Intl.DateTimeFormatOptions,
    localeOverride?: string,
  ): string {
    const argsMatch =
      this.hasLast && this.lastValue === value && this.lastOptions === options;

    const result = this.memoisedOrCompute(localeOverride, argsMatch, () =>
      this.formatService.formatDate(value, options, localeOverride),
    );
    this.hasLast = true;
    this.lastValue = value;
    this.lastOptions = options;
    return result;
  }
}
