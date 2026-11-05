import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideTranslateService, TranslateService } from '@ngx-translate/core';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApprovalBulkDialogComponent, type ApprovalBulkDialogData } from './approval-bulk-dialog.component';

describe('ApprovalBulkDialogComponent', () => {
  let fixture: ComponentFixture<ApprovalBulkDialogComponent>;
  let ref: jasmine.SpyObj<MatDialogRef<ApprovalBulkDialogComponent>>;
  let data: ApprovalBulkDialogData;
  beforeEach(async () => {
    data = {decision: 'rejected', title: 'Reject 2 requests?', totals: [{amount: '1', currency: 'EGP'}, {amount: '2', currency: 'SAR'}], incomplete: false};
    ref = jasmine.createSpyObj('MatDialogRef', ['close']);
    await TestBed.configureTestingModule({imports: [ApprovalBulkDialogComponent], providers: [
      provideTranslateService(), {provide: MAT_DIALOG_DATA, useFactory: () => data}, {provide: MatDialogRef, useValue: ref},
    ]}).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog); translate.setTranslation('ar', arCatalog); translate.use('en');
  });
  function render(): ApprovalBulkDialogComponent {
    fixture = TestBed.createComponent(ApprovalBulkDialogComponent); fixture.detectChanges(); return fixture.componentInstance;
  }
  it('requires one non-blank comment, caps it at 2000 and applies it verbatim to all requests', () => {
    const component = render();
    expect(fixture.nativeElement.querySelector('textarea').getAttribute('maxlength')).toBe('2000');
    for (const comment of ['', '  ', 'x'.repeat(2001)]) {
      component.comment.set(comment); fixture.detectChanges(); component.confirm();
      expect(component.invalid()).toBeTrue(); expect(ref.close).not.toHaveBeenCalled();
    }
    component.comment.set(' Reason '); fixture.detectChanges(); component.confirm();
    expect(ref.close).toHaveBeenCalledWith({confirmed: true, comment: ' Reason '});
    expect(fixture.nativeElement.textContent).toContain('EGP 1'); expect(fixture.nativeElement.textContent).toContain('SAR 2');
  });
  it('allows approval without a comment and returns cancellation without a decision', () => {
    data = {...data, decision: 'approved', title: 'Approve 2 requests?'};
    const component = render(); expect(fixture.nativeElement.querySelector('textarea')).toBeNull();
    component.confirm(); expect(ref.close).toHaveBeenCalledWith({confirmed: true, comment: null});
    component.cancel(); expect(ref.close).toHaveBeenCalledWith({confirmed: false, comment: null});
  });
  for (const locale of ['en', 'ar']) {
    it(`renders the dialog in ${locale} direction with Latin money digits`, () => {
      TestBed.inject(TranslateService).use(locale);
      data = {...data, title: (locale === 'ar' ? arCatalog : enCatalog).approvals.bulk.rejectTitle.two.replace('{{count}}', '2')};
      render();
      fixture.nativeElement.setAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr'); fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(locale === 'ar' ? arCatalog.approvals.bulk.comment : enCatalog.approvals.bulk.comment);
      expect(fixture.nativeElement.textContent).not.toMatch(/[٠-٩]/);
      expect(getComputedStyle(fixture.nativeElement).direction).toBe(locale === 'ar' ? 'rtl' : 'ltr');
    });
  }
});
