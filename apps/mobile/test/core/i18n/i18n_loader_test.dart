import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/i18n/i18n_loader.dart';

class _MapAssetBundle extends AssetBundle {
  _MapAssetBundle(this._data);

  final Map<String, String> _data;

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final value = _data[key];
    if (value == null) throw FlutterError('Missing asset: $key');
    return value;
  }

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

void main() {
  final en = jsonEncode({
    'common': {'brandName': 'ProcurePilot'},
    'lowStock': {
      'title': 'Low Stock Report',
      'actionLabel': 'Running low',
      'countRemainingLabel': 'Count remaining',
    },
  });
  final ar = jsonEncode({
    'common': {'brandName': 'ProcurePilot'},
    'lowStock': {
      'title': 'بلاغ انخفاض المخزون',
      'actionLabel': 'المخزون منخفض',
      'countRemainingLabel': 'الكمية المتبقية',
    },
  });

  group('I18nLoader', () {
    test('loads English catalogue and resolves dotted keys', () async {
      final bundle = _MapAssetBundle({
        '../../packages/i18n/en.json': en,
        '../../packages/i18n/ar.json': ar,
      });
      final loader = I18nLoader(bundle: bundle);

      await loader.load('en');

      expect(loader.locale, 'en');
      expect(loader.textDirection, TextDirection.ltr);
      expect(loader.t('lowStock.title'), 'Low Stock Report');
      expect(loader.t('lowStock.actionLabel'), 'Running low');
    });

    test('loads Arabic catalogue and switches to RTL', () async {
      final bundle = _MapAssetBundle({
        '../../packages/i18n/en.json': en,
        '../../packages/i18n/ar.json': ar,
      });
      final loader = I18nLoader(bundle: bundle);

      await loader.load('ar');

      expect(loader.locale, 'ar');
      expect(loader.isRtl, isTrue);
      expect(loader.textDirection, TextDirection.rtl);
      expect(loader.t('lowStock.title'), 'بلاغ انخفاض المخزون');
    });

    test('supports simple {{param}} substitution', () async {
      final bundle = _MapAssetBundle({
        '../../packages/i18n/en.json': jsonEncode({
          'greeting': 'Hello {{name}}',
        }),
        '../../packages/i18n/ar.json': ar,
      });
      final loader = I18nLoader(bundle: bundle);
      await loader.load('en');

      expect(
        loader.t('greeting', params: {'name': 'World'}),
        'Hello World',
      );
    });

    test('returns the key itself for missing translations', () async {
      final bundle = _MapAssetBundle({
        '../../packages/i18n/en.json': en,
        '../../packages/i18n/ar.json': ar,
      });
      final loader = I18nLoader(bundle: bundle);
      await loader.load('en');

      expect(loader.t('missing.key'), 'missing.key');
    });
  });
}
