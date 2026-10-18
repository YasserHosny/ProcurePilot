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

// PO lines created before #128 had "(pack of <size> <base unit code>)" appended to the stored
// description in English; the pack is now rendered separately and localised. Hide that suffix
// for display only when it is exactly what the old code generated from this line's own pack
// fields, so text a user typed is never hidden, and never strip it from what gets saved.
const LEGACY_PACK_SUFFIX = /\s*\(pack of ([\d.]+) ([a-z]+)\)$/;

export function lineDescription(line: {
  description: string;
  pack_base_quantity?: string | null;
  base_unit: string;
}): string {
  const match = LEGACY_PACK_SUFFIX.exec(line.description);
  if (!match || line.pack_base_quantity == null) return line.description;
  const generated =
    parseFloat(match[1]) === parseFloat(line.pack_base_quantity) && match[2] === line.base_unit;
  return generated ? line.description.slice(0, match.index) : line.description;
}
