import type { FeedbackCategory, FeedbackStatus } from './platform-feedback-api';

/**
 * Literal translation keys per enum value. Kept as full literals (not built by concatenation) so
 * `scripts/check-i18n-keys.mjs` can verify every one exists in both catalogues.
 */
export const STATUS_LABEL_KEYS: Record<FeedbackStatus, string> = {
  new: 'platform.feedback.status.new',
  reviewed: 'platform.feedback.status.reviewed',
  resolved: 'platform.feedback.status.resolved',
};

export const STATUS_ACTION_KEYS: Record<FeedbackStatus, string> = {
  new: 'platform.feedback.actions.markNew',
  reviewed: 'platform.feedback.actions.markReviewed',
  resolved: 'platform.feedback.actions.markResolved',
};

export const CATEGORY_LABEL_KEYS: Record<FeedbackCategory, string> = {
  bug: 'platform.feedback.category.bug',
  idea: 'platform.feedback.category.idea',
  question: 'platform.feedback.category.question',
  other: 'platform.feedback.category.other',
};

export const ROLE_LABEL_KEYS: Record<string, string> = {
  owner: 'common.roles.owner',
  buyer: 'common.roles.buyer',
  branch_manager: 'common.roles.branch_manager',
  approver: 'common.roles.approver',
  viewer: 'common.roles.viewer',
};
