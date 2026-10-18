import type { TranslateService } from '@ngx-translate/core';
import type { PackDefinition } from '../../core/api/models';
import type { FormatService } from '../../core/format/format.service';

export function packLabel(
  pack: PackDefinition | string | null | undefined,
  baseUnit: string,
  translate: TranslateService,
  format: FormatService,
): { size: number; unit: string; label: string | null } {
  const size = typeof pack === 'string'
    ? parseFloat(pack)
    : pack
      ? parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)))
      : 0;
  const key = `rfq.email.units.${baseUnit}`;
  const translated: string = translate.instant(key);
  const unit = translated === key ? baseUnit : translated;
  const label: string | null = Number.isFinite(size) && size > 0 && size !== 1
    ? translate.instant('orders.create.packUnit', { size: format.formatNumber(size, { maximumFractionDigits: 6 }), unit })
    : null;
  return { size, unit, label };
}
