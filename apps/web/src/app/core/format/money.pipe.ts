import { Pipe, PipeTransform } from '@angular/core';

import type { Money } from '../api/models';
import { LocaleReactiveFormatPipe } from './locale-reactive-format.pipe';

type MoneyInput = Money | { amount: string | number; currency: string } | null | undefined;

/**
 * Pipe to format Money structures ensuring an explicit currency is always rendered.
 *
 * Example: {{ invoice.total | formatMoney }}
 */
@Pipe({
  name: 'formatMoney',
  standalone: true,
  // Impure so a language switch re-renders without a reload (the Money input itself does not change).
  pure: false,
})
export class FormatMoneyPipe extends LocaleReactiveFormatPipe implements PipeTransform {
  private lastValue: MoneyInput;
  private lastAmount: string | number | null | undefined;
  private lastCurrency: string | undefined;
  private hasLast = false;

  transform(value: MoneyInput, localeOverride?: string): string {
    const amount = value?.amount;
    const currency = value?.currency;
    const argsMatch =
      this.hasLast &&
      this.lastValue === value &&
      this.lastAmount === amount &&
      this.lastCurrency === currency;

    const result = this.memoisedOrCompute(localeOverride, argsMatch, () =>
      this.formatService.formatMoney(value, localeOverride),
    );
    this.hasLast = true;
    this.lastValue = value;
    this.lastAmount = amount;
    this.lastCurrency = currency;
    return result;
  }
}
