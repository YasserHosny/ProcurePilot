import { Direction, Directionality } from '@angular/cdk/bidi';
import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export type LayoutDirection = 'ltr' | 'rtl';

/**
 * Service to manage application-wide text direction and wire Angular CDK Directionality.
 *
 * T064: Wires Angular CDK's Directionality to the active language and sets `dir` and `lang`
 * on the document root (<html>) so that Angular Material components mirror correctly.
 */
@Injectable({ providedIn: 'root' })
export class DirectionService {
  private readonly document = inject(DOCUMENT);
  private readonly cdkDirectionality = inject(Directionality);

  private readonly direction = signal<LayoutDirection>('ltr');

  readonly currentDirection = this.direction.asReadonly();
  readonly isRtl = computed(() => this.direction() === 'rtl');

  /**
   * Updates directionality across the DOM document and Angular CDK.
   */
  setDirection(dir: LayoutDirection, lang?: string): void {
    this.direction.set(dir);

    // Update document element attributes
    const docElement = this.document.documentElement;
    if (docElement) {
      docElement.setAttribute('dir', dir);
      if (lang) {
        docElement.setAttribute('lang', lang);
      }
    }

    if (this.document.body) {
      this.document.body.setAttribute('dir', dir);
    }

    // Wire CDK Directionality so overlays, dialogs, menus mirror
    const cdkDir = dir as Direction;
    if (this.cdkDirectionality.value !== cdkDir) {
      (this.cdkDirectionality as { value: Direction }).value = cdkDir;
      this.cdkDirectionality.change.emit(cdkDir);
    }
  }
}
