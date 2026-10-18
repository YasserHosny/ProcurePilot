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
  const pack25kg = { pack_base_quantity: '25.000000', base_unit: 'kilogram' };

  it('hides the English pack suffix older purchase orders generated from the line pack', () => {
    expect(lineDescription({ ...pack25kg, description: 'أرز مصري (شيكارة 25 كجم) (pack of 25 kilogram)' }))
      .toBe('أرز مصري (شيكارة 25 كجم)');
    expect(lineDescription({ pack_base_quantity: '18.000000', base_unit: 'litre', description: 'زيت (pack of 18 litre)' }))
      .toBe('زيت');
  });

  it('keeps text that does not match the line pack, or a line without a pack', () => {
    expect(lineDescription({ ...pack25kg, description: 'Paper (pack of 10 kilogram)' })).toBe('Paper (pack of 10 kilogram)');
    expect(lineDescription({ ...pack25kg, description: 'Paper (pack of 25 litre)' })).toBe('Paper (pack of 25 litre)');
    expect(lineDescription({ pack_base_quantity: null, base_unit: 'kilogram', description: 'Rice (pack of 25 kilogram)' }))
      .toBe('Rice (pack of 25 kilogram)');
    expect(lineDescription({ ...pack25kg, description: 'Paper (pack of 6)' })).toBe('Paper (pack of 6)');
  });
});
