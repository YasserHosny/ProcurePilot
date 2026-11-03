import { OverlayContainer } from '@angular/cdk/overlay';
import { ApplicationRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';

import { CatalogueConfirmDialogComponent, ConfirmDialogData } from './confirm-dialog.component';

describe('CatalogueConfirmDialogComponent accessibility', () => {
  let dialog: MatDialog;
  let overlay: HTMLElement;
  const data: ConfirmDialogData = {
    titleKey: 'confirm.title', messageKey: 'confirm.message', messageParams: { name: 'Draft' },
    confirmKey: 'confirm.accept', cancelKey: 'confirm.cancel',
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MatDialogModule, CatalogueConfirmDialogComponent],
      providers: [provideNoopAnimations(), provideTranslateService()],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', { confirm: {
      title: 'Confirm deletion', message: 'Delete {{name}}?',
      warning: 'This cannot be undone.', accept: 'Delete', cancel: 'Cancel',
    } });
    translate.setTranslation('ar', { confirm: {
      title: 'تأكيد الحذف', message: 'حذف {{name}}؟',
      warning: 'لا يمكن التراجع عن هذا الإجراء.', accept: 'حذف', cancel: 'إلغاء',
    } });
    translate.use('en');
    dialog = TestBed.inject(MatDialog);
    overlay = TestBed.inject(OverlayContainer).getContainerElement();
  });

  afterEach(() => dialog.closeAll());

  async function open(overrides: Partial<ConfirmDialogData> = {}, describedBy?: string) {
    const ref = dialog.open(CatalogueConfirmDialogComponent, {
      data: { ...data, ...overrides }, ariaDescribedBy: describedBy,
    });
    ref.componentRef!.changeDetectorRef.detectChanges();
    await TestBed.inject(ApplicationRef).whenStable();
    const container = overlay.querySelector<HTMLElement>('.mat-mdc-dialog-container')!;
    return { ref, container };
  }

  for (const lang of ['en', 'ar']) {
    it(`describes the modal with its translated message in ${lang}`, async () => {
      TestBed.inject(TranslateService).use(lang);
      const { container } = await open();
      expect(container.getAttribute('aria-modal')).toBe('true');
      const message = container.querySelector<HTMLElement>('.dialog-message')!;
      expect(message.id).toBeTruthy();
      expect(container.getAttribute('aria-describedby')?.split(/\s+/)).toContain(message.id);
      expect(document.getElementById(message.id)?.textContent?.trim())
        .toBe(lang === 'en' ? 'Delete Draft?' : 'حذف Draft؟');
    });
  }

  it('appends message and warning ids to an existing description', async () => {
    const { container } = await open({ warningKey: 'confirm.warning' }, 'existing-description');
    const ids = container.getAttribute('aria-describedby')!.split(/\s+/);
    expect(ids).toContain('existing-description');
    for (const selector of ['.dialog-message', '.dialog-warning']) {
      const element = container.querySelector<HTMLElement>(selector)!;
      expect(element.id).toBeTruthy();
      expect(ids).toContain(element.id);
    }
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('assigns distinct message ids to dialogs opened in sequence', async () => {
    const first = await open();
    const firstId = first.container.querySelector('.dialog-message')!.id;
    first.ref.close();
    await TestBed.inject(ApplicationRef).whenStable();
    const second = await open();
    const secondId = second.container.querySelector('.dialog-message')!.id;
    expect(firstId).toBeTruthy();
    expect(secondId).toBeTruthy();
    expect(secondId).not.toBe(firstId);
  });

  it('keeps the default first-button focus and cancel result', async () => {
    const { ref, container } = await open();
    const result = jasmine.createSpy('closed');
    ref.afterClosed().subscribe(result);
    const cancel = container.querySelector<HTMLButtonElement>('button')!;
    expect(document.activeElement).toBe(cancel);
    cancel.click();
    await TestBed.inject(ApplicationRef).whenStable();
    expect(result).toHaveBeenCalledWith(false);
  });
});
