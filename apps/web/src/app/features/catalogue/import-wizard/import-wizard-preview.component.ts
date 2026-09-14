import { Component, EventEmitter, Input, Output } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatRadioModule } from "@angular/material/radio";
import { MatTableModule } from "@angular/material/table";
import { TranslatePipe } from "@ngx-translate/core";

import type { ImportPreview } from "../../../core/api/models";

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
  styleUrl: "./import-wizard-preview.component.scss",
})
export class ImportWizardPreviewComponent {
  @Input({ required: true }) preview!: ImportPreview;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) isCommitting = false;
  @Input() duplicateHandling: "skip" | "update" = "skip";
  @Output() readonly duplicateHandlingChange = new EventEmitter<"skip" | "update">();
  @Output() readonly commit = new EventEmitter<void>();
  @Output() readonly resetWizard = new EventEmitter<void>();

  readonly errorColumns: readonly string[] = ["line", "column", "reason"];

  getPreviewObjectKeys(rows: readonly Record<string, unknown>[] | undefined): string[] {
    if (!rows || rows.length === 0) return [];
    return Object.keys(rows[0]);
  }

  formatPreviewCell(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value !== "object") return String(value);
    const obj = value as Record<string, unknown>;
    if ("amount" in obj && "currency" in obj) {
      return `${obj["amount"]} ${obj["currency"]}`;
    }
    return JSON.stringify(value);
  }

  onDuplicateUpdated(val: "skip" | "update"): void {
    this.duplicateHandling = val;
    this.duplicateHandlingChange.emit(val);
  }
}
