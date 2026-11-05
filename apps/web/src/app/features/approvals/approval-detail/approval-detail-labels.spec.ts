import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';

// Include every label/visible-text pair introduced by the approval detail feature.
// Both the single-row and split-member links use this pair. The detail page's
// back and open-queue links have no aria-label override: their text is their name.
for (const [locale, catalogue] of Object.entries({en: enCatalog, ar: arCatalog})) {
  describe(`approval detail accessible names (${locale})`, () => {
    const pairs = [
      {
        key: 'approvals.detail.viewDetailsLabel',
        label: catalogue.approvals.detail.viewDetailsLabel,
        visible: catalogue.approvals.detail.viewDetails,
      },
    ];

    for (const {key, label, visible} of pairs) {
      it(`${key} contains its visible link text as a contiguous substring`, () => {
        const withoutPlaceholders = label.replace(/{{[\s\S]*?}}/g, '');
        expect(visible.trim().length).toBeGreaterThan(0);
        expect(withoutPlaceholders).withContext(`${locale}: ${key}`).toContain(visible);
      });
    }
  });
}
