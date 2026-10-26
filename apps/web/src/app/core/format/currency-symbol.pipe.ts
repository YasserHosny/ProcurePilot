import { Pipe, PipeTransform, inject } from '@angular/core';

import { FormatService } from './format.service';

/**
 * Pipe to format a currency code into its display symbol (e.g. 'ج.م' for Arabic locales, ISO code for English).
 *
 * Example: {{ 'EGP' | currencySymbol }}
 */
@Pipe({
  name: 'currencySymbol',
  standalone: true,
  // Impure so a language switch re-renders the symbol (the input string itself does not change).
  pure: false,
})
export class CurrencySymbolPipe implements PipeTransform {
  private readonly formatService = inject(FormatService);

  transform(value: string | null | undefined, localeOverride?: string): string {
    if (!value) return '';
    return this.formatService.currencySymbol(value, localeOverride);
  }
}
