import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CompareComponent } from './compare.component';
import { RfqApi, RfqResponseComparisonList, PrepareRequestResponse } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Branch, Supplier, Product } from '../../../core/api/models';

describe('CompareComponent (RFQ)', () => {
  let component: CompareComponent;
  let fixture: ComponentFixture<CompareComponent>;
  let mockRfqApi: jasmine.SpyObj<RfqApi>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockRouter: jasmine.SpyObj<Router>;
  let mockSnackBar: jasmine.SpyObj<MatSnackBar>;

  const dummyResponses: RfqResponseComparisonList = {
    items: [
      {
        id: 'resp-1',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-1',
        submitted_at: '2026-09-25T10:00:00Z',
        lines: [
          {
            workspace_product_id: 'prod-1',
            quoted_quantity: '10',
            quoted_unit_price_amount: '5.00',
            quoted_unit_price_currency: 'USD',
            pending_match: false
          }
        ]
      },
      {
        id: 'resp-2',
        rfq_id: 'rfq-1',
        supplier_id: 'supp-2',
        submitted_at: '2026-09-25T11:00:00Z',
        lines: [
          {
            workspace_product_id: null,
            quoted_quantity: '10',
            quoted_unit_price_amount: '4.50',
            quoted_unit_price_currency: 'USD',
            pending_match: true
          }
        ]
      }
    ]
  };

  beforeEach(async () => {
    mockRfqApi = jasmine.createSpyObj('RfqApi', ['listResponses', 'prepareRequest']);
    mockRfqApi.listResponses.and.returnValue(of(dummyResponses));
    mockRfqApi.prepareRequest.and.returnValue(of({ purchase_request_id: 'pr-1' } as PrepareRequestResponse));

    mockApiService = jasmine.createSpyObj('ApiService', ['listBranches', 'suppliers', 'products']);
    mockApiService.listBranches.and.returnValue(of({ items: [{ id: 'branch-1', name: 'Main Branch' }], next_cursor: null } as unknown as { items: Branch[], next_cursor: string | null }));
    mockApiService.suppliers.and.returnValue(of({ items: [{ id: 'supp-1', name: 'Supplier One' }], next_cursor: null } as unknown as { items: Supplier[], next_cursor: string | null }));
    mockApiService.products.and.returnValue(of({ items: [{ id: 'prod-1', tenant_name: 'Product One' }], next_cursor: null } as unknown as { items: Product[], next_cursor: string | null }));
    mockRouter = jasmine.createSpyObj('Router', ['navigate']);
    mockSnackBar = jasmine.createSpyObj('MatSnackBar', ['open']);
    mockSnackBar.open.and.returnValue({
      onAction: () => of(undefined),
    } as unknown as ReturnType<MatSnackBar['open']>);

    await TestBed.configureTestingModule({
      imports: [CompareComponent, TranslateModule.forRoot()],
      providers: [
        { provide: RfqApi, useValue: mockRfqApi },
        { provide: ApiService, useValue: mockApiService },
        { provide: Router, useValue: mockRouter },
        { provide: MatSnackBar, useValue: mockSnackBar },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of({ get: () => 'rfq-1' }),
          },
        },
        provideNoopAnimations(),
      ],
    })
    .overrideProvider(MatSnackBar, { useValue: mockSnackBar })
    .compileComponents();

    fixture = TestBed.createComponent(CompareComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load responses and resolve names on init', () => {
    expect(mockRfqApi.listResponses).toHaveBeenCalledWith('rfq-1');
    expect(mockApiService.listBranches).toHaveBeenCalled();
    expect(mockApiService.suppliers).toHaveBeenCalled();
    expect(mockApiService.products).toHaveBeenCalled();

    expect(component.responses().length).toBe(2);
    expect(component.selectedBranchId()).toBe('branch-1');
    expect(component.supplierNames()['supp-1']).toBe('Supplier One');
    expect(component.productNames()['prod-1']).toBe('Product One');
  });

  it('should disable prepare action for responses with pending match lines', () => {
    expect(component.isEligible(dummyResponses.items[0])).toBeTrue();
    expect(component.isEligible(dummyResponses.items[1])).toBeFalse();
  });

  it('should show error snackbar when preparing an ineligible response', () => {
    component.prepareRequest(dummyResponses.items[1]);
    expect(mockSnackBar.open).toHaveBeenCalledWith(
      jasmine.any(String),
      'OK',
      { duration: 3000 }
    );
    expect(mockRfqApi.prepareRequest).not.toHaveBeenCalled();
  });

  it('should call prepareRequest API and show success snackbar for eligible response', () => {
    const requiredDate = new Date();
    component.requiredByDate.set(requiredDate);
    
    component.prepareRequest(dummyResponses.items[0]);
    
    expect(mockRfqApi.prepareRequest).toHaveBeenCalledWith('rfq-1', {
      rfq_response_id: 'resp-1',
      branch_id: 'branch-1',
      required_by_date: requiredDate.toISOString().split('T')[0]
    });
    
    expect(mockSnackBar.open).toHaveBeenCalledWith(
      jasmine.any(String),
      jasmine.any(String),
      { duration: 5000 }
    );
  });
});
