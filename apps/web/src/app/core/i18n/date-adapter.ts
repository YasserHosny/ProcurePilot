import { DestroyRef, Injectable, Injector, Provider, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  DateAdapter,
  MAT_DATE_FORMATS,
  MAT_NATIVE_DATE_FORMATS,
  NativeDateAdapter,
} from '@angular/material/core';
import { TranslateService } from '@ngx-translate/core';

import { SessionService } from '../auth/session.service';

const ARABIC_INDIC = '٠١٢٣٤٥٦٧٨٩';
const EXTENDED_ARABIC_INDIC = '۰۱۲۳۴۵۶۷۸۹';

function toLatinDigits(value: string): string {
  return value.replace(/[٠-٩۰-۹]/g, (d) => {
    const i = ARABIC_INDIC.indexOf(d);
    return String(i !== -1 ? i : EXTENDED_ARABIC_INDIC.indexOf(d));
  });
}

const pad = (n: number): string => String(n).padStart(2, '0');

/**
 * Date-picker adapter that follows the interface language instead of the browser's.
 *
 * Typed dates are day-first (DD/MM/YYYY) in Arabic and for every workspace outside the US
 * region (Egypt, the Gulf, UK, ...); only an English-language US workspace gets MM/DD/YYYY --
 * the same convention extraction uses to read quote dates. The input
 * keeps Latin digits so it is easy to type, and accepts Arabic-Indic digits too. Calendar month
 * and day names come from the UI language.
 */
@Injectable()
export class AppDateAdapter extends NativeDateAdapter {
  private readonly translate = inject(TranslateService, { optional: true });
  private readonly injector = inject(Injector);

  constructor() {
    super();
    // Start in the interface locale. Material rewrites the input text on every localeChanges,
    // so a first sync from inside parse() wiped the first typed digit (finding 40).
    this.syncLocale();
    // Re-emit localeChanges on a language switch so date inputs already on screen reformat
    // and an open calendar relabels, instead of waiting for the next adapter call.
    this.translate?.onLangChange
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => this.syncLocale());
  }

  private language(): string {
    return this.translate?.currentLang || this.translate?.getDefaultLang() || 'en';
  }

  private region(): string | undefined {
    try {
      return this.injector.get(SessionService, null)?.tenant()?.region;
    } catch {
      return undefined;
    }
  }

  /** True unless the workspace works month-first (English UI, US region). */
  isDayFirst(): boolean {
    return !(this.language() === 'en' && this.region() === 'US');
  }

  private syncLocale(): void {
    const locale = this.language() === 'ar' ? 'ar-EG' : this.isDayFirst() ? 'en-GB' : 'en-US';
    if (this.locale !== locale) {
      this.setLocale(locale);
    }
  }

  override format(date: Date, displayFormat: object): string {
    this.syncLocale();
    if (displayFormat === MAT_NATIVE_DATE_FORMATS.display.dateInput) {
      const day = pad(date.getDate());
      const month = pad(date.getMonth() + 1);
      const year = String(date.getFullYear());
      return this.isDayFirst() ? `${day}/${month}/${year}` : `${month}/${day}/${year}`;
    }
    return super.format(date, displayFormat);
  }

  // Never syncs the locale: that emits localeChanges, and Material would overwrite what the
  // user is typing. Day/month order comes from isDayFirst(), not from this.locale.
  override parse(value: unknown, parseFormat?: unknown): Date | null {
    if (typeof value === 'string') {
      const text = toLatinDigits(value.trim());
      if (!text) return null;
      const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
      if (iso) return this.build(+iso[1], +iso[2], +iso[3]);
      const parts = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(text);
      if (parts) {
        const [first, second, year] = [+parts[1], +parts[2], +parts[3]];
        return this.isDayFirst()
          ? this.build(year, second, first)
          : this.build(year, first, second);
      }
      // Anything else (a partly typed "22/1") is invalid, never Date.parse's month-first guess.
      return this.invalid();
    }
    return super.parse(value, parseFormat);
  }

  override getMonthNames(style: 'long' | 'short' | 'narrow'): string[] {
    this.syncLocale();
    return super.getMonthNames(style);
  }

  override getDateNames(): string[] {
    this.syncLocale();
    return super.getDateNames();
  }

  override getDayOfWeekNames(style: 'long' | 'short' | 'narrow'): string[] {
    this.syncLocale();
    return super.getDayOfWeekNames(style);
  }

  override getYearName(date: Date): string {
    this.syncLocale();
    return super.getYearName(date);
  }

  override getFirstDayOfWeek(): number {
    // Saturday in Egypt; Monday elsewhere day-first; Sunday for US workspaces.
    if (this.language() === 'ar' || this.region() === 'EG') return 6;
    return this.isDayFirst() ? 1 : 0;
  }

  /** An invalid Date for out-of-range parts (31/02), so the form reports it instead of rolling over. */
  private build(year: number, month: number, day: number): Date {
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
      ? date
      : this.invalid();
  }
}

/** Use in place of MatNativeDateModule / provideNativeDateAdapter(). */
export function provideAppDateAdapter(): Provider[] {
  return [
    { provide: DateAdapter, useClass: AppDateAdapter },
    { provide: MAT_DATE_FORMATS, useValue: MAT_NATIVE_DATE_FORMATS },
  ];
}
