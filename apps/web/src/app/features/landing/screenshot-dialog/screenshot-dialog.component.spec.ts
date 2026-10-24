import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService } from '@ngx-translate/core';

import { ScreenshotDialogComponent, ScreenshotDialogData } from './screenshot-dialog.component';

describe('ScreenshotDialogComponent', () => {
  let component: ScreenshotDialogComponent;
  let fixture: ComponentFixture<ScreenshotDialogComponent>;
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<ScreenshotDialogComponent>>;

  const mockData: ScreenshotDialogData = {
    src: '/landing/en/01-quotation-review.jpg',
    alt: 'Demonstration screen: Quotation review',
    caption: 'Check extracted details beside the source document.',
  };

  beforeEach(async () => {
    dialogRefSpy = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [ScreenshotDialogComponent],
      providers: [
        provideTranslateService(),
        { provide: MAT_DIALOG_DATA, useValue: mockData },
        { provide: MatDialogRef, useValue: dialogRefSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ScreenshotDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('creates the dialog', () => {
    expect(component).toBeTruthy();
  });

  it('renders image with provided src and alt', () => {
    const img: HTMLImageElement = fixture.nativeElement.querySelector('.dialog-image');
    expect(img).toBeTruthy();
    expect(img.getAttribute('src')).toBe(mockData.src);
    expect(img.alt).toBe(mockData.alt);
  });

  it('renders caption via mat-dialog-title directive', () => {
    const titleEl: HTMLElement = fixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(titleEl).toBeTruthy();
    expect(titleEl.textContent?.trim()).toBe(mockData.caption);
  });

  it('has no redundant nested role="dialog"', () => {
    const nestedDialog = fixture.nativeElement.querySelector('[role="dialog"]');
    expect(nestedDialog).toBeNull();
  });

  it('closes the dialog when close button is clicked', () => {
    const closeBtn: HTMLButtonElement = fixture.nativeElement.querySelector('.dialog-close-btn');
    closeBtn.click();
    expect(dialogRefSpy.close).toHaveBeenCalled();
  });
});
