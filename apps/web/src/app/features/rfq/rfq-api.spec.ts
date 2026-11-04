import { formatRfqReference } from './rfq-api';

describe('formatRfqReference', () => {
  it('pads references without truncating and omits missing values', () => {
    expect(formatRfqReference(1)).toBe('RFQ-000001');
    expect(formatRfqReference(123456)).toBe('RFQ-123456');
    expect(formatRfqReference(null)).toBe('');
    expect(formatRfqReference(undefined)).toBe('');
  });
});
