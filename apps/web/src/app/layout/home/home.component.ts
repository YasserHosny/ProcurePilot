import { Component, inject } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { Role } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [MatCardModule, MatIconModule, TranslatePipe],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);

  readonly member = this.session.currentMember;
  readonly tenant = this.session.tenant;

  formatRole(role: Role | null | undefined): string {
    if (!role) return '';
    return this.translate.instant(`common.roles.${role}`);
  }
}
