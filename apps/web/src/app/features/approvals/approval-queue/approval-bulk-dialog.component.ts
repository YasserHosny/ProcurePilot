import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslatePipe } from '@ngx-translate/core';
import type { Money } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';

export interface ApprovalBulkDialogData {
  readonly decision: 'approved' | 'rejected';
  readonly title: string;
  readonly totals: readonly Money[];
  readonly incomplete: boolean;
}
export interface ApprovalBulkDialogResult { readonly confirmed: boolean; readonly comment: string | null; }

@Component({
  selector: 'app-approval-bulk-dialog', standalone: true,
  imports: [FormsModule, MatButtonModule, MatDialogModule, MatFormFieldModule, MatInputModule, TranslatePipe],
  templateUrl: './approval-bulk-dialog.component.html',
  styleUrl: './approval-bulk-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApprovalBulkDialogComponent {
  readonly data = inject<ApprovalBulkDialogData>(MAT_DIALOG_DATA);
  private readonly dialogRef = inject(MatDialogRef<ApprovalBulkDialogComponent, ApprovalBulkDialogResult>);
  private readonly format = inject(FormatService);
  readonly comment = signal('');
  readonly invalid = computed(() => this.comment().length > 2000 || (this.data.decision === 'rejected' && !this.comment().trim()));
  money(value: Money): string { return this.format.formatCurrencyAmount(value, 'en'); }
  confirm(): void {
    if (!this.invalid()) this.dialogRef.close({confirmed: true, comment: this.comment() || null});
  }
  cancel(): void { this.dialogRef.close({confirmed: false, comment: null}); }
}
