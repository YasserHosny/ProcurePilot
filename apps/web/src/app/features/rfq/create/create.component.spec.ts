import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RfqCreateComponent } from './create.component';
import { RfqApi, Rfq } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule } from '@ngx-translate/core';
import { TranslateService } from '@ngx-translate/core';
import { Product, Supplier } from '../../../core/api/models';

describe('RfqCreateComponent', () => {
  let component: RfqCreateComponent;
  let fixture: ComponentFixture<RfqCreateComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let apiSpy: jasmine.SpyObj<ApiService>;
  let translate: TranslateService;

  beforeEach(async () => {
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['createRfq', 'sendRfq']);
    apiSpy = jasmine.createSpyObj('ApiService', ['products', 'suppliers']);
    
    apiSpy.products.and.returnValue(of({ items: [{ id: 'prod-1', tenant_name: 'Product 1' } as Product], next_cursor: null }));
    apiSpy.suppliers.and.returnValue(of({ items: [{ id: 'sup-1', name: 'Supplier 1', contact_email: 'sup@test.com' } as Supplier], next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [RfqCreateComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: RfqApi, useValue: rfqApiSpy },
        { provide: ApiService, useValue: apiSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(RfqCreateComponent);
    component = fixture.componentInstance;
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', { rfq: { create: {
      validationError: 'Please check the following RFQ fields:',
      neededByDateLabel: 'Needed By Date',
      saveError: 'SAVE FALLBACK',
      errors: { notFound: 'The requested RFQ resource could not be found.' },
    } } }, true);
    translate.use('en');
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('rejects tenant terms over 4000 characters and accepts exactly 4000', () => {
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 11, 1),
      tenantTerms: 'x'.repeat(4001),
    });

    fixture.detectChanges();
    expect(component.form.controls.tenantTerms.invalid).toBeTrue();
    expect((fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBeTrue();

    component.form.controls.tenantTerms.setValue('x'.repeat(4000));
    fixture.detectChanges();
    expect(component.form.controls.tenantTerms.valid).toBeTrue();
    expect(component.form.valid).toBeTrue();
  });

  it('should show rejection reason for suppliers without email', () => {
    rfqApiSpy.createRfq.and.returnValue(of({
      rfq: { id: 'rfq-1', status: 'draft' } as Rfq,
      lines: [],
      recipients: [],
      rejected_recipients: [{ supplier_id: 'sup-1', reason: 'missing_contact_email' }]
    }));

    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 11, 1)
    });

    component.onSave();
    
    expect(component.rejectedSuppliers().length).toBe(1);
    expect(component.rejectedSuppliers()[0].reason).toBe('missing_contact_email');
    expect(component.rfqId()).toBe('rfq-1');
  });
  
  it('should call sendRfq when explicit send is triggered', () => {
    component.rfqId.set('rfq-1');
    rfqApiSpy.sendRfq.and.returnValue(of({
      rfq: { id: 'rfq-1', status: 'sent' } as Rfq,
      recipients: []
    }));
    
    component.onSend();
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-1');
  });

  it('sends the picked local calendar date and uses the fallback for an unknown error code', () => {
    rfqApiSpy.createRfq.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 422, error: { code: 'invalid_date', message: 'Invalid needed-by date' }
    })));
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'], neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    expect(rfqApiSpy.createRfq).toHaveBeenCalledWith(jasmine.objectContaining({ needed_by_date: '2026-10-20' }));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('SAVE FALLBACK');
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).not.toContain('Invalid needed-by date');
  });

  it('translates validation errors and known field labels', () => {
    rfqApiSpy.createRfq.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 422,
      error: {
        code: 'validation.invalid_request',
        message: 'Request validation failed.',
        details: [{ loc: ['body', 'needed_by_date'], msg: 'Invalid date', type: 'date_parsing' }],
      },
    })));
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'], neededByDate: new Date(2026, 9, 20),
    });

    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('Please check the following RFQ fields:');
    expect(alert.textContent).toContain('Needed By Date');
    expect(alert.textContent).not.toContain('Request validation failed.');
  });

  it('shows translated not-found text instead of the server message', () => {
    rfqApiSpy.createRfq.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 404, error: { code: 'not_found', message: 'Resource was not found.' },
    })));
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'], neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('The requested RFQ resource could not be found.');
    expect(alert.textContent).not.toContain('Resource was not found.');
  });

  it('uses the save fallback for an unknown server code', () => {
    rfqApiSpy.createRfq.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 400, error: { code: 'unknown.code', message: 'Untrusted server detail' },
    })));
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'], neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('SAVE FALLBACK');
    expect(alert.textContent).not.toContain('Untrusted server detail');
  });
});
