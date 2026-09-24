import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, Validators, FormArray } from '@angular/forms';
import { RfqApi } from '../rfq-api';

@Component({
  selector: 'app-rfq-create',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './create.component.html',
  styleUrl: './create.component.scss'
})
export class RfqCreateComponent {
  private readonly fb = inject(FormBuilder);
  private readonly rfqApi = inject(RfqApi);

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
