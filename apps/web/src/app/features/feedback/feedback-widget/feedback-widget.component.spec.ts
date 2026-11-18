import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { OverlayContainer } from '@angular/cdk/overlay';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { SessionService } from '../../../core/auth/session.service';
import { I18nService } from '../../../core/i18n';
import { FeedbackDraftStore } from '../feedback-draft.store';
import { FeedbackDialogComponent } from './feedback-dialog.component';
import { FeedbackWidgetComponent } from './feedback-widget.component';

describe('FeedbackWidgetComponent (FR-001, FR-010, FR-011)', () => {
  let fixture: ComponentFixture<FeedbackWidgetComponent>;
  let overlay: HTMLElement;
  let draft: FeedbackDraftStore;
  const member = signal<{ id: string } | null>({ id: 'user-a' });
  const tenant = signal<{ id: string } | null>({ id: 'tenant-1' });

  const fab = (): HTMLButtonElement =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-test="fab"]')!;
  const dialog = (): HTMLElement | null => overlay.querySelector('[role="dialog"]');

  beforeEach(async () => {
    member.set({ id: 'user-a' });
    tenant.set({ id: 'tenant-1' });
    await TestBed.configureTestingModule({
      imports: [FeedbackWidgetComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        provideTranslateService(),
        { provide: I18nService, useValue: { currentLocale: signal('en') } },
        { provide: SessionService, useValue: { currentMember: member, tenant } },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    overlay = TestBed.inject(OverlayContainer).getContainerElement();
    draft = TestBed.inject(FeedbackDraftStore);
    draft.reset();
    fixture = TestBed.createComponent(FeedbackWidgetComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    draft.reset();
    TestBed.inject(OverlayContainer).ngOnDestroy();
  });

  it('renders a floating button named for screen readers', () => {
    expect(fab()).not.toBeNull();
    expect(fab().getAttribute('aria-label')).toBe(enCatalog.feedback.widget.open);
    expect(fab().getAttribute('aria-haspopup')).toBe('dialog');
  });

  it('opens the feedback dialog with the notice visible', async () => {
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(dialog()).not.toBeNull();
    expect(dialog()!.getAttribute('aria-modal')).toBe('true');
    expect(overlay.textContent).toContain(enCatalog.feedback.notice);
  });

  it('does not open a second dialog on a repeated click', async () => {
    fab().click();
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(overlay.querySelectorAll('[role="dialog"]').length).toBe(1);
  });

  it('closes from the Close button and returns focus to the button', async () => {
    fab().focus();
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();

    overlay.querySelector<HTMLButtonElement>('[data-test="close"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(fab());
  });

  it('closes on Escape', async () => {
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();
    dialog()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(dialog()).toBeNull();
  });

  it('marks the button when a draft is waiting, and keeps it after the dialog is closed', async () => {
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-test="draft-dot"]')).toBeNull();
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();
    draft.text.set('half written');
    overlay.querySelector<HTMLButtonElement>('[data-test="close"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('[data-test="draft-dot"]')).not.toBeNull();
    expect(fab().getAttribute('aria-label')).toContain(enCatalog.feedback.widget.draftBadge);
    expect(draft.text()).toBe('half written');
  });

  it('does not show or reopen one member\'s draft to another member', () => {
    fab().click();
    draft.text.set('private');
    fixture.detectChanges();
    member.set({ id: 'user-b' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-test="draft-dot"]')).toBeNull();
  });

  it('passes afterCapture: true on the next open after a capture close, and not on the open after that', async () => {
    const dialogService = TestBed.inject(MatDialog);
    spyOn(dialogService, 'open').and.callThrough();

    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(dialogService.open).toHaveBeenCalledWith(
      FeedbackDialogComponent,
      jasmine.objectContaining({ data: undefined }),
    );

    overlay.querySelector<HTMLButtonElement>('[data-test="hide-to-capture"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    // Next open: should have afterCapture: true
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(dialogService.open).toHaveBeenCalledWith(
      FeedbackDialogComponent,
      jasmine.objectContaining({ data: { afterCapture: true } }),
    );

    overlay.querySelector<HTMLButtonElement>('[data-test="close"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    // Open after that: should not have afterCapture
    fab().click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(dialogService.open).toHaveBeenCalledWith(
      FeedbackDialogComponent,
      jasmine.objectContaining({ data: undefined }),
    );
  });
});
