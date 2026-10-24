import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import en from '../../../../../../packages/i18n/en.json';
import { FormatService } from '../../core/format/format.service';
import { packLabel } from './pack-label';

describe('packLabel', () => {
  let translate: TranslateService;
  let format: FormatService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideTranslateService()] });
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.use('en');
    format = TestBed.inject(FormatService);
  });

  it('labels a fractional live product pack without a derived base_quantity', () => {
    const result = packLabel({ pack_count: 3, unit_size: '0.33' }, 'kilogram', translate, format);
    expect(result.size).toBe(0.99);
    expect(result.label).toBe('pack of 0.99 kg');
  });

  it('labels a fractional pack snapshot', () => {
    expect(packLabel('0.500000', 'litre', translate, format).label).toBe('pack of 0.5 L');
  });

  it('omits the pack label for size one, missing, or non-positive sizes', () => {
    for (const size of ['1.000000', null, undefined, '0', '-1']) {
      expect(packLabel(size, 'litre', translate, format).label).toBeNull();
    }
  });
});
