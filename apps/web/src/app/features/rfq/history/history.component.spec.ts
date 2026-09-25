import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HistoryComponent } from './history.component';
import { RfqApi, RfqSummary, RfqList } from '../rfq-api';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule } from '@ngx-translate/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { HttpErrorResponse } from '@angular/common/http';

import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

describe('HistoryComponent', () => {
  let component: HistoryComponent;
  let fixture: ComponentFixture<HistoryComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let routerSpy: jasmine.SpyObj<Router>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockRfqs: RfqSummary[] = [
    {
      id: 'rfq-1',
      status: 'sent',
      needed_by_date: '2026-10-01',
      created_at: '2026-09-25T10:00:00Z',
      recipient_count: 5,
      response_count: 2,
      converted_purchase_request_id: null
    },
    {
      id: 'rfq-2',
      status: 'converted',
      needed_by_date: '2026-10-05',
      created_at: '2026-09-24T10:00:00Z',
      recipient_count: 3,
      response_count: 3,
      converted_purchase_request_id: 'pr-1'
    }
  ];

  const mockRfqList: RfqList = {
    items: mockRfqs,
    next_cursor: null
  };

  beforeEach(async () => {
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['listRfqs']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    rfqApiSpy.listRfqs.and.returnValue(of(mockRfqList));

    await TestBed.configureTestingModule({
      imports: [HistoryComponent, TranslateModule.forRoot(), NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: RfqApi, useValue: rfqApiSpy },
        { provide: Router, useValue: routerSpy },
        { provide: MatSnackBar, useValue: snackBarSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(HistoryComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // triggers ngOnInit
  });

  it('should create and load RFQs', () => {
    expect(component).toBeTruthy();
    expect(rfqApiSpy.listRfqs).toHaveBeenCalled();
    expect(component.rfqs().length).toBe(2);
    expect(component.loading()).toBeFalse();
  });

  it('should navigate to compare view for non-converted RFQ', () => {
    component.onRowClick(mockRfqs[0]);
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/rfq/compare', 'rfq-1']);
  });

  it('should navigate to request view for converted RFQ', () => {
    component.onRowClick(mockRfqs[1]);
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'pr-1']);
  });

  it('should display error snackbar on load failure', () => {
    rfqApiSpy.listRfqs.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    component.loadRfqs();
    expect(component.loading()).toBeFalse();
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      jasmine.any(String),
      jasmine.any(String),
      { duration: 5000 },
    );
  });

  it('should render table rows', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('tr.mat-mdc-row');
    expect(rows.length).toBe(2);
  });
});
