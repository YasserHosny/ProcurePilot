import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatChipsModule } from "@angular/material/chips";
import { MatDividerModule } from "@angular/material/divider";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatRadioModule } from "@angular/material/radio";
import { MatSelectModule } from "@angular/material/select";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { MatTableModule } from "@angular/material/table";
import { ActivatedRoute, Router, RouterLink } from "@angular/router";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import { ApiService } from "../../../core/api/api.service";
import type { ApiError, ImportPreview, ImportResult } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";

type WizardStep = "upload" | "preview" | "result";

@Component({
  selector: "app-import-wizard",
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatRadioModule,
    MatSelectModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
  ],
  templateUrl: "./import-wizard.component.html",
  styleUrl: "./import-wizard.component.scss",
})
export class ImportWizardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly currentStep = signal<WizardStep>("upload");
  readonly importKind = signal<"products" | "suppliers">("products");
  readonly selectedFile = signal<File | null>(null);

  readonly isUploading = signal<boolean>(false);
  readonly isCommitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly previewData = signal<ImportPreview | null>(null);
  readonly onDuplicate = signal<"skip" | "update">("skip");
  readonly importResult = signal<ImportResult | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole("owner", "buyer"));

  readonly errorColumns: readonly string[] = ["line", "column", "reason"];

  ngOnInit(): void {
    const kind = this.route.snapshot.queryParamMap.get("kind");
    if (kind === "suppliers" || kind === "products") {
      this.importKind.set(kind);
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      this.selectedFile.set(file);
      this.errorMessage.set(null);
    }
  }

  onDropFile(event: DragEvent): void {
    event.preventDefault();
    if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
      const file = event.dataTransfer.files[0];
      if (file.name.endsWith(".csv") || file.type === "text/csv") {
        this.selectedFile.set(file);
        this.errorMessage.set(null);
      } else {
        this.errorMessage.set(this.translate.instant("catalogue.import.unsupportedFileError"));
      }
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  uploadAndValidate(): void {
    const file = this.selectedFile();
    if (!file || !this.isWriter()) return;

    this.isUploading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.uploadImport(this.importKind(), file).subscribe({
      next: (res) => {
        this.previewData.set(res);
        this.isUploading.set(false);
        this.currentStep.set("preview");
      },
      error: (err: unknown) => {
        this.isUploading.set(false);
        this.handleError(err);
      },
    });
  }

  confirmImport(): void {
    const preview = this.previewData();
    if (!preview || !preview.valid || !this.isWriter()) return;

    this.isCommitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.commitImport(preview.import_id, this.onDuplicate()).subscribe({
      next: (res) => {
        this.importResult.set(res);
        this.isCommitting.set(false);
        this.currentStep.set("result");
      },
      error: (err: unknown) => {
        this.isCommitting.set(false);
        this.handleError(err);
      },
    });
  }

  resetWizard(): void {
    this.selectedFile.set(null);
    this.previewData.set(null);
    this.importResult.set(null);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.currentStep.set("upload");
  }

  getPreviewObjectKeys(rows: readonly Record<string, unknown>[] | undefined): string[] {
    if (!rows || rows.length === 0) return [];
    return Object.keys(rows[0]);
  }

  formatPreviewCell(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value !== "object") return String(value);
    const record = value as Record<string, unknown>;
    if ("pack_count" in record && "unit_size" in record) {
      return `${record["pack_count"]} × ${record["unit_size"]}`;
    }
    if ("amount" in record && "currency" in record) {
      return `${record["amount"]} ${record["currency"]}`;
    }
    return JSON.stringify(record);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      if (err.status === 415) {
        this.errorMessage.set(this.translate.instant("catalogue.import.unsupportedFileError"));
        return;
      }
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant("catalogue.import.genericError"),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant("catalogue.import.genericError"));
  }
}
