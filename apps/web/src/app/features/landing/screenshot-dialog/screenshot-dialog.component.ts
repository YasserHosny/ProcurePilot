import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe } from '@ngx-translate/core';

export interface ScreenshotDialogData {
  readonly src: string;
  readonly alt: string;
  readonly caption: string;
}

@Component({
  selector: 'app-screenshot-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: './screenshot-dialog.component.html',
  styleUrl: './screenshot-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScreenshotDialogComponent {
  readonly dialogRef = inject(MatDialogRef<ScreenshotDialogComponent>);
  readonly data: ScreenshotDialogData = inject(MAT_DIALOG_DATA);
}
