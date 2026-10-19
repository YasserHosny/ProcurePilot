import 'package:intl/intl.dart';

import '../i18n/i18n_loader.dart';

/// Formats a decimal string (such as a quantity) for display without
/// loss of precision. Trims trailing zeros after the decimal point,
/// formats up to 6 fraction digits, and maps separators and digits
/// to Arabic-Indic when the locale is Arabic.
String formatDecimal(
  String value, {
  required String locale,
  int maxFractionDigits = 6,
  bool trimTrailingZeros = true,
}) {
  try {
    final trimmed = value.trim();
    final match = RegExp(r'^([+-]?)(\d+)(?:\.(\d*))?$').firstMatch(trimmed);
    if (match == null) return value;
    final negative = match.group(1) == '-';
    final wholeStr = match.group(2)!;
    var fraction = match.group(3) ?? '';

    if (fraction.length > maxFractionDigits) {
      fraction = fraction.substring(0, maxFractionDigits);
    }
    if (trimTrailingZeros) {
      fraction = fraction.replaceAll(RegExp(r'0+$'), '');
    }

    final symbols = NumberFormat.decimalPattern(locale).symbols;
    final groups = <String>[];
    for (var end = wholeStr.length; end > 0; end -= 3) {
      final start = end - 3 < 0 ? 0 : end - 3;
      groups.insert(0, wholeStr.substring(start, end));
    }
    final groupedWhole = groups.join(symbols.GROUP_SEP);
    var formatted = fraction.isEmpty
        ? '${negative ? '-' : ''}$groupedWhole'
        : '${negative ? '-' : ''}$groupedWhole${symbols.DECIMAL_SEP}$fraction';

    if (locale == 'ar') {
      formatted = formatted
          .replaceAll(symbols.GROUP_SEP, '٬')
          .replaceAll(symbols.DECIMAL_SEP, '٫')
          .replaceAllMapped(
            RegExp(r'[0-9]'),
            (m) => String.fromCharCode(0x0660 + int.parse(m[0]!)),
          );
    }
    return formatted;
  } on Object {
    return value;
  }
}

/// Canonical unit key aliases for normalisation.
const Map<String, String> _unitAliases = {
  'litre': 'litre',
  'liter': 'litre',
  'l': 'litre',
  'lt': 'litre',
  'ltr': 'litre',
  'kilogram': 'kilogram',
  'kg': 'kilogram',
  'kgs': 'kilogram',
  'kilo': 'kilogram',
  'kilos': 'kilogram',
  'gram': 'gram',
  'g': 'gram',
  'gm': 'gram',
  'millilitre': 'millilitre',
  'milliliter': 'millilitre',
  'ml': 'millilitre',
  'each': 'each',
  'ea': 'each',
  'pc': 'each',
  'pcs': 'each',
  'piece': 'each',
  'pieces': 'each',
  'unit': 'each',
  'units': 'each',
};

/// Localises a raw unit code (e.g. `litre` -> `L` in English, `لتر` in Arabic)
/// using translations from `units.*` or `rfq.email.units.*`.
/// Falls back to the raw unit string if unknown or untranslated.
String localizeUnit(
  String? unit, {
  required I18nLoader i18n,
}) {
  if (unit == null || unit.trim().isEmpty) return '';
  final raw = unit.trim().toLowerCase();
  final canonical = _unitAliases[raw] ?? raw;
  final unitKey = 'units.$canonical';
  final unitLookedUp = i18n.t(unitKey);
  if (unitLookedUp != unitKey) {
    return unitLookedUp;
  }
  final key = 'rfq.email.units.$canonical';
  final lookedUp = i18n.t(key);
  if (lookedUp != key) {
    return lookedUp;
  }
  return unit.trim();
}

/// Formats request quantity for display.
///
/// When [packBaseQuantity] is greater than 0 and not equal to 1, renders
/// `"2 × 18 L"` (in English) or `"٢ × ١٨ لتر"` (in Arabic).
/// Otherwise renders the trimmed, localized quantity.
String formatQuantity(
  String quantity, {
  String? packBaseQuantity,
  String? baseUnit,
  required I18nLoader i18n,
  String? locale,
}) {
  final activeLocale = locale ?? i18n.locale;
  final formattedQty = formatDecimal(quantity, locale: activeLocale);
  if (packBaseQuantity == null) return formattedQty;

  final packNum = double.tryParse(packBaseQuantity.trim());
  if (packNum == null || packNum <= 0 || (packNum - 1.0).abs() < 1e-9) {
    return formattedQty;
  }

  final formattedPack = formatDecimal(packBaseQuantity, locale: activeLocale);
  final unit = localizeUnit(baseUnit, i18n: i18n);
  if (unit.isEmpty) {
    return '$formattedQty × $formattedPack';
  }
  return '$formattedQty × $formattedPack $unit';
}
