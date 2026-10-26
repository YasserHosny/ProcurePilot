import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/features/about/about_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('AboutScreen', () {
    testWidgets('renders the i18n strings in en', (tester) async {
      final fakeVersionProvider = FakeAppVersionProvider('0.1.0 (1)');

      await pumpWithServices(
        tester,
        child: const AboutScreen(),
        versionProvider: fakeVersionProvider,
        locale: 'en',
      );
      await tester.pumpAndSettle();

      expect(find.text('Help & about'), findsOneWidget);
      expect(find.text('Contact support'), findsOneWidget);
      expect(
        find.text('Questions or problems with ProcurePilot'),
        findsOneWidget,
      );
      expect(find.text('Privacy Policy'), findsOneWidget);
      expect(find.text('Terms of Service'), findsOneWidget);
      expect(find.text('ProcurePilot by Iron Systems'), findsOneWidget);
      expect(find.text('www.iron-sys.com'), findsOneWidget);
      expect(find.text('Version 0.1.0 (1)'), findsOneWidget);
    });

    testWidgets('renders the i18n strings in ar (RTL direction)', (
      tester,
    ) async {
      final fakeVersionProvider = FakeAppVersionProvider('0.1.0 (1)');

      await pumpWithServices(
        tester,
        child: const AboutScreen(),
        versionProvider: fakeVersionProvider,
        locale: 'ar',
      );
      await tester.pumpAndSettle();

      // Screen is rendered in RTL
      expect(
        Directionality.of(tester.element(find.text('المساعدة وحول التطبيق'))),
        TextDirection.rtl,
      );

      // Arabic strings
      expect(find.text('المساعدة وحول التطبيق'), findsOneWidget);
      expect(find.text('تواصل مع الدعم'), findsOneWidget);
      expect(
        find.text('أسئلة أو مشكلات في استخدام ProcurePilot'),
        findsOneWidget,
      );
      expect(find.text('سياسة الخصوصية'), findsOneWidget);
      expect(find.text('شروط الخدمة'), findsOneWidget);
      expect(find.text('ProcurePilot من Iron Systems'), findsOneWidget);
      expect(find.text('www.iron-sys.com'), findsOneWidget);
      expect(find.text('الإصدار 0.1.0 (1)'), findsOneWidget);

      // Company link / website stays LTR even in RTL Arabic
      expect(
        Directionality.of(tester.element(find.text('www.iron-sys.com'))),
        TextDirection.ltr,
      );
    });

    testWidgets(
      'tapping each tile calls the fake LinkOpener with mailto:support@iron-sys.com, <origin>/privacy, <origin>/terms, https://www.iron-sys.com/',
      (tester) async {
        final fakeLinkOpener = FakeLinkOpener();
        const testOrigin = 'https://portal.iron-sys.com';

        await pumpWithServices(
          tester,
          child: const AboutScreen(),
          linkOpener: fakeLinkOpener,
          webOrigin: testOrigin,
        );
        await tester.pumpAndSettle();

        // 1. Contact support tile -> mailto:support@iron-sys.com
        await tester.tap(find.byKey(const Key('aboutContactSupportTile')));
        await tester.pumpAndSettle();
        expect(fakeLinkOpener.calls, contains('mailto:support@iron-sys.com'));

        // 2. Privacy Policy tile -> <origin>/privacy
        await tester.tap(find.byKey(const Key('aboutPrivacyPolicyTile')));
        await tester.pumpAndSettle();
        expect(fakeLinkOpener.calls, contains('$testOrigin/privacy'));

        // 3. Terms of Service tile -> <origin>/terms
        await tester.tap(find.byKey(const Key('aboutTermsOfServiceTile')));
        await tester.pumpAndSettle();
        expect(fakeLinkOpener.calls, contains('$testOrigin/terms'));

        // 4. Company link -> https://www.iron-sys.com/
        await tester.tap(find.byKey(const Key('aboutCompanyLink')));
        await tester.pumpAndSettle();
        expect(fakeLinkOpener.calls, contains('https://www.iron-sys.com/'));
      },
    );

    testWidgets('version line shows the fake version', (tester) async {
      final fakeVersionProvider = FakeAppVersionProvider('2.4.6 (123)');

      await pumpWithServices(
        tester,
        child: const AboutScreen(),
        versionProvider: fakeVersionProvider,
      );
      await tester.pumpAndSettle();

      expect(find.text('Version 2.4.6 (123)'), findsOneWidget);
    });

    testWidgets('normalises webOrigin with trailing slash correctly', (
      tester,
    ) async {
      final fakeLinkOpener = FakeLinkOpener();

      await pumpWithServices(
        tester,
        child: const AboutScreen(),
        linkOpener: fakeLinkOpener,
        webOrigin: 'https://custom-origin.com/',
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('aboutPrivacyPolicyTile')));
      await tester.pumpAndSettle();
      expect(fakeLinkOpener.calls, contains('https://custom-origin.com/privacy'));
    });
  });
}
