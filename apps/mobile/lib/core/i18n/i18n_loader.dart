import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;

/// Loads the shared `packages/i18n/{en,ar}.json` catalogue as a Flutter asset
/// and exposes dotted-key lookups matching the shape used by web's
/// `@ngx-translate/core`.
class I18nLoader extends ChangeNotifier {
  I18nLoader({AssetBundle? bundle}) : _bundle = bundle ?? rootBundle;

  final AssetBundle _bundle;
  Map<String, dynamic> _translations = const {};
  String _locale = 'en';

  String get locale => _locale;

  /// True when the active locale is Arabic, which drives RTL.
  bool get isRtl => _locale == 'ar';

  /// [TextDirection] derived from the active locale so the UI cannot drift
  /// out of sync with the selected JSON file.
  TextDirection get textDirection =>
      isRtl ? TextDirection.rtl : TextDirection.ltr;

  /// Loads the catalogue for [locale] from the bundled assets.
  Future<void> load(String locale) async {
    final path = '../../packages/i18n/$locale.json';
    final raw = await _bundle.loadString(path);
    _translations = jsonDecode(raw) as Map<String, dynamic>;
    _locale = locale;
    notifyListeners();
  }

  /// Looks up a dotted key such as `requests.form.branchLabel`.
  ///
  /// Supports simple `{{param}}` substitution when [params] is supplied.
  /// Returns [key] itself when the key is missing so the UI degrades visibly
  /// rather than showing an empty string.
  String t(String key, {Map<String, String>? params}) {
    final parts = key.split('.');
    dynamic node = _translations;
    for (final part in parts) {
      if (node is! Map<String, dynamic>) return key;
      node = node[part];
    }
    if (node == null) return key;

    var value = node.toString();
    if (params != null) {
      params.forEach((param, replacement) {
        value = value.replaceAll('{{$param}}', replacement);
      });
    }
    return value;
  }
}
