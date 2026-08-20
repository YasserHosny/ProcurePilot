export const environment = {
  production: false,
  apiBaseUrl: '/api/v1',
  // Empty locally; supplied at build time in deployed environments.
  sentryDsn: '',
} as const;
