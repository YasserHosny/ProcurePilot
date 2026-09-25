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
        // R2.4 Supplier IQ — supplier scorecard (must precede the generic :id route)
        path: 'suppliers/:id/scorecard',
        loadComponent: () =>
          import('./features/catalogue/supplier-scorecard/supplier-scorecard.component').then(
            (m) => m.SupplierScorecardComponent,
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
        path: 'supplier-risk',
        loadComponent: () =>
          import('./features/supplier-risk/risk-queue/risk-queue.component').then(
            (m) => m.RiskQueueComponent,
          ),
      },
      {
        path: 'analyst',
        loadComponent: () =>
          import('./features/analyst/conversation/conversation.component').then(
            (m) => m.AnalystConversationComponent,
          ),
      },
      {
        path: 'analyst/history',
        loadComponent: () =>
          import('./features/analyst/history/history.component').then(
            (m) => m.AnalystHistoryComponent,
          ),
      },
      {
        path: 'analyst/:conversationId',
        loadComponent: () =>
          import('./features/analyst/conversation/conversation.component').then(
            (m) => m.AnalystConversationComponent,
          ),
      },
      {
        path: 'negotiation-briefs/:id',
        loadComponent: () =>
          import('./features/supplier-risk/brief-detail/brief-detail.component').then(
            (m) => m.BriefDetailComponent,
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
      {
        path: 'orders',
        loadComponent: () =>
          import('./features/orders/order-list/order-list.component').then(
            (m) => m.OrderListComponent,
          ),
      },
      {
        path: 'orders/:id',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/orders/order-detail/order-detail.component').then(
            (m) => m.OrderDetailComponent,
          ),
      },
      // --- RFQ sourcing (R4.3) ---
      {
        path: 'rfq/create',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/rfq/create/create.component').then((m) => m.RfqCreateComponent),
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
      {
        path: 'forecasting',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/forecasting/reorder-queue/reorder-queue.component').then(
            (m) => m.ReorderQueueComponent,
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
      // --- reports center (R2.5) ---
      {
        path: 'reports',
        loadComponent: () =>
          import('./features/reports/reports-center/reports-center.component').then(
            (m) => m.ReportsCenterComponent,
          ),
      },
      {
        path: 'reports/schedule-form',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/reports/schedule-form/schedule-form.component').then(
            (m) => m.ScheduleFormComponent,
          ),
      },
      {
        path: 'reports/digest-settings',
        loadComponent: () =>
          import('./features/reports/digest-settings/digest-settings.component').then(
            (m) => m.DigestSettingsComponent,
          ),
      },
      // --- automated ingestion (R3.0) ---
      {
        path: 'ingestion',
        loadComponent: () =>
          import('./features/ingestion/dashboard/dashboard.component').then(
            (m) => m.DashboardComponent,
          ),
      },
      {
        path: 'ingestion/email-config',
        loadComponent: () =>
          import('./features/ingestion/email-config/email-config.component').then(
            (m) => m.EmailConfigComponent,
          ),
      },
      {
        path: 'ingestion/email-log',
        loadComponent: () =>
          import('./features/ingestion/email-log/email-log.component').then(
            (m) => m.EmailLogComponent,
          ),
      },
      {
        path: 'ingestion/capture',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/ingestion/capture/capture.component').then(
            (m) => m.CaptureComponent,
          ),
      },
      {
        path: 'ingestion/catalogue-import',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/ingestion/catalogue-import/catalogue-import.component').then(
            (m) => m.CatalogueImportComponent,
          ),
      },
      {
        path: 'ingestion/refresh-schedules',
        canActivate: [roleGuard('owner', 'buyer')],
        loadComponent: () =>
          import('./features/ingestion/refresh-schedules/refresh-schedules.component').then(
            (m) => m.RefreshSchedulesComponent,
          ),
      },
      // --- accounting integration (R3.1) ---
      {
        path: 'accounting',
        loadComponent: () =>
          import(
            './features/accounting/connection-settings/connection-settings.component'
          ).then((m) => m.ConnectionSettingsComponent),
      },
      {
        path: 'accounting/bills',
        loadComponent: () =>
          import('./features/accounting/bills/bills.component').then(
            (m) => m.BillsComponent,
          ),
      },
      {
        path: 'accounting/discrepancies',
        loadComponent: () =>
          import(
            './features/accounting/discrepancies/discrepancies.component'
          ).then((m) => m.DiscrepanciesComponent),
      },
      // --- pos / inventory integration (R3.2) ---
      {
        path: 'pos',
        loadComponent: () =>
          import(
            './features/pos/connection-settings/connection-settings.component'
          ).then((m) => m.ConnectionSettingsComponent),
      },
      {
        path: 'pos/signals',
        loadComponent: () =>
          import(
            './features/pos/signals-review/signals-review.component'
          ).then((m) => m.SignalsReviewComponent),
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
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/settings.component').then((m) => m.SettingsComponent),
      },
      // --- requests & approvals (Chunk R2.1) ---
      {
        path: 'requests',
        loadComponent: () =>
          import('./features/requests/request-list/request-list.component').then(
            (m) => m.RequestListComponent,
          ),
      },
      {
        path: 'requests/new',
        loadComponent: () =>
          import('./features/requests/request-form/request-form.component').then(
            (m) => m.RequestFormComponent,
          ),
      },
      {
        path: 'requests/:id',
        loadComponent: () =>
          import('./features/requests/request-form/request-form.component').then(
            (m) => m.RequestFormComponent,
          ),
      },
      {
        path: 'approvals',
        loadComponent: () =>
          import('./features/approvals/approval-queue/approval-queue.component').then(
            (m) => m.ApprovalQueueComponent,
          ),
      },
    ],
  },

  { path: '**', redirectTo: '' },
];
