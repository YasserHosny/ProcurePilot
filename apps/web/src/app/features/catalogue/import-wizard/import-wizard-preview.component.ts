import { Component, EventEmitter, Input, OnInit, Output, inject, signal, ChangeDetectionStrategy } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatRadioModule } from "@angular/material/radio";
import { MatTableModule } from "@angular/material/table";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import { ApiService } from "../../../core/api/api.service";
import type { BaseUnit, ImportPreview } from "../../../core/api/models";
import { formatCurrencyAmount } from "../../../core/format/format.service";
import { I18nService } from "../../../core/i18n";

@Component({
  selector: "app-import-wizard-preview",
  standalone: true,
  imports: [
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatRadioModule,
    MatTableModule,
    MatProgressSpinnerModule,
    TranslatePipe,
  ],
  templateUrl: "./import-wizard-preview.component.html",
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: "./import-wizard-preview.component.scss",
})
export class ImportWizardPreviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly i18n = inject(I18nService);
  private readonly translate = inject(TranslateService);

  @Input({ required: true }) preview!: ImportPreview;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) isCommitting = false;
  @Input() duplicateHandling: "skip" | "update" = "skip";
  @Output() readonly duplicateHandlingChange = new EventEmitter<"skip" | "update">();
  @Output() readonly commit = new EventEmitter<void>();
  @Output() readonly resetWizard = new EventEmitter<void>();

  readonly baseUnits = signal<readonly BaseUnit[]>([]);
  readonly errorColumns: readonly string[] = ["line", "column", "reason"];

  ngOnInit(): void {
    this.api.baseUnits?.()?.subscribe({
      next: (res) => this.baseUnits.set(res.items),
      error: () => this.baseUnits.set([]),
    });
  }

  getPreviewObjectKeys(rows: readonly Record<string, unknown>[] | undefined): string[] {
    if (!rows || rows.length === 0) return [];
    return Object.keys(rows[0]);
  }

  formatPreviewHeader(column: string): string {
    const key = `catalogue.import.previewColumns.${column}`;
    const translated = this.translate.instant(key);
    return translated && translated !== key ? translated : column;
  }

  formatPreviewCell(value: unknown, row?: Record<string, unknown>): string {
    if (value === null || value === undefined) return "—";
    if (typeof value !== "object") return String(value);
    const obj = value as Record<string, unknown>;
    if ("pack_count" in obj && "unit_size" in obj) {
      return this.formatPackCell(obj, row);
    }
    if (
      "amount" in obj &&
      "currency" in obj &&
      typeof obj["currency"] === "string"
    ) {
      return formatCurrencyAmount(
        { amount: obj["amount"] as string | number, currency: obj["currency"] },
        this.translate.getCurrentLang() || this.translate.getFallbackLang() || "en",
      );
    }
    return JSON.stringify(value);
  }

  formatPackCell(pack: Record<string, unknown>, row?: Record<string, unknown>): string {
    const packCount = String(pack["pack_count"] ?? "");
    const unitSize = this.stripTrailingDecimalZeros(String(pack["unit_size"] ?? ""));
    const baseUnitCode = typeof row?.["base_unit"] === "string" ? row["base_unit"] : "";
    const unitLabel = this.resolveUnitLabel(baseUnitCode);
    return unitLabel ? `${packCount} × ${unitSize} ${unitLabel}` : `${packCount} × ${unitSize}`;
  }

  resolveUnitLabel(code: string): string {
    if (!code) return "";
    const match = this.baseUnits().find((unit) => unit.code === code);
    if (!match) return code;
    return this.i18n.currentLocale() === "ar" ? match.label_ar : match.label_en;
  }

  private stripTrailingDecimalZeros(value: string): string {
    if (!value.includes(".")) return value;
    return value.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
  }

  onDuplicateUpdated(val: "skip" | "update"): void {
    this.duplicateHandling = val;
    this.duplicateHandlingChange.emit(val);
  }
}
