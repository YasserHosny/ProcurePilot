import { Routes } from '@angular/router';

import { authGuard, roleGuard } from './core/auth/auth.guard';

/**
 * Public routes and guarded routes are kept in separate blocks (FR-016).
 *
 * Sign-up is reachable but invitation-gated at the server (FR-033).
 * Guarded routes render inside the authenticated shell.
 */
export const routes: Routes = [
  // --- public routes ---
  {
    path: 'auth',
    children: [
      {
        path: 'sign-in',
        loadComponent: () =>
          import('./features/auth/sign-in/sign-in.component').then((m) => m.SignInComponent),
      },
      {
        path: 'password-reset',
        loadComponent: () =>
          import('./features/auth/password-reset/password-reset.component').then(
            (m) => m.PasswordResetComponent,
          ),
      },
      { path: '', pathMatch: 'full', redirectTo: 'sign-in' },
    ],
  },
  {
    path: 'onboarding',
    children: [
      {
        path: 'signup',
        loadComponent: () =>
          import('./features/onboarding/signup/signup.component').then((m) => m.SignupComponent),
      },
      {
        path: 'accept-invitation',
        loadComponent: () =>
          import('./features/onboarding/accept-invitation/accept-invitation.component').then(
            (m) => m.AcceptInvitationComponent,
          ),
      },
      { path: '', pathMatch: 'full', redirectTo: 'signup' },
    ],
  },

  // --- guarded shell ---
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'home' },
      {
        path: 'home',
        loadComponent: () =>
          import('./layout/home/home.component').then((m) => m.HomeComponent),
      },
      {
        path: 'team',
        canActivate: [roleGuard('owner')],
        loadComponent: () =>
          import('./features/team/team.component').then((m) => m.TeamComponent),
      },
    ],
  },

  { path: '**', redirectTo: '' },
];
