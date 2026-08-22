import { Component, inject } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import { TranslatePipe } from "@ngx-translate/core";

export interface ConfirmDialogData {
  readonly titleKey: string;
  readonly messageKey: string;
  readonly itemName?: string;
  readonly confirmKey: string;
  readonly cancelKey?: string;
  readonly isDestructive?: boolean;
}

@Component({
  selector: "app-catalogue-confirm-dialog",
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: "./confirm-dialog.component.html",
  styleUrl: "./confirm-dialog.component.scss",
})
export class CatalogueConfirmDialogComponent {
  private readonly dialogRef = inject(MatDialogRef<CatalogueConfirmDialogComponent, boolean>);
  readonly data: ConfirmDialogData = inject(MAT_DIALOG_DATA);

  onConfirm(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
