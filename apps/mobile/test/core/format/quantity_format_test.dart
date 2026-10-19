import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/format/quantity_format.dart';
import 'package:procurepilot_mobile/core/i18n/i18n_loader.dart';

class _RealAssetBundle extends AssetBundle {
  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    for (final candidate in [
      key,
      'packages/i18n/${key.split('/').last}',
      '../../packages/i18n/${key.split('/').last}',
    ]) {
      final f = File(candidate);
      if (f.existsSync()) {
        return f.readAsString();
      }
    }
    throw FlutterError('Missing asset: $key');
  }

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

Future<I18nLoader> _loadRealI18n(String locale) async {
  final loader = I18nLoader(bundle: _RealAssetBundle());
  await loader.load(locale);
  return loader;
}

void main() {
  late I18nLoader i18nEn;
  late I18nLoader i18nAr;

  setUpAll(() async {
    i18nEn = await _loadRealI18n('en');
    i18nAr = await _loadRealI18n('ar');
  });

  group('formatDecimal', () {
    test('formats whole numbers trimming trailing zeros in English', () {
      expect(formatDecimal('1.000000', locale: 'en'), '1');
      expect(formatDecimal('2.000000', locale: 'en'), '2');
      expect(formatDecimal('100.0', locale: 'en'), '100');
    });

    test('formats fractions up to 6 digits trimming trailing zeros in English', () {
      expect(formatDecimal('12.5', locale: 'en'), '12.5');
      expect(formatDecimal('2.500000', locale: 'en'), '2.5');
      expect(formatDecimal('0.123456', locale: 'en'), '0.123456');
      expect(formatDecimal('12500.750000', locale: 'en'), '12,500.75');
    });

    test('formats numbers using Arabic-Indic digits in Arabic', () {
      expect(formatDecimal('1.000000', locale: 'ar'), '١');
      expect(formatDecimal('2.000000', locale: 'ar'), '٢');
      expect(formatDecimal('12.5', locale: 'ar'), '١٢٫٥');
      expect(formatDecimal('18.000000', locale: 'ar'), '١٨');
      expect(formatDecimal('2.500000', locale: 'ar'), '٢٫٥');
      expect(formatDecimal('12500.750000', locale: 'ar'), '١٢٬٥٠٠٫٧٥');
    });
  });

  group('localizeUnit', () {
    test('normalises litre aliases in English and Arabic from i18n', () {
      for (final alias in ['litre', 'liter', 'l', 'lt', 'ltr', 'LITRE']) {
        expect(localizeUnit(alias, i18n: i18nEn), 'L');
        expect(localizeUnit(alias, i18n: i18nAr), 'لتر');
      }
    });

    test('normalises kilogram aliases in English and Arabic from i18n', () {
      for (final alias in ['kilogram', 'kg', 'kgs', 'kilo', 'kilos', 'KG']) {
        expect(localizeUnit(alias, i18n: i18nEn), 'kg');
        expect(localizeUnit(alias, i18n: i18nAr), 'كجم');
      }
    });

    test('normalises gram aliases in English and Arabic from i18n', () {
      for (final alias in ['gram', 'g', 'gm', 'Gram']) {
        expect(localizeUnit(alias, i18n: i18nEn), 'g');
        expect(localizeUnit(alias, i18n: i18nAr), 'جم');
      }
    });

    test('normalises millilitre aliases in English and Arabic from i18n', () {
      for (final alias in ['millilitre', 'milliliter', 'ml', 'ML']) {
        expect(localizeUnit(alias, i18n: i18nEn), 'mL');
        expect(localizeUnit(alias, i18n: i18nAr), 'مل');
      }
    });

    test('normalises each/piece aliases in English and Arabic from i18n', () {
      for (final alias in [
        'each',
        'ea',
        'pc',
        'pcs',
        'piece',
        'pieces',
        'unit',
        'units',
      ]) {
        expect(localizeUnit(alias, i18n: i18nEn), 'pcs');
        expect(localizeUnit(alias, i18n: i18nAr), 'وحدة');
      }
    });

    test('falls back to raw unit for unknown units', () {
      expect(localizeUnit('pack', i18n: i18nEn), 'pack');
      expect(localizeUnit('box', i18n: i18nAr), 'box');
      expect(localizeUnit(null, i18n: i18nEn), '');
      expect(localizeUnit('', i18n: i18nEn), '');
    });
  });

  group('formatQuantity', () {
    test('formats pack quantity with base quantity and unit in English', () {
      expect(
        formatQuantity(
          '2.000000',
          packBaseQuantity: '18.000000',
          baseUnit: 'litre',
          i18n: i18nEn,
        ),
        '2 × 18 L',
      );
    });

    test('formats pack quantity with base quantity and unit in Arabic', () {
      expect(
        formatQuantity(
          '2.000000',
          packBaseQuantity: '18.000000',
          baseUnit: 'litre',
          i18n: i18nAr,
        ),
        '٢ × ١٨ لتر',
      );
    });

    test('does not show multiplier when pack_base_quantity is 1 or missing', () {
      expect(
        formatQuantity(
          '5.000000',
          packBaseQuantity: '1.000000',
          baseUnit: 'litre',
          i18n: i18nEn,
        ),
        '5',
      );
      expect(
        formatQuantity(
          '5.000000',
          packBaseQuantity: null,
          baseUnit: 'litre',
          i18n: i18nEn,
        ),
        '5',
      );
      expect(
        formatQuantity(
          '5.000000',
          packBaseQuantity: '0',
          baseUnit: 'litre',
          i18n: i18nEn,
        ),
        '5',
      );
    });
  });
}
