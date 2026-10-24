import 'package:intl/intl.dart';

/// Formats a [DateTime] value as a localized medium date and short time.
///
/// Converts [value] to local time. For Arabic ([locale] is `'ar'`),
/// maps ASCII digits 0-9 to Arabic-Indic digits (٠-٩).
String formatDateTime(DateTime value, {required String locale}) {
  final local = value.toLocal();
  final formatted = DateFormat.yMMMd(locale).add_jm().format(local);
  if (locale == 'ar') {
    return formatted.replaceAllMapped(
      RegExp(r'[0-9]'),
      (match) => String.fromCharCode(0x0660 + int.parse(match[0]!)),
    );
  }
  return formatted;
}
