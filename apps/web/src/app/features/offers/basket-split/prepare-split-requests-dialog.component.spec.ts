import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { RequestsApiService } from '../../requests/requests-api';
import { OffersApiService } from '../offers-api';
import { PrepareSplitRequestsDialogComponent } from './prepare-split-requests-dialog.component';

describe('PrepareSplitRequestsDialogComponent (P-185)', () => {
  let fixture: ComponentFixture<PrepareSplitRequestsDialogComponent>;
  let api: jasmine.SpyObj<ApiService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['listBranches', 'listCostCentres']);
    await TestBed.configureTestingModule({
      imports: [PrepareSplitRequestsDialogComponent],
      providers: [
        provideTranslateService(),
        provideNoopAnimations(),
        { provide: ApiService, useValue: api },
        { provide: SessionService, useValue: { tenant: () => null } },
        { provide: OffersApiService, useValue: {} },
        { provide: RequestsApiService, useValue: {} },
        { provide: MatDialogRef, useValue: { close: () => undefined } },
        { provide: MAT_DIALOG_DATA, useValue: { basketId: 'b1', rfqId: 'r1' } },
      ],
    }).compileComponents();
    TestBed.inject(TranslateService).setTranslation('en', {
      basketSplit: { prepareRequests: { errors: { branchesLoadFailed: 'Branches could not be loaded.', costCentresLoadFailed: 'Cost centres could not be loaded.' } } },
    });
    TestBed.inject(TranslateService).use('en');
  });

  // Before: both loads failed silently and the dialog showed empty pickers with no explanation.
  it('says so when the branches cannot be loaded', () => {
    api.listBranches.and.returnValue(throwError(() => new Error('down')));
    api.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    fixture = TestBed.createComponent(PrepareSplitRequestsDialogComponent);
    fixture.detectChanges();

    const alert = (fixture.nativeElement as HTMLElement).querySelector('.dialog-error');
    expect(alert?.textContent).toContain('Branches could not be loaded.');
  });

  it('says so when the cost centres cannot be loaded', () => {
    api.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    api.listCostCentres.and.returnValue(throwError(() => new Error('down')));
    fixture = TestBed.createComponent(PrepareSplitRequestsDialogComponent);
    fixture.detectChanges();

    const alert = (fixture.nativeElement as HTMLElement).querySelector('.dialog-error');
    expect(alert?.textContent).toContain('Cost centres could not be loaded.');
  });
});
