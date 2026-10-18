import type { TranslateService } from '@ngx-translate/core';

interface ConstraintLike {
  readonly kind?: string;
  readonly supplier_id?: string | null;
  readonly description?: string;
}

/**
 * The solver also reports internal bookkeeping (e.g. its deterministic tie-break) as an
 * "applied constraint"; that is not something a buyer can act on, so it is never shown.
 */
export function isUserFacingConstraint(constraint: ConstraintLike): boolean {
  return !(constraint.kind === 'urgency' && /tie-break/i.test(constraint.description ?? ''));
}

/** Localised sentence for a constraint, chosen by `kind`; solver free text is never shown. */
export function constraintText(
  constraint: ConstraintLike,
  translate: TranslateService,
  supplierName: (supplierId: string) => string,
  outcome: 'applied' | 'violated' = 'applied',
): string {
  const params = {
    supplier: constraint.supplier_id ? supplierName(constraint.supplier_id) : '',
  };
  // A violated constraint is a failure, so it must not reuse the "applied" wording.
  const group = outcome === 'violated' ? 'violationText' : 'constraintText';
  const key = `advancedBasket.${group}.${constraint.kind ?? 'generic'}`;
  const text: string = translate.instant(key, params);
  return text === key ? translate.instant(`advancedBasket.${group}.generic`) : text;
}
