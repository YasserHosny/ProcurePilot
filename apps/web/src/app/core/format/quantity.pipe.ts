import { Pipe, PipeTransform, inject } from '@angular/core';

import { FormatService } from './format.service';

/**
 * Quantity without trailing zeros and with locale digits (`100.000000` -> `100` / `١٠٠`).
 *
 * Example: {{ line.quantity | formatQuantity }}
 */
@Pipe({
  name: 'formatQuantity',
  standalone: true,
})
export class FormatQuantityPipe implements PipeTransform {
  private readonly formatService = inject(FormatService);

  transform(value: number | string | null | undefined, localeOverride?: string): string {
    return this.formatService.formatExactQuantity(value, localeOverride);
  }
}
