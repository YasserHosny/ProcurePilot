import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/format/money_format.dart';

void main() {
  group('formatMoney', () {
    test('groups a two-decimal currency in English', () {
      expect(formatMoney('12500.000000', 'EGP', locale: 'en'), 'EGP 12,500.00');
    });

    test('uses three decimals for KWD', () {
      expect(formatMoney('12.5', 'KWD', locale: 'en'), 'KWD 12.500');
    });

    test('rounds only for display', () {
      expect(formatMoney('1.23456', 'EGP', locale: 'en'), 'EGP 1.23');
      expect(formatMoney('1.23456', 'EGP', locale: 'en'), 'EGP 1.23');
    });

    test('does not lose large integer precision through double conversion', () {
      expect(
        formatMoney('9007199254740993.00', 'EGP', locale: 'en'),
        'EGP 9,007,199,254,740,993.00',
      );
    });

    test('uses zero decimal places for JPY and KRW', () {
      expect(formatMoney('1234.5', 'JPY', locale: 'en'), 'JPY 1,235');
      expect(formatMoney('1234', 'KRW', locale: 'en'), 'KRW 1,234');
    });

    test('preserves unknown currency codes with two decimals', () {
      expect(formatMoney('1234.5', 'XYZ', locale: 'en'), 'XYZ 1,234.50');
    });

    test('formats negative amounts', () {
      expect(formatMoney('-1234.5', 'EGP', locale: 'en'), 'EGP -1,234.50');
    });

    test('uses Arabic locale conventions and direction isolation', () {
      final formatted = formatMoney('12500', 'EGP', locale: 'ar');
      expect(formatted, '\u2068١٢٬٥٠٠٫٠٠ ج.م\u2069');
      expect(formatted, startsWith('\u2068'));
      expect(formatted, endsWith('\u2069'));
    });

    test('formats Arabic money with number first followed by Arabic currency symbol (PPS-84)', () {
      expect(formatMoney('300.00', 'EGP', locale: 'ar'), '\u2068٣٠٠٫٠٠ ج.م\u2069');
      expect(formatMoney('190', 'SAR', locale: 'ar'), '\u2068١٩٠٫٠٠ ر.س\u2069');
      expect(formatMoney('50', 'AED', locale: 'ar'), '\u2068٥٠٫٠٠ د.إ\u2069');
      expect(formatMoney('12.5', 'KWD', locale: 'ar'), '\u2068١٢٫٥٠٠ د.ك\u2069');
      expect(formatMoney('10', 'QAR', locale: 'ar'), '\u2068١٠٫٠٠ ر.ق\u2069');
      expect(formatMoney('5', 'BHD', locale: 'ar'), '\u2068٥٫٠٠٠ د.ب\u2069');
      expect(formatMoney('7', 'OMR', locale: 'ar'), '\u2068٧٫٠٠٠ ر.ع\u2069');
      expect(formatMoney('20', 'JOD', locale: 'ar'), '\u2068٢٠٫٠٠ د.أ\u2069');
    });

    test('falls back to ISO code for unknown currencies in Arabic locale (PPS-84)', () {
      expect(formatMoney('100', 'USD', locale: 'ar'), '\u2068١٠٠٫٠٠ USD\u2069');
      expect(formatMoney('1234.5', 'XYZ', locale: 'ar'), '\u2068١٬٢٣٤٫٥٠ XYZ\u2069');
    });

    test('leaves English formatting unchanged (PPS-84)', () {
      expect(formatMoney('300.00', 'EGP', locale: 'en'), 'EGP 300.00');
    });
  });
}
