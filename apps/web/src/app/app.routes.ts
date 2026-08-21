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
      {
        path: 'plan',
        loadComponent: () =>
          import('./features/onboarding/plan-display/plan-display.component').then(
            (m) => m.PlanDisplayComponent,
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
        path: 'products',
        loadComponent: () =>
          import('./features/catalogue/product-list/product-list.component').then(
            (m) => m.ProductListComponent,
          ),
      },
      {
        path: 'products/new',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/catalogue/product-form/product-form.component').then(
            (m) => m.ProductFormComponent,
          ),
      },
      {
        path: 'products/:id',
        loadComponent: () =>
          import('./features/catalogue/product-form/product-form.component').then(
            (m) => m.ProductFormComponent,
          ),
      },
      {
        path: 'suppliers',
        loadComponent: () =>
          import('./features/catalogue/supplier-list/supplier-list.component').then(
            (m) => m.SupplierListComponent,
          ),
      },
      {
        path: 'suppliers/new',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/catalogue/supplier-form/supplier-form.component').then(
            (m) => m.SupplierFormComponent,
          ),
      },
      {
        path: 'suppliers/:id',
        loadComponent: () =>
          import('./features/catalogue/supplier-form/supplier-form.component').then(
            (m) => m.SupplierFormComponent,
          ),
      },
      {
        path: 'import',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/catalogue/import-wizard/import-wizard.component').then(
            (m) => m.ImportWizardComponent,
          ),
      },
      {
        path: 'team',
        canActivate: [roleGuard('owner')],
        loadComponent: () =>
          import('./features/team/team.component').then((m) => m.TeamComponent),
      },
      {
        path: 'quotations',
        loadComponent: () =>
          import('./features/quotations/review-queue/review-queue.component').then(
            (m) => m.ReviewQueueComponent,
          ),
      },
      {
        path: 'quotations/upload',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/quotations/upload/quotation-upload.component').then(
            (m) => m.QuotationUploadComponent,
          ),
      },
      {
        path: 'quotations/:id/review',
        loadComponent: () =>
          import('./features/quotations/quotation-review/quotation-review.component').then(
            (m) => m.QuotationReviewComponent,
          ),
      },
      {
        path: 'quotations/:id',
        loadComponent: () =>
          import('./features/quotations/quotation-review/quotation-review.component').then(
            (m) => m.QuotationReviewComponent,
          ),
      },
      {
        path: 'matching',
        loadComponent: () =>
          import('./features/matching/resolution-queue/resolution-queue.component').then(
            (m) => m.ResolutionQueueComponent,
          ),
      },
      {
        path: 'matching/tasks/:id',
        loadComponent: () =>
          import('./features/matching/match-resolution/match-resolution.component').then(
            (m) => m.MatchResolutionComponent,
          ),
      },
      {
        path: 'matching/:id',
        loadComponent: () =>
          import('./features/matching/match-resolution/match-resolution.component').then(
            (m) => m.MatchResolutionComponent,
          ),
      },
      // --- smart compare and intelligence (Chunk 4.5) ---
      {
        path: 'offers/compare',
        loadComponent: () =>
          import('./features/offers/compare/compare.component').then((m) => m.CompareComponent),
      },
      {
        path: 'offers/compare/:id',
        loadComponent: () =>
          import('./features/offers/compare/compare.component').then((m) => m.CompareComponent),
      },
      {
        path: 'compare',
        redirectTo: 'offers/compare',
        pathMatch: 'full',
      },
      {
        path: 'compare/:id',
        loadComponent: () =>
          import('./features/offers/compare/compare.component').then((m) => m.CompareComponent),
      },
      {
        path: 'offers/product-intelligence',
        loadComponent: () =>
          import('./features/offers/product-intelligence/product-intelligence.component').then(
            (m) => m.ProductIntelligenceComponent,
          ),
      },
      {
        path: 'offers/product-intelligence/:id',
        loadComponent: () =>
          import('./features/offers/product-intelligence/product-intelligence.component').then(
            (m) => m.ProductIntelligenceComponent,
          ),
      },
      {
        path: 'offers/basket-split',
        loadComponent: () =>
          import('./features/offers/basket-split/basket-split.component').then(
            (m) => m.BasketSplitComponent,
          ),
      },
      {
        path: 'offers/basket-split/:id',
        loadComponent: () =>
          import('./features/offers/basket-split/basket-split.component').then(
            (m) => m.BasketSplitComponent,
          ),
      },
      {
        path: 'alerts',
        loadComponent: () =>
          import('./features/alerts/alerts-inbox/alerts-inbox.component').then(
            (m) => m.AlertsInboxComponent,
          ),
      },
      // --- value proof & savings (Chunk 4.6) ---
      {
        path: 'savings',
        loadComponent: () =>
          import('./features/savings/savings-ledger/savings-ledger.component').then(
            (m) => m.SavingsLedgerComponent,
          ),
      },
      {
        path: 'savings/outcome-capture',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/savings/outcome-capture/outcome-capture.component').then(
            (m) => m.OutcomeCaptureComponent,
          ),
      },
      {
        path: 'savings/export',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/savings/export-savings/export-savings.component').then(
            (m) => m.ExportSavingsComponent,
          ),
      },
      {
        path: 'savings/export/:id',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/savings/export-savings/export-savings.component').then(
            (m) => m.ExportSavingsComponent,
          ),
      },
      {
        path: 'savings/:id/evidence',
        loadComponent: () =>
          import('./features/savings/saving-evidence/saving-evidence.component').then(
            (m) => m.SavingEvidenceComponent,
          ),
      },
      {
        path: 'savings/:id',
        loadComponent: () =>
          import('./features/savings/saving-evidence/saving-evidence.component').then(
            (m) => m.SavingEvidenceComponent,
          ),
      },
      {
        path: 'plan',
        loadComponent: () =>
          import('./features/onboarding/plan-display/plan-display.component').then(
            (m) => m.PlanDisplayComponent,
          ),
      },
    ],
  },

  { path: '**', redirectTo: '' },
];
