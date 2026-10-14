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
      expect(formatted, contains('١٢٬٥٠٠٫٠٠'));
      expect(formatted, startsWith('\u2068'));
      expect(formatted, endsWith('\u2069'));
    });
  });
}
