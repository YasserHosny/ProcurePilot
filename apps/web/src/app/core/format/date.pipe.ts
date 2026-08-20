import { Pipe, PipeTransform, inject } from '@angular/core';

import { FormatService } from './format.service';

/**
 * Pipe to format Date objects or ISO date strings with locale sensitivity.
 *
 * Example: {{ item.created_at | formatDate }}
 */
@Pipe({
  name: 'formatDate',
  standalone: true,
})
export class FormatDatePipe implements PipeTransform {
  private readonly formatService = inject(FormatService);

  transform(
    value: string | Date | number | null | undefined,
    options?: Intl.DateTimeFormatOptions,
    localeOverride?: string,
  ): string {
    return this.formatService.formatDate(value, options, localeOverride);
  }
}
