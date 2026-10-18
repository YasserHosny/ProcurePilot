import { Pipe, PipeTransform, inject } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';

/**
 * Display label for a supported base-unit code (`kilogram` -> `kg` / `كجم`). Unknown codes are
 * shown as-is rather than as a raw translation key.
 */
export function unitLabel(translate: TranslateService, code: string | null | undefined): string {
  if (!code) return '';
  const key = `units.${code}`;
  const translated: string = translate.instant(key);
  return translated === key ? code : translated;
}

/** Example: {{ product.base_unit | unitLabel }} */
@Pipe({
  name: 'unitLabel',
  standalone: true,
  // Impure so a language switch relabels without a reload, like the translate pipe.
  pure: false,
})
export class UnitLabelPipe implements PipeTransform {
  private readonly translate = inject(TranslateService);

  transform(code: string | null | undefined): string {
    return unitLabel(this.translate, code);
  }
}
