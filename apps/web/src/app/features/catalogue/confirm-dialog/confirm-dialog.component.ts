import { Component, inject, ChangeDetectionStrategy, ElementRef, afterNextRender } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import { TranslatePipe } from "@ngx-translate/core";

export interface ConfirmDialogData {
  readonly titleKey: string;
  readonly messageKey: string;
  readonly messageParams?: Record<string, unknown>;
  readonly itemName?: string;
  readonly confirmKey: string;
  readonly confirmParams?: Record<string, unknown>;
  readonly cancelKey?: string;
  readonly isDestructive?: boolean;
  readonly warningKey?: string;
  readonly warningParams?: Record<string, unknown>;
  readonly showConfirm?: boolean;
  readonly listItems?: readonly string[];
  readonly previewSubject?: string;
  readonly previewBody?: string;
  readonly previewLocale?: string;
  readonly [key: string]: unknown;
}

let nextDescriptionId = 0;

@Component({
  selector: "app-catalogue-confirm-dialog",
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: "./confirm-dialog.component.html",
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: "./confirm-dialog.component.scss",
})
export class CatalogueConfirmDialogComponent {
  private readonly dialogRef = inject(MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
  readonly data: ConfirmDialogData = inject(MAT_DIALOG_DATA);

  readonly messageId = `confirm-dialog-message-${nextDescriptionId++}`;
  readonly warningId = `${this.messageId}-warning`;

  constructor() {
    const host = inject(ElementRef<HTMLElement>).nativeElement;
    afterNextRender(() => {
      const container = host.closest('.mat-mdc-dialog-container');
      if (!container) return;

      container.setAttribute('aria-modal', 'true');
      const descriptionIds = new Set(
        (container.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean),
      );
      descriptionIds.add(this.messageId);
      if (this.data.warningKey) descriptionIds.add(this.warningId);
      container.setAttribute('aria-describedby', [...descriptionIds].join(' '));
    });
  }

  onConfirm(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
