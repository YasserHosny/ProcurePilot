import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from './date.pipe';
import { FormatMoneyPipe } from './money.pipe';
import { FormatQuantityPipe } from './quantity.pipe';

// PPS-139: switching the language from the account menu re-rendered translated strings but left
// money, dates and quantities in the previous language until a reload. The inputs below never
// change; only the language does.
const TEMPLATE = `
  <span class="money">{{ price | formatMoney }}</span>
  <span class="date">{{ day | formatDate }}</span>
  <span class="qty">{{ qty | formatQuantity }}</span>
`;

@Component({
  selector: 'app-eager-format-host',
  imports: [FormatMoneyPipe, FormatDatePipe, FormatQuantityPipe],
  template: TEMPLATE,
  changeDetection: ChangeDetectionStrategy.Eager,
})
class EagerFormatHostComponent {
  readonly price = { amount: '86', currency: 'SAR' };
  readonly day = '2026-10-31';
  readonly qty = '1500.000000';
}

@Component({
  selector: 'app-onpush-format-child',
  imports: [FormatMoneyPipe, FormatDatePipe, FormatQuantityPipe],
  template: TEMPLATE,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class OnPushFormatChildComponent {
  readonly price = { amount: '86', currency: 'SAR' };
  readonly day = '2026-10-31';
  readonly qty = '1500.000000';
}

// An OnPush view nested under an Eager parent, as in the feature components.
@Component({
  selector: 'app-onpush-format-host',
  imports: [OnPushFormatChildComponent],
  template: '<app-onpush-format-child />',
  changeDetection: ChangeDetectionStrategy.Eager,
})
class OnPushFormatHostComponent {}

const ARABIC_DIGITS = /[٠-٩]/;

function text(fixture: ComponentFixture<unknown>, selector: string): string {
  const el = (fixture.nativeElement as HTMLElement).querySelector(selector);
  return (el?.textContent ?? '').trim();
}

describe('format pipes follow a language switch (PPS-139)', () => {
  let translate: TranslateService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [EagerFormatHostComponent, OnPushFormatHostComponent],
      providers: [provideTranslateService({ fallbackLang: 'en' })],
    });
    translate = TestBed.inject(TranslateService);
  });

  for (const [name, host] of [
    ['eager host', EagerFormatHostComponent],
    ['OnPush host', OnPushFormatHostComponent],
  ] as const) {
    describe(name, () => {
      it('re-renders Arabic values in English after switching ar → en', () => {
        translate.use('ar');
        const fixture = TestBed.createComponent<unknown>(host);
        fixture.detectChanges();

        expect(text(fixture, '.money')).toBe('٨٦ ر.س');
        expect(text(fixture, '.date')).toMatch(ARABIC_DIGITS);
        expect(text(fixture, '.qty')).toBe('١٬٥٠٠');

        translate.use('en');
        fixture.detectChanges();

        expect(text(fixture, '.money')).toBe('SAR 86');
        expect(text(fixture, '.date')).toBe('Oct 31, 2026');
        expect(text(fixture, '.qty')).toBe('1,500');
      });

      it('re-renders English values in Arabic after switching en → ar', () => {
        translate.use('en');
        const fixture = TestBed.createComponent<unknown>(host);
        fixture.detectChanges();

        expect(text(fixture, '.money')).toBe('SAR 86');

        translate.use('ar');
        fixture.detectChanges();

        expect(text(fixture, '.money')).toBe('٨٦ ر.س');
        expect(text(fixture, '.date')).toMatch(ARABIC_DIGITS);
        expect(text(fixture, '.qty')).toBe('١٬٥٠٠');
      });
    });
  }
});
