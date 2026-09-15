import { CommonModule, NgClass } from "@angular/common";
import { Component, Input } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatIconModule } from "@angular/material/icon";
import { MatTableModule } from "@angular/material/table";
import { MatTooltipModule } from "@angular/material/tooltip";
import { RouterLink } from "@angular/router";
import { TranslatePipe } from "@ngx-translate/core";

import { FormatDatePipe } from "../../../core/format/date.pipe";
import { FormatMoneyPipe } from "../../../core/format/money.pipe";
import type { ProjectedOffer } from "./compare-projection";

@Component({
  selector: "app-compare-table",
  standalone: true,
  imports: [
    CommonModule,
    NgClass,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: "./compare-table.component.html",
  styleUrl: "./compare-table.component.scss",
})
export class CompareTableComponent {
  @Input({ required: true }) offers: readonly ProjectedOffer[] = [];
  @Input({ required: true }) displayedColumns: readonly string[] = [];
  @Input() recommendedOfferId: string | null | undefined = null;
  @Input({ required: true }) requestedQuantity = "1";
  @Input({ required: true }) baseUnit = "unit";

  getConfidenceClass(confidence: string): string {
    return `confidence-${confidence.toLowerCase()}`;
  }

  formatPercent(val: string | number): string {
    const num = typeof val === "string" ? parseFloat(val) : val;
    return isNaN(num) ? "0%" : `${Math.round(num * 100)}%`;
  }

  getRecordPurchaseParams(offer: ProjectedOffer): Record<string, string> {
    const params: Record<string, string> = {
      product_id: offer.workspace_product_id,
      supplier_id: offer.supplier_id,
      unit_price: offer.projected_unit_price.amount,
      unit_price_amount: offer.projected_unit_price.amount,
      total_paid: offer.projected_landed_cost.amount,
      total_paid_amount: offer.projected_landed_cost.amount,
      realised_amount: offer.projected_landed_cost.amount,
      currency: offer.projected_landed_cost.currency,
      realised_currency: offer.projected_landed_cost.currency,
      quantity: this.requestedQuantity,
      unit: this.baseUnit,
      base_unit: this.baseUnit,
    };
    if (offer.quotation_line_id) {
      params["quotation_line_id"] = offer.quotation_line_id;
    }
    if (offer.match_decision_id) {
      params["match_decision_id"] = offer.match_decision_id;
    }
    return params;
  }
}
