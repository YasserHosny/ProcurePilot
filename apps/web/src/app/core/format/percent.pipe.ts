import { Pipe, PipeTransform } from '@angular/core';

import { formatScorePercent } from './format.service';
import { LocaleReactiveFormatPipe } from './locale-reactive-format.pipe';

/**
 * Whole-percent match score with locale digits (`85` -> `85%` / `٨٥٪`).
 *
 * Example: {{ formatScore(cand.confidence) | formatPercent }}
 */
@Pipe({
  name: 'formatPercent',
  standalone: true,
  // Impure so a language switch re-renders without a reload, like the other format pipes.
  pure: false,
})
export class FormatPercentPipe extends LocaleReactiveFormatPipe implements PipeTransform {
  private lastValue: number | null | undefined;
  private hasLast = false;

  transform(value: number | null | undefined, localeOverride?: string): string {
    const argsMatch = this.hasLast && this.lastValue === value;
    const result = this.memoisedOrCompute(localeOverride, argsMatch, () =>
      formatScorePercent(value, this.formatService.locale(localeOverride)),
    );
    this.hasLast = true;
    this.lastValue = value;
    return result;
  }
}
