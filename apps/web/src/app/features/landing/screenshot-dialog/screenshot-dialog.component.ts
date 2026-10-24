import { ChangeDetectionStrategy, Component, HostListener, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe } from '@ngx-translate/core';

import { I18nService } from '../../../core/i18n/i18n.service';

export interface ScreenshotDialogItem {
  readonly id: string;
  readonly src: string;
  readonly alt: string;
  readonly caption: string;
}

export interface ScreenshotDialogData {
  readonly items?: readonly ScreenshotDialogItem[];
  readonly initialIndex?: number;
  readonly src?: string;
  readonly alt?: string;
  readonly caption?: string;
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
  private readonly i18n = inject(I18nService);

  readonly items = signal<readonly ScreenshotDialogItem[]>(
    this.data.items && this.data.items.length > 0
      ? this.data.items
      : [
          {
            id: 'item-0',
            src: this.data.src ?? '',
            alt: this.data.alt ?? '',
            caption: this.data.caption ?? '',
          },
        ]
  );

  readonly currentIndex = signal<number>(this.data.initialIndex ?? 0);
  readonly currentItem = computed(() => this.items()[this.currentIndex()] ?? this.items()[0]);
  readonly isRtl = this.i18n.isRtl;

  prev(): void {
    if (this.currentIndex() > 0) {
      this.currentIndex.update((i) => i - 1);
    }
  }

  next(): void {
    if (this.currentIndex() < this.items().length - 1) {
      this.currentIndex.update((i) => i + 1);
    }
  }

  @HostListener('keydown', ['$event'])
  handleKeyDown(event: KeyboardEvent): void {
    const isRtl = this.isRtl();
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      if (isRtl) {
        this.prev();
      } else {
        this.next();
      }
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      if (isRtl) {
        this.next();
      } else {
        this.prev();
      }
    }
  }
}
