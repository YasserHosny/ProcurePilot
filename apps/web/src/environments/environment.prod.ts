export const environment = {
  production: true,
  apiBaseUrl: '/api/v1',
  // Empty locally; supplied at build time in deployed environments.
  sentryDsn: '',
  // Shown in the account menu's Contact support item; a Zoho alias of the founder's mailbox.
  supportEmail: 'support@iron-sys.com',
} as const;
