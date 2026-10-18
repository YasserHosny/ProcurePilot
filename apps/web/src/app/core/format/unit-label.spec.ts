import { TestBed } from '@angular/core/testing';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import ar from '../../../../../../packages/i18n/ar.json';
import en from '../../../../../../packages/i18n/en.json';
import { lineDescription } from '../../features/orders/pack-label';
import { unitLabel } from './unit-label';

describe('unitLabel', () => {
  it('labels supported base units in the interface language and passes unknown codes through', () => {
    TestBed.configureTestingModule({ imports: [TranslateModule.forRoot()] });
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.setTranslation('ar', ar);
    translate.use('en');
    expect(unitLabel(translate, 'kilogram')).toBe('kg');
    translate.use('ar');
    expect(unitLabel(translate, 'kilogram')).toBe('كجم');
    expect(unitLabel(translate, 'litre')).toBe('لتر');
    expect(unitLabel(translate, 'EA')).toBe('EA');
    expect(unitLabel(translate, null)).toBe('');
  });
});

describe('lineDescription', () => {
  it('drops the English pack suffix older purchase orders stored in the description', () => {
    expect(lineDescription('أرز مصري (شيكارة 25 كجم) (pack of 25 kilogram)')).toBe('أرز مصري (شيكارة 25 كجم)');
    expect(lineDescription('زيت (صفيحة 18 لتر) (pack of 18 litre)')).toBe('زيت (صفيحة 18 لتر)');
    expect(lineDescription('Paper (pack of 6)')).toBe('Paper (pack of 6)');
  });
});
