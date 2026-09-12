import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('LowStockReportScreen', () {
    late FakeMobileApiClient fakeMobileClient;
    late FakeRequestsApiClient fakeRequestsClient;

    final testProduct = CatalogueProduct(
      id: '00000000-0000-0000-0000-000000000002',
      tenantName: 'Fresh Whole Milk 2L',
      canonicalName: 'Fresh Whole Milk 2L',
      baseUnit: 'bottle',
      status: 'active',
      createdAt: DateTime.now(),
    );

    setUp(() {
      fakeMobileClient = FakeMobileApiClient();
      fakeRequestsClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: '00000000-0000-0000-0000-000000000001',
            name: 'Downtown Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ]
        ..catalogueSearchResults = [testProduct];
    });

    Future<void> pumpScreen(
      WidgetTester tester, {
      CatalogueProduct? product,
      String? branchId,
    }) async {
      await pumpWithServices(
        tester,
        child: LowStockReportScreen(
          initialProduct: product,
          initialBranchId: branchId,
        ),
        mobileApiClient: fakeMobileClient,
        requestsApiClient: fakeRequestsClient,
      );
      await tester.pumpAndSettle();
    }

    Future<void> enterText(WidgetTester tester, Key key, String text) async {
      final finder = find.byKey(key);
      await tester.ensureVisible(finder);
      await tester.enterText(finder, text);
      await tester.pumpAndSettle();
    }

    Future<void> tapButton(WidgetTester tester, Key key) async {
      final finder = find.byKey(key);
      await tester.ensureVisible(finder);
      await tester.tap(finder);
      await tester.pumpAndSettle();
    }

    testWidgets('one-tap submit WITH a count passes exact parameters', (
      tester,
    ) async {
      await pumpScreen(tester, product: testProduct);

      await enterText(
        tester,
        const Key('lowStockCountRemainingField'),
        '14',
      );

      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(fakeMobileClient.createLowStockCalls.length, equals(1));
      final call = fakeMobileClient.createLowStockCalls.single;
      expect(
        call['branchId'],
        equals('00000000-0000-0000-0000-000000000001'),
      );
      expect(
        call['workspaceProductId'],
        equals(testProduct.id),
      );
      expect(call['countRemaining'], equals('14'));
      expect(call['idempotencyKey'], isNotNull);
      expect(call['idempotencyKey'], isNotEmpty);
    });

    testWidgets('one-tap submit WITHOUT a count passes null countRemaining', (
      tester,
    ) async {
      await pumpScreen(tester, product: testProduct);

      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const Key('lowStockCountRemainingField')),
            )
            .controller
            ?.text,
        isEmpty,
      );

      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(fakeMobileClient.createLowStockCalls.length, equals(1));
      final call = fakeMobileClient.createLowStockCalls.single;
      expect(
        call['branchId'],
        equals('00000000-0000-0000-0000-000000000001'),
      );
      expect(
        call['workspaceProductId'],
        equals(testProduct.id),
      );
      expect(call['countRemaining'], isNull);
      expect(call['idempotencyKey'], isNotNull);
      expect(call['idempotencyKey'], isNotEmpty);
    });

    testWidgets('confirmation state renders after successful call', (
      tester,
    ) async {
      await pumpScreen(tester, product: testProduct);

      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(find.byKey(const Key('lowStockConfirmationView')), findsOneWidget);
      expect(
        find.text('Low stock report submitted.'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('lowStockSuccessIcon')), findsOneWidget);
    });

    testWidgets('rapid double-tap produces exactly one client-side call', (
      tester,
    ) async {
      await pumpScreen(tester, product: testProduct);

      final submitFinder = find.byKey(const Key('lowStockSubmitButton'));
      expect(submitFinder, findsOneWidget);

      await tester.tap(submitFinder);
      await tester.tap(submitFinder, warnIfMissed: false);
      await tester.pumpAndSettle();

      expect(fakeMobileClient.createLowStockCalls.length, equals(1));
    });

    testWidgets('catalogue search populates product and allows selection', (
      tester,
    ) async {
      await pumpScreen(tester);

      expect(
        find.byKey(const Key('lowStockProductSearchField')),
        findsOneWidget,
      );

      await enterText(
        tester,
        const Key('lowStockProductSearchField'),
        'Milk',
      );
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('lowStockProductResult_0')), findsOneWidget);
      expect(find.text('Fresh Whole Milk 2L'), findsOneWidget);

      await tester.tap(find.byKey(const Key('lowStockProductResult_0')));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('lowStockSelectedProductCard')),
        findsOneWidget,
      );
      expect(find.text('Fresh Whole Milk 2L'), findsOneWidget);

      await tapButton(tester, const Key('lowStockSubmitButton'));
      expect(fakeMobileClient.createLowStockCalls.length, equals(1));
      expect(
        fakeMobileClient.createLowStockCalls.single['workspaceProductId'],
        equals(testProduct.id),
      );
    });

    testWidgets('error state displays and retry reuses the same idempotency key', (
      tester,
    ) async {
      await pumpScreen(tester, product: testProduct);

      fakeMobileClient.createLowStockError = const ApiException(
        statusCode: 503,
        code: 'service_unavailable',
        message: 'Network error occurred',
        traceId: 'trace-123',
      );

      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(fakeMobileClient.createLowStockCalls.length, equals(1));
      final firstKey =
          fakeMobileClient.createLowStockCalls[0]['idempotencyKey'];
      expect(firstKey, isNotNull);
      expect(find.text('Network error occurred'), findsOneWidget);

      fakeMobileClient.createLowStockError = null;
      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(fakeMobileClient.createLowStockCalls.length, equals(2));
      final secondKey =
          fakeMobileClient.createLowStockCalls[1]['idempotencyKey'];
      expect(secondKey, equals(firstKey));
      expect(find.byKey(const Key('lowStockConfirmationView')), findsOneWidget);
    });

    testWidgets('validation refuses submission if branch is unselected', (
      tester,
    ) async {
      fakeRequestsClient.branches = [
        Branch(
          id: 'branch-1',
          name: 'Branch One',
          isActive: true,
          createdAt: DateTime.now(),
        ),
        Branch(
          id: 'branch-2',
          name: 'Branch Two',
          isActive: true,
          createdAt: DateTime.now(),
        ),
      ];

      await pumpScreen(tester, product: testProduct);

      await tapButton(tester, const Key('lowStockSubmitButton'));

      expect(fakeMobileClient.createLowStockCalls, isEmpty);
      expect(find.text('Branch is required.'), findsOneWidget);
    });
  });
}
