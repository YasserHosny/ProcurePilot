import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:procurepilot_mobile/core/format/date_format.dart';

void main() {
  group('formatDateTime', () {
    setUpAll(() async {
      await initializeDateFormatting();
    });

    final localDateTime = DateTime(2026, 10, 24, 14, 30);

    test('formats local DateTime in English', () {
      expect(
        formatDateTime(localDateTime, locale: 'en'),
        'Oct 24, 2026 2:30\u202FPM',
      );
    });

    test('formats local DateTime in Arabic with Arabic-Indic digits', () {
      final formatted = formatDateTime(localDateTime, locale: 'ar');
      expect(formatted, '٢٤ أكتوبر ٢٠٢٦ ٢:٣٠ م');
      expect(formatted.contains('٢٠٢٦'), isTrue);
      expect(RegExp(r'[0-9]').hasMatch(formatted), isFalse);
    });

    test('UTC DateTime produces the same result as its local conversion', () {
      final utcDateTime = DateTime.utc(2026, 10, 24, 11, 30);
      expect(
        formatDateTime(utcDateTime, locale: 'en'),
        formatDateTime(utcDateTime.toLocal(), locale: 'en'),
      );
      expect(
        formatDateTime(utcDateTime, locale: 'ar'),
        formatDateTime(utcDateTime.toLocal(), locale: 'ar'),
      );
    });
  });
}
