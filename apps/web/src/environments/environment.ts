export const environment = {
  production: false,
  apiBaseUrl: '/api/v1',
  // Empty locally; supplied at build time in deployed environments.
  sentryDsn: '',
  // Shown in the account menu's Contact support item; a Zoho alias of the founder's mailbox.
  supportEmail: 'support@iron-sys.com',
  // New-business address listed on www.iron-sys.com.
  salesEmail: 'hello@iron-sys.com',
} as const;
