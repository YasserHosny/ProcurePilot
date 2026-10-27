import 'package:intl/intl.dart';

const _arabicCurrencySymbols = {
  'EGP': 'ج.م',
  'SAR': 'ر.س',
  'AED': 'د.إ',
  'KWD': 'د.ك',
  'QAR': 'ر.ق',
  'BHD': 'د.ب',
  'OMR': 'ر.ع',
  'JOD': 'د.أ',
};

/// Formats a decimal amount for display without converting its full precision
/// through a binary floating point value.
String formatMoney(String amount, String currency, {required String locale}) {
  final code = currency.toUpperCase();
  final digits = switch (code) {
    'KWD' || 'BHD' || 'OMR' => 3,
    'JPY' || 'KRW' || 'CLP' || 'VND' || 'ISK' => 0,
    _ => 2,
  };
  try {
    final value = amount.trim();
    final match = RegExp(r'^([+-]?)(\d+)(?:\.(\d*))?$').firstMatch(value);
    if (match == null) {
      final symbol = locale == 'ar' ? (_arabicCurrencySymbols[code] ?? code) : code;
      final formatted = locale == 'ar' ? '$amount $symbol' : '$code $amount';
      return locale == 'ar' ? '\u2068$formatted\u2069' : formatted;
    }
    final negative = match.group(1) == '-';
    final whole = BigInt.parse(match.group(2)!);
    final fraction = match.group(3) ?? '';
    final padded = fraction.padRight(digits + 1, '0');
    var minor = digits == 0
        ? BigInt.zero
        : BigInt.parse(padded.substring(0, digits));
    var roundedWhole = whole;
    if (digits < padded.length && padded.codeUnitAt(digits) >= 53) {
      if (digits > 0) {
        minor += BigInt.one;
        final limit = BigInt.from(10).pow(digits);
        if (minor >= limit) {
          roundedWhole += BigInt.one;
          minor -= limit;
        }
      } else {
        roundedWhole += BigInt.one;
      }
    }
    final isZero = roundedWhole == BigInt.zero && minor == BigInt.zero;
    final isNegative = negative && !isZero;
    final showFraction = digits > 0 && minor != BigInt.zero;

    final symbols = NumberFormat.decimalPattern(locale).symbols;
    final wholeText = roundedWhole.toString();
    final groups = <String>[];
    for (var end = wholeText.length; end > 0; end -= 3) {
      final start = end - 3 < 0 ? 0 : end - 3;
      groups.insert(0, wholeText.substring(start, end));
    }
    final groupedWhole = groups.join(symbols.GROUP_SEP);
    final fractionText = showFraction
        ? '${symbols.DECIMAL_SEP}${minor.toString().padLeft(digits, '0')}'
        : '';
    var number = '${isNegative ? '-' : ''}$groupedWhole$fractionText';
    if (locale == 'ar') {
      number = number
          .replaceAll(symbols.GROUP_SEP, '٬')
          .replaceAll(symbols.DECIMAL_SEP, '٫')
          .replaceAllMapped(
            RegExp(r'[0-9]'),
            (match) => String.fromCharCode(0x0660 + int.parse(match[0]!)),
          );
    }
    final formatted = locale == 'ar'
        ? '$number ${_arabicCurrencySymbols[code] ?? code}'
        : '$code $number';
    return locale == 'ar' ? '\u2068$formatted\u2069' : formatted;
  } on Object {
    final symbol = locale == 'ar' ? (_arabicCurrencySymbols[code] ?? code) : code;
    final formatted = locale == 'ar' ? '$amount $symbol' : '$code $amount';
    return locale == 'ar' ? '\u2068$formatted\u2069' : formatted;
  }
}
