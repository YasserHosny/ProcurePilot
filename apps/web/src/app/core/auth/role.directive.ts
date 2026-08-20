import {
  Directive,
  Input,
  TemplateRef,
  ViewContainerRef,
  effect,
  inject,
  signal,
} from '@angular/core';

import type { Role } from '../api/models';
import { SessionService } from './session.service';

/**
 * Structural directive hiding DOM elements the active role may not use.
 *
 * Usage:
 *   <button *appRole="'owner'">Invite Member</button>
 *   <div *appRole="['owner', 'buyer']">Purchasing Actions</div>
 *
 * NOTE: This is a DISPLAY CONVENIENCE, NOT A SECURITY CONTROL.
 * The server refuses unauthorised actions regardless (research R9). Principle V puts the
 * tenancy boundary in the database for the same reason: a control that lives only in the client
 * is not a control.
 * Never rely on this directive as the sole protection for sensitive operations.
 */
@Directive({
  selector: '[appRole]',
  standalone: true,
})
export class RoleDirective {
  private readonly templateRef = inject(TemplateRef<unknown>);
  private readonly viewContainer = inject(ViewContainerRef);
  private readonly session = inject(SessionService);

  private readonly requiredRoles = signal<readonly Role[]>([]);
  private isViewCreated = false;

  @Input()
  set appRole(roles: Role | readonly Role[] | null | undefined) {
    if (!roles) {
      this.requiredRoles.set([]);
    } else if (Array.isArray(roles)) {
      this.requiredRoles.set(roles);
    } else {
      this.requiredRoles.set([roles as Role]);
    }
  }

  constructor() {
    effect(() => {
      const roles = this.requiredRoles();
      const userRole = this.session.role();

      const hasPermission = roles.length === 0 || (userRole !== null && roles.includes(userRole));

      if (hasPermission && !this.isViewCreated) {
        this.viewContainer.createEmbeddedView(this.templateRef);
        this.isViewCreated = true;
      } else if (!hasPermission && this.isViewCreated) {
        this.viewContainer.clear();
        this.isViewCreated = false;
      }
    });
  }
}
