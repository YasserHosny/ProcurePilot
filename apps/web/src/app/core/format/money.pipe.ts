import { Pipe, PipeTransform, inject } from '@angular/core';

import type { Money } from '../api/models';
import { FormatService } from './format.service';

/**
 * Pipe to format Money structures ensuring an explicit currency is always rendered.
 *
 * Example: {{ invoice.total | formatMoney }}
 */
@Pipe({
  name: 'formatMoney',
  standalone: true,
})
export class FormatMoneyPipe implements PipeTransform {
  private readonly formatService = inject(FormatService);

  transform(
    value: Money | { amount: string | number; currency: string } | null | undefined,
    localeOverride?: string,
  ): string {
    return this.formatService.formatMoney(value, localeOverride);
  }
}
