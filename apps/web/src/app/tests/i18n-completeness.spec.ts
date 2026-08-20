import enCatalog from '../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../packages/i18n/ar.json';

describe('i18n Catalogue Parity and Completeness (T068)', () => {
  function extractLeafKeys(obj: Record<string, unknown>, prefix = ''): string[] {
    const keys: string[] = [];
    for (const [k, v] of Object.entries(obj)) {
      const fullPath = prefix ? `${prefix}.${k}` : k;
      if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        keys.push(...extractLeafKeys(v as Record<string, unknown>, fullPath));
      } else {
        keys.push(fullPath);
      }
    }
    return keys;
  }

  function getLeafValue(obj: Record<string, unknown>, path: string): unknown {
    const segments = path.split('.');
    let current: unknown = obj;
    for (const seg of segments) {
      if (typeof current !== 'object' || current === null) return undefined;
      current = (current as Record<string, unknown>)[seg];
    }
    return current;
  }

  it('should have 100% key parity between English and Arabic catalogues in both directions', () => {
    const enKeys = extractLeafKeys(enCatalog as Record<string, unknown>);
    const arKeys = extractLeafKeys(arCatalog as Record<string, unknown>);

    const missingInArabic = enKeys.filter((key) => !arKeys.includes(key));
    const missingInEnglish = arKeys.filter((key) => !enKeys.includes(key));

    const errorMessage = [
      missingInArabic.length > 0 ? `Missing in Arabic: ${missingInArabic.join(', ')}` : '',
      missingInEnglish.length > 0 ? `Missing in English: ${missingInEnglish.join(', ')}` : '',
    ]
      .filter(Boolean)
      .join('; ');

    expect(missingInArabic).withContext(errorMessage).toEqual([]);
    expect(missingInEnglish).withContext(errorMessage).toEqual([]);
  });

  it('should not contain empty translation values in English catalogue', () => {
    const enKeys = extractLeafKeys(enCatalog as Record<string, unknown>);
    const emptyKeys: string[] = [];

    for (const key of enKeys) {
      const val = getLeafValue(enCatalog as Record<string, unknown>, key);
      if (typeof val !== 'string' || val.trim().length === 0) {
        emptyKeys.push(key);
      }
    }

    expect(emptyKeys).withContext(`Empty keys in EN: ${emptyKeys.join(', ')}`).toEqual([]);
  });

  it('should not contain empty translation values in Arabic catalogue', () => {
    const arKeys = extractLeafKeys(arCatalog as Record<string, unknown>);
    const emptyKeys: string[] = [];

    for (const key of arKeys) {
      const val = getLeafValue(arCatalog as Record<string, unknown>, key);
      if (typeof val !== 'string' || val.trim().length === 0) {
        emptyKeys.push(key);
      }
    }

    expect(emptyKeys).withContext(`Empty keys in AR: ${emptyKeys.join(', ')}`).toEqual([]);
  });
});
