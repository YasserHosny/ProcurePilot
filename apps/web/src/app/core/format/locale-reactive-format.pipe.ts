import { ChangeDetectorRef, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslateService } from '@ngx-translate/core';

import { FormatService } from './format.service';

/**
 * Shared support for impure locale-aware format pipes.
 * Subscribes to language changes so OnPush hosts re-check, and memoises the last
 * formatted string so impure change-detection passes do not rebuild Intl formatters.
 */
export abstract class LocaleReactiveFormatPipe {
  protected readonly formatService = inject(FormatService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);
  private readonly translate = inject(TranslateService, { optional: true });

  private memoised = false;
  private memoLocale: string | undefined;
  private memoLocaleOverride: string | undefined;
  private memoResult = '';

  constructor() {
    this.translate?.onLangChange
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.cdr.markForCheck());
  }

  /**
   * Returns the cached string when `argsMatch`, `localeOverride` and the resolved
   * locale are unchanged; otherwise runs `compute` and stores the result.
   */
  protected memoisedOrCompute(
    localeOverride: string | undefined,
    argsMatch: boolean,
    compute: () => string,
  ): string {
    const locale = this.formatService.locale(localeOverride);
    if (
      this.memoised &&
      argsMatch &&
      this.memoLocaleOverride === localeOverride &&
      this.memoLocale === locale
    ) {
      return this.memoResult;
    }
    const result = compute();
    this.memoised = true;
    this.memoLocale = locale;
    this.memoLocaleOverride = localeOverride;
    this.memoResult = result;
    return result;
  }
}
