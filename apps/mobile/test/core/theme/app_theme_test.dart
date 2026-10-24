import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/theme/app_theme.dart';
import 'package:procurepilot_mobile/core/theme/brand_colors.dart';
import 'package:procurepilot_mobile/core/theme/brand_logo.dart';
import 'package:procurepilot_mobile/core/theme/ledger_typography.dart';

void main() {
  group('AppTheme', () {
    test(
      'colorScheme.primary is navy 0xFF0B2545 and the scaffold background is Paper 0xFFF4F6F9',
      () {
        final theme = AppTheme.lightTheme;
        expect(theme.colorScheme.primary, const Color(0xFF0B2545));
        expect(theme.scaffoldBackgroundColor, const Color(0xFFF4F6F9));
        expect(theme.colorScheme.surface, const Color(0xFFF4F6F9));
      },
    );

    test("the text theme's family is Readex Pro", () {
      final theme = AppTheme.lightTheme;
      expect(theme.textTheme.bodyMedium?.fontFamily, 'Readex Pro');
      expect(theme.textTheme.bodyLarge?.fontFamily, 'Readex Pro');
      expect(theme.textTheme.titleMedium?.fontFamily, 'Readex Pro');
      expect(theme.textTheme.titleLarge?.fontFamily, 'Readex Pro');
      expect(theme.textTheme.headlineSmall?.fontFamily, 'Readex Pro');
      expect(theme.textTheme.labelMedium?.fontFamily, 'Readex Pro');
    });

    test('theme provides warning and success tokens via ThemeExtension', () {
      final theme = AppTheme.lightTheme;
      final colors = theme.extension<LedgerColors>();
      expect(colors, isNotNull);
      expect(colors!.warning, const Color(0xFF8A4B00));
      expect(colors.success, const Color(0xFF166534));
      expect(colors.savings, const Color(0xFF0C7A6E));
      expect(colors.paperBorderStrong, const Color(0xFF8494A8));
    });

    test('LedgerTypography exposes tabular figures using Noto Kufi Arabic', () {
      final style = LedgerTypography.tabularFigures();
      expect(style.fontFamily, 'Noto Kufi Arabic');
      expect(style.fontFeatures, contains(const FontFeature.tabularFigures()));
    });
  });

  group('BrandLogo', () {
    testWidgets("shows the Arabic lockup under locale 'ar'", (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Localizations.override(
              context: context,
              locale: const Locale('ar'),
              child: const Scaffold(body: BrandLogo()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final imageFinder = find.byType(Image);
      expect(imageFinder, findsOneWidget);
      final image = tester.widget<Image>(imageFinder);
      final asset = image.image as AssetImage;
      expect(
        asset.assetName,
        'assets/brand/procurepilot-arabic-horizontal-1436px.png',
      );
    });

    testWidgets("shows the English lockup under locale 'en'", (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Localizations.override(
              context: context,
              locale: const Locale('en'),
              child: const Scaffold(body: BrandLogo()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final imageFinder = find.byType(Image);
      expect(imageFinder, findsOneWidget);
      final image = tester.widget<Image>(imageFinder);
      final asset = image.image as AssetImage;
      expect(
        asset.assetName,
        'assets/brand/procurepilot-horizontal-1436px.png',
      );
    });

    testWidgets('shows the mark alone below 24 px tall', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(body: BrandLogo(height: 20)),
        ),
      );
      await tester.pumpAndSettle();

      final imageFinder = find.byType(Image);
      expect(imageFinder, findsOneWidget);
      final image = tester.widget<Image>(imageFinder);
      final asset = image.image as AssetImage;
      expect(asset.assetName, 'assets/brand/procurepilot-mark-192px.png');
    });

    testWidgets(
      'is not mirrored under TextDirection.rtl (no Transform with a negative x scale above it)',
      (tester) async {
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Localizations.override(
                context: context,
                locale: const Locale('ar'),
                child: const Directionality(
                  textDirection: TextDirection.rtl,
                  child: Scaffold(body: BrandLogo()),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final imageFinder = find.byType(Image);
        expect(imageFinder, findsOneWidget);
        final image = tester.widget<Image>(imageFinder);
        expect(image.matchTextDirection, isFalse);

        final transforms = tester.widgetList<Transform>(find.byType(Transform));
        for (final transform in transforms) {
          final matrix = transform.transform;
          expect(matrix.storage[0], isNot(isNegative));
        }
      },
    );
  });
}
