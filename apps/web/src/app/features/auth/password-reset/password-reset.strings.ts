export const PASSWORD_RESET_STRINGS = {
  brandName: 'ProcurePilot',
  title: 'Reset your password',
  subtitle: 'Enter your email address and we will send you a link to reset your password.',
  emailLabel: 'Work Email Address',
  emailPlaceholder: 'you@company.com',
  emailRequired: 'Email is required',
  emailInvalid: 'Please enter a valid email address',
  submitButton: 'Send Reset Instructions',
  submittingButton: 'Sending instructions...',
  backToSignIn: 'Back to sign in',
  // Deliberate security rule: always report the same message whether or not address is known
  successTitle: 'Check your email',
  successMessage: 'If an account exists with that email address, we have sent instructions to reset your password.',
  rateLimitedError: 'Too many password reset requests. Please wait a few moments and try again.',
  genericError: 'Unable to process reset request. Please check your connection and try again.',
  traceIdLabel: 'Reference ID',
} as const;
