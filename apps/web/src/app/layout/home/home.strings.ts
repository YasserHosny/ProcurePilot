export const HOME_STRINGS = {
  welcomePrefix: 'Welcome to',
  workspaceReadyBadge: 'Isolated Workspace Active',
  heroDescription: 'Your business workspace is provisioned with database-level tenant isolation, role-based access control, and financial configurations.',
  cardsSectionTitle: 'Workspace Information',
  
  cardTenantTitle: 'Tenant & Security',
  cardTenantSubtitle: 'Data isolation & multi-tenancy',
  labelTenantId: 'Tenant ID',
  labelSlug: 'Workspace Slug',
  labelCreatedAt: 'Created At',
  labelIsolation: 'Isolation Level',
  valIsolation: 'PostgreSQL Row-Level Security (FORCED)',

  cardConfigTitle: 'Regional & Financial Settings',
  cardConfigSubtitle: 'Immutable baseline configuration',
  labelRegion: 'Region',
  labelCurrency: 'Primary Currency',
  labelTaxModel: 'Tax Model',
  labelDefaultLocale: 'Default Locale',

  cardMemberTitle: 'Current User Authority',
  cardMemberSubtitle: 'Role and session credentials',
  labelEmail: 'Email Address',
  labelRole: 'Assigned Role',
  labelMfa: 'Multi-Factor Auth',
  valMfaEnabled: 'Enabled',
  valMfaDisabled: 'Not configured',

  emptyStateTitle: 'Procurement Intelligence Modules',
  emptyStateDescription: 'Platform Foundation (Chunk 4.1) establishes secure tenancy and authentication. Core procurement modules will be unlocked in upcoming releases.',

  step1Title: 'Platform Foundation',
  step1Desc: 'Tenant isolation, authentication, and RBAC skeleton.',
  step1Status: 'Active (Chunk 4.1)',

  step2Title: 'Quotation Inbox & OCR',
  step2Desc: 'Upload supplier PDF quotations with automated AI line-item extraction.',
  step2Status: 'Upcoming (Chunk 4.3)',

  step3Title: 'Smart Compare & Landed Cost',
  step3Desc: 'Automated pack-size normalisation and best-price recommendations.',
  step3Status: 'Upcoming (Chunk 4.5)',

  step4Title: 'Verified Savings Ledger',
  step4Desc: 'Auditable proof of purchasing savings vs baseline policies.',
  step4Status: 'Upcoming (Chunk 4.6)',

  roleOwner: 'Owner',
  roleBuyer: 'Buyer',
  roleBranchManager: 'Branch Manager',
  roleApprover: 'Approver',
  roleViewer: 'Viewer',
} as const;
