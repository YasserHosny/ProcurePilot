import { Router } from '@angular/router';

import type { Alert } from './alerts-api';

/**
 * Navigation helpers for actionable alerts.
 * Strictly routes to existing Chunk 4.2-4.5 screens without introducing out-of-scope purchase/request actions.
 */
export function navigateAlertAction(router: Router, alert: Alert): void {
  switch (alert.action) {
    case 'compare_product':
      router.navigate(['/offers/compare', alert.workspace_product_id], {
        queryParams: { product_id: alert.workspace_product_id },
      });
      break;

    case 'review_supplier':
      if (alert.supplier_id) {
        router.navigate(['/suppliers', alert.supplier_id]);
      } else {
        router.navigate(['/suppliers']);
      }
      break;

    case 'view_price_history':
      router.navigate(['/offers/product-intelligence', alert.workspace_product_id], {
        queryParams: {
          product_id: alert.workspace_product_id,
          supplier_id: alert.supplier_id || undefined,
        },
      });
      break;

    case 'inspect_scorecard':
      if (alert.supplier_id) {
        router.navigate(['/suppliers', alert.supplier_id, 'scorecard']);
      } else {
        router.navigate(['/suppliers']);
      }
      break;

    case 'review_quotation': {
      const quotationId =
        alert.evidence && typeof alert.evidence === 'object'
          ? ((alert.evidence['quotation_id_1'] as string) ||
            (alert.evidence['quotation_id'] as string) ||
            null)
          : null;
      if (quotationId) {
        router.navigate(['/quotations', quotationId, 'review']);
      } else {
        router.navigate(['/quotations']);
      }
      break;
    }

    case 'view_delivery_issues':
      if (alert.supplier_id) {
        router.navigate(['/suppliers', alert.supplier_id, 'scorecard']);
      } else {
        router.navigate(['/suppliers']);
      }
      break;

    default:
      break;
  }
}
