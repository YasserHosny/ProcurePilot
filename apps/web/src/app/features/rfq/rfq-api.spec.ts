import { RfqActionKeys, formatRfqReference } from './rfq-api';

describe('formatRfqReference', () => {
  it('pads references without truncating and omits missing values', () => {
    expect(formatRfqReference(1)).toBe('RFQ-000001');
    expect(formatRfqReference(123456)).toBe('RFQ-123456');
    expect(formatRfqReference(null)).toBe('');
    expect(formatRfqReference(undefined)).toBe('');
  });
});

describe('RfqActionKeys', () => {
  it('reuses a key while the payload it was created for is unchanged', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('create:new', '{"quantity":"10"}');
    expect(keys.get('create:new', '{"quantity":"10"}')).toBe(first);
  });

  it('rotates the key when the payload changes, so edits are never swallowed by a replay', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('update:rfq-1', '{"quantity":"10"}');
    const edited = keys.get('update:rfq-1', '{"quantity":"12"}');
    expect(edited).not.toBe(first);
    expect(keys.get('update:rfq-1', '{"quantity":"12"}')).toBe(edited);
  });

  it('keeps the previous behaviour for actions without a payload', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('send:rfq-1');
    expect(keys.get('send:rfq-1')).toBe(first);
    keys.clear('send:rfq-1');
    expect(keys.get('send:rfq-1')).not.toBe(first);
  });
});
