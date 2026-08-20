import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

/**
 * Public routes and guarded routes are kept in separate blocks (FR-016).
 *
 * Screens land in later tasks; the shape is fixed here so they are added rather than
 * restructured. Note that sign-up is reachable but invitation-gated at the server — the pilot
 * is not open to public registration (FR-033).
 */
export const routes: Routes = [
  // --- public ---
  {
    path: 'auth',
    children: [
      { path: 'sign-in', loadComponent: () => import('./features/auth/sign-in/sign-in.component').then((m) => m.SignInComponent) },
      { path: '', pathMatch: 'full', redirectTo: 'sign-in' },
    ],
  },

  // --- guarded ---
  {
    path: '',
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'home' },
      { path: 'home', loadComponent: () => import('./layout/home/home.component').then((m) => m.HomeComponent) },
    ],
  },

  { path: '**', redirectTo: '' },
];
