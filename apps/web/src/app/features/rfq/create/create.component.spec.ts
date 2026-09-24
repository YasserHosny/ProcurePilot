import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RfqCreateComponent } from './create.component';
import { RfqApi, Rfq } from '../rfq-api';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

describe('RfqCreateComponent', () => {
  let component: RfqCreateComponent;
  let fixture: ComponentFixture<RfqCreateComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;

  beforeEach(async () => {
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['createRfq', 'sendRfq']);
    
    await TestBed.configureTestingModule({
      imports: [RfqCreateComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: RfqApi, useValue: rfqApiSpy }
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
      neededByDate: '2026-12-01'
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
});
