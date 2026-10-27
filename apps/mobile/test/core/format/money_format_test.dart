import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/format/money_format.dart';

void main() {
  group('formatMoney', () {
    test('groups a two-decimal currency in English', () {
      expect(formatMoney('12500.000000', 'EGP', locale: 'en'), 'EGP 12,500');
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
        'EGP 9,007,199,254,740,993',
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
      expect(formatted, '\u2068١٢٬٥٠٠ ج.م\u2069');
      expect(formatted, startsWith('\u2068'));
      expect(formatted, endsWith('\u2069'));
    });

    test('formats Arabic money with number first followed by Arabic currency symbol (PPS-84)', () {
      expect(formatMoney('300.00', 'EGP', locale: 'ar'), '\u2068٣٠٠ ج.م\u2069');
      expect(formatMoney('190', 'SAR', locale: 'ar'), '\u2068١٩٠ ر.س\u2069');
      expect(formatMoney('50', 'AED', locale: 'ar'), '\u2068٥٠ د.إ\u2069');
      expect(formatMoney('12.5', 'KWD', locale: 'ar'), '\u2068١٢٫٥٠٠ د.ك\u2069');
      expect(formatMoney('10', 'QAR', locale: 'ar'), '\u2068١٠ ر.ق\u2069');
      expect(formatMoney('5', 'BHD', locale: 'ar'), '\u2068٥ د.ب\u2069');
      expect(formatMoney('7', 'OMR', locale: 'ar'), '\u2068٧ ر.ع\u2069');
      expect(formatMoney('20', 'JOD', locale: 'ar'), '\u2068٢٠ د.أ\u2069');
    });

    test('falls back to ISO code for unknown currencies in Arabic locale (PPS-84)', () {
      expect(formatMoney('100', 'USD', locale: 'ar'), '\u2068١٠٠ USD\u2069');
      expect(formatMoney('1234.5', 'XYZ', locale: 'ar'), '\u2068١٬٢٣٤٫٥٠ XYZ\u2069');
    });

    test('leaves English formatting unchanged (PPS-84)', () {
      expect(formatMoney('300.00', 'EGP', locale: 'en'), 'EGP 300');
    });

    test('shows 0 decimals when whole and full minor digits when not (PPS-85)', () {
      expect(formatMoney('24640.00', 'EGP', locale: 'ar'), '\u2068٢٤٬٦٤٠ ج.م\u2069');
      expect(formatMoney('16.25', 'EGP', locale: 'ar'), '\u2068١٦٫٢٥ ج.م\u2069');
      expect(formatMoney('24640.0000', 'EGP', locale: 'en'), 'EGP 24,640');
      expect(formatMoney('12.5', 'EGP', locale: 'en'), 'EGP 12.50');
    });

    test('avoids negative zero (PPS-85)', () {
      expect(formatMoney('-0.00', 'EGP', locale: 'en'), 'EGP 0');
      expect(formatMoney('-0.00', 'EGP', locale: 'ar'), '\u2068٠ ج.م\u2069');
      expect(formatMoney('-0.001', 'EGP', locale: 'en'), 'EGP 0');
      expect(formatMoney('-0.001', 'EGP', locale: 'ar'), '\u2068٠ ج.م\u2069');
    });
  });
}
