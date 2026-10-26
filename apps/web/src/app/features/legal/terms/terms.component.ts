import { ChangeDetectionStrategy, Component } from '@angular/core';

import { LegalPageComponent } from '../legal-page/legal-page.component';

@Component({
  selector: 'app-terms',
  standalone: true,
  imports: [LegalPageComponent],
  templateUrl: './terms.component.html',
  styleUrl: './terms.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TermsComponent {}
