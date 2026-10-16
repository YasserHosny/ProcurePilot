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
import { Product, Supplier } from '../../../core/api/models';

describe('RfqCreateComponent', () => {
  let component: RfqCreateComponent;
  let fixture: ComponentFixture<RfqCreateComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let apiSpy: jasmine.SpyObj<ApiService>;

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
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
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

  it('sends the picked local calendar date and shows API errors', () => {
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
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain('Invalid needed-by date');
  });
});
