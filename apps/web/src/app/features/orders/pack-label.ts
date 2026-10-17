import type { TranslateService } from '@ngx-translate/core';
import type { Product } from '../../core/api/models';
import type { FormatService } from '../../core/format/format.service';

export function packLabel(
  product: Product | undefined,
  baseUnit: string,
  translate: TranslateService,
  format: FormatService,
): { size: number; unit: string; label: string | null } {
  const pack = product?.pack;
  const size = pack
    ? parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)))
    : 0;
  const key = `rfq.email.units.${baseUnit}`;
  const translated: string = translate.instant(key);
  const unit = translated === key ? baseUnit : translated;
  const label: string | null = size > 1
    ? translate.instant('orders.create.packUnit', { size: format.formatQuantity(size), unit })
    : null;
  return { size, unit, label };
}
