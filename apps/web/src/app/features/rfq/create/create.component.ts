import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators, FormArray } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule } from '@ngx-translate/core';
import { RfqApi } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { Product, Supplier } from '../../../core/api/models';

@Component({
  selector: 'app-rfq-create',
  standalone: true,
  imports: [
    CommonModule, 
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatProgressSpinnerModule,
    TranslateModule
  ],
  templateUrl: './create.component.html',
  styleUrl: './create.component.scss'
})
export class RfqCreateComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly rfqApi = inject(RfqApi);
  private readonly apiService = inject(ApiService);

  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly form = this.fb.nonNullable.group({
    lines: this.fb.array([
      this.fb.nonNullable.group({
        workspace_product_id: ['', Validators.required],
        quantity: ['', [Validators.required, Validators.min(0.01)]],
      })
    ], Validators.required),
    supplierIds: [[] as string[], Validators.required],
    neededByDate: ['', Validators.required],
    tenantTerms: [''],
  });

  readonly isSaving = signal(false);
  readonly isSending = signal(false);
  readonly rfqId = signal<string | null>(null);
  readonly rfqStatus = signal<'draft' | 'sent' | null>(null);
  readonly rejectedSuppliers = signal<{ supplier_id: string; reason: string }[]>([]);

  ngOnInit(): void {
    this.apiService.products({ limit: 100, status: 'active' }).subscribe(res => {
      this.products.set(res.items);
    });
    this.apiService.suppliers({ limit: 100, status: 'active' }).subscribe(res => {
      // Filter out suppliers with no contact_email as requested in the prompt
      this.suppliers.set(res.items.filter(s => !!s.contact_email));
    });
  }

  get linesFormArray() {
    return this.form.get('lines') as FormArray;
  }

  addLine() {
    this.linesFormArray.push(
      this.fb.nonNullable.group({
        workspace_product_id: ['', Validators.required],
        quantity: ['', [Validators.required, Validators.min(0.01)]],
      })
    );
  }

  removeLine(index: number) {
    if (this.linesFormArray.length > 1) {
      this.linesFormArray.removeAt(index);
    }
  }

  onSave() {
    if (this.form.invalid) return;

    this.isSaving.set(true);
    this.rejectedSuppliers.set([]);
    
    const val = this.form.getRawValue();
    const payload = {
      lines: val.lines,
      recipient_supplier_ids: val.supplierIds,
      needed_by_date: val.neededByDate,
      tenant_terms: val.tenantTerms || undefined,
    };

    this.rfqApi.createRfq(payload).subscribe({
      next: (res) => {
        this.rfqId.set(res.rfq.id);
        this.rfqStatus.set(res.rfq.status as 'draft' | 'sent');
        this.rejectedSuppliers.set(res.rejected_recipients);
        this.isSaving.set(false);
      },
      error: () => {
        this.isSaving.set(false);
      }
    });
  }

  onSend() {
    const id = this.rfqId();
    if (!id) return;
    
    this.isSending.set(true);
    this.rfqApi.sendRfq(id).subscribe({
      next: (res) => {
        this.rfqStatus.set(res.rfq.status as 'draft' | 'sent');
        this.isSending.set(false);
      },
      error: () => {
        this.isSending.set(false);
      }
    });
  }
}
