import { ChangeDetectionStrategy, Component } from '@angular/core';

import { LegalPageComponent } from '../legal-page/legal-page.component';

@Component({
  selector: 'app-privacy',
  standalone: true,
  imports: [LegalPageComponent],
  templateUrl: './privacy.component.html',
  styleUrl: './privacy.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PrivacyComponent {}
