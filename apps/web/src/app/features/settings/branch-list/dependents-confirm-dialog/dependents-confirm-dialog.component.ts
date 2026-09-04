import { Component, inject } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import { TranslatePipe } from "@ngx-translate/core";

export interface DependentsConfirmDialogData {
  /** Sum of the branch's cost_centre_count and branch_role_assignment_count from the 422 details. */
  readonly dependentCount: number;
}

@Component({
  selector: "app-dependents-confirm-dialog",
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: "./dependents-confirm-dialog.component.html",
  styleUrl: "./dependents-confirm-dialog.component.scss",
})
export class BranchDependentsConfirmDialogComponent {
  private readonly dialogRef = inject(
    MatDialogRef<BranchDependentsConfirmDialogComponent, boolean>,
  );
  readonly data: DependentsConfirmDialogData = inject(MAT_DIALOG_DATA);

  readonly warningParams = { count: this.data.dependentCount };

  onConfirm(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
