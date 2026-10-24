import 'package:intl/intl.dart';

/// Formats a [DateTime] value as a localized medium date and short time.
///
/// Converts [value] to local time. For Arabic ([locale] is `'ar'`),
/// maps ASCII digits 0-9 to Arabic-Indic digits (٠-٩).
String formatDateTime(DateTime value, {required String locale}) {
  final local = value.toLocal();
  final formatted = DateFormat.yMMMd(locale).add_jm().format(local);
  return _localizeDigits(formatted, locale: locale);
}

/// Formats an ISO calendar date (`YYYY-MM-DD`) as a localized medium date.
///
/// Parses the calendar date as `DateTime(y, m, d)` without timezone conversion
/// so that the calendar day never shifts. If [isoDate] does not parse as a valid
/// `YYYY-MM-DD` date, returns [isoDate] unchanged.
///
/// For Arabic ([locale] is `'ar'`), maps ASCII digits 0-9 to Arabic-Indic digits (٠-٩).
String formatDate(String isoDate, {required String locale}) {
  final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(isoDate.trim());
  if (match == null) return isoDate;

  final year = int.tryParse(match[1]!);
  final month = int.tryParse(match[2]!);
  final day = int.tryParse(match[3]!);
  if (year == null || month == null || day == null) return isoDate;
  if (month < 1 || month > 12 || day < 1 || day > 31) return isoDate;

  final date = DateTime(year, month, day);
  if (date.year != year || date.month != month || date.day != day) {
    return isoDate;
  }

  final formatted = DateFormat.yMMMd(locale).format(date);
  return _localizeDigits(formatted, locale: locale);
}

String _localizeDigits(String formatted, {required String locale}) {
  if (locale == 'ar') {
    return formatted.replaceAllMapped(
      RegExp(r'[0-9]'),
      (match) => String.fromCharCode(0x0660 + int.parse(match[0]!)),
    );
  }
  return formatted;
}
