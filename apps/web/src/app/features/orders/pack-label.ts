import type { TranslateService } from '@ngx-translate/core';
import type { PackDefinition } from '../../core/api/models';
import type { FormatService } from '../../core/format/format.service';
import { unitLabel } from '../../core/format/unit-label';

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
  const unit = unitLabel(translate, baseUnit);
  const label: string | null = Number.isFinite(size) && size > 0 && size !== 1
    ? translate.instant('orders.create.packUnit', { size: format.formatExactQuantity(size), unit })
    : null;
  return { size, unit, label };
}

// PO lines created before #128 had an English "(pack of 25 kilogram)" appended to the stored
// description; the pack is now rendered separately and localised, so hide the old suffix.
const LEGACY_PACK_SUFFIX = /\s*\(pack of [\d.,]+ [a-z]+\)\s*$/i;

export function lineDescription(description: string): string {
  return description.replace(LEGACY_PACK_SUFFIX, '');
}
