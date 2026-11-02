import type { TranslateService } from '@ngx-translate/core';
import type { BasketPackSnapshot, Product } from '../../../core/api/models';
import type { FormatService } from '../../../core/format/format.service';
import { unitLabel } from '../../../core/format/unit-label';

export interface QuantityDisplayResult {
  readonly primary: string;
  readonly secondary: string | null;
}

export interface QuantityDisplayOptions {
  readonly line: { workspace_product_id: string; quantity: string | number };
  readonly product?: Product | null;
  readonly packSnapshot?: Readonly<Record<string, BasketPackSnapshot>> | null;
  readonly translate: TranslateService;
  readonly format: FormatService;
}

/**
 * ADR-020: quantities are bought in packs. The solver works in base units, so show
 * "20 × 25 kg" first and the base total secondary. Loose goods (pack of 1) show base only.
 */
export function formatQuantityDisplay(options: QuantityDisplayOptions): QuantityDisplayResult {
  const { line, product, packSnapshot, translate, format } = options;
  const base = typeof line.quantity === 'number' ? line.quantity : parseFloat(line.quantity);
  const rawUnit =
    packSnapshot?.[line.workspace_product_id]?.base_unit ??
    product?.base_unit ??
    '';
  const unit = unitLabel(translate, rawUnit);
  const fmt = (n: number): string =>
    format.formatNumber(n, { maximumFractionDigits: 6 });

  // Prefer the pack definition captured at submission: the catalogue may have changed since.
  const snapshot = packSnapshot?.[line.workspace_product_id];
  const pack = product?.pack;
  const size = snapshot
    ? parseFloat(snapshot.base_quantity)
    : pack
      ? parseFloat(pack.base_quantity ?? String(pack.pack_count * parseFloat(pack.unit_size)))
      : 0;

  // Only a pack of exactly one base unit is "loose goods"; a 0.5 kg pack is still a pack.
  if (!Number.isFinite(base) || !Number.isFinite(size) || size <= 0 || size === 1) {
    const rawVal = Number.isFinite(base) ? fmt(base) : String(line.quantity);
    return { primary: `${rawVal} ${unit}`.trim(), secondary: null };
  }

  const packs = base / size;
  return {
    primary: translate.instant('basketSplit.result.packQuantity', {
      count: fmt(packs),
      size: fmt(size),
      unit,
    }),
    secondary: translate.instant('basketSplit.result.baseEquivalent', {
      total: fmt(base),
      unit,
    }),
  };
}
