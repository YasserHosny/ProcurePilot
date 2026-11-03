export const environment = {
  production: true,
  apiBaseUrl: '/api/v1',
  // Empty locally; supplied at build time in deployed environments.
  sentryDsn: '',
  // Shown in the account menu's Contact support item; a Zoho alias of the founder's mailbox.
  supportEmail: 'support@iron-sys.com',
  // New-business address listed on www.iron-sys.com.
  salesEmail: 'hello@iron-sys.com',
  // Founder's WhatsApp for new business, international format without '+' (wa.me links).
  salesWhatsapp: '201027354140',
} as const;
