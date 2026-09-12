import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/requests/request_form_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('RequestFormScreen', () {
    late FakeRequestsApiClient fakeClient;

    setUp(() {
      fakeClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'branch-1',
            name: 'Main Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ]
        ..costCentres = [
          CostCentre(
            id: 'cc-1',
            name: 'Marketing',
            code: 'MKT',
            isArchived: false,
            createdAt: DateTime.now(),
          ),
        ]
        ..catalogueSearchResults = [
          CatalogueProduct(
            id: 'product-1',
            tenantName: 'Semi-Skimmed Milk',
            canonicalName: 'Semi-Skimmed Milk',
            baseUnit: 'litre',
            status: 'active',
            createdAt: DateTime.now(),
          ),
        ];
    });

    Future<void> pumpForm(WidgetTester tester) async {
      await pumpWithServices(
        tester,
        child: const RequestFormScreen(),
        requestsApiClient: fakeClient,
      );
      await tester.pumpAndSettle();
    }

    Future<void> tapButton(WidgetTester tester, Key key) async {
      final finder = find.byKey(key);
      await tester.ensureVisible(finder);
      await tester.pumpAndSettle();
      await tester.tap(finder);
      await tester.pumpAndSettle();
    }

    Future<void> enterText(WidgetTester tester, Key key, String text) async {
      final finder = find.byKey(key);
      await tester.ensureVisible(finder);
      await tester.pumpAndSettle();
      await tester.enterText(finder, text);
      await tester.pumpAndSettle();
    }

    testWidgets('renders branch, cost-centre and required-by fields', (
      tester,
    ) async {
      await pumpForm(tester);
      expect(find.byKey(const Key('requestFormBranchField')), findsOneWidget);
      expect(find.byKey(const Key('requestFormCostCentreField')), findsOneWidget);
      expect(find.byKey(const Key('requestFormRequiredByField')), findsOneWidget);
    });

    testWidgets('catalogue search populates product selection', (tester) async {
      await pumpForm(tester);
      await enterText(tester, const Key('requestLine_0_productSearch'), 'milk');
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestLine_0_productResult_0')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('requestLine_0_productResult_0')));
      await tester.pumpAndSettle();
    });

    testWidgets('adds and removes line items', (tester) async {
      await pumpForm(tester);
      expect(find.byKey(const Key('requestLine_0')), findsOneWidget);

      await tapButton(tester, const Key('requestFormAddLineButton'));
      expect(find.byKey(const Key('requestLine_1')), findsOneWidget);

      await tapButton(tester, const Key('requestLine_0_removeButton'));
      expect(find.byKey(const Key('requestLine_1')), findsNothing);
      expect(find.byKey(const Key('requestLine_0')), findsOneWidget);
    });

    testWidgets('saves a draft with branch, date and line', (tester) async {
      await pumpForm(tester);

      await tester.tap(find.byKey(const Key('requestFormBranchField')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Main Branch').last);
      await tester.pumpAndSettle();

      await enterText(
        tester,
        const Key('requestFormRequiredByField'),
        '2026-10-01',
      );
      await enterText(
        tester,
        const Key('requestLine_0_productSearch'),
        'product-1',
      );
      await enterText(tester, const Key('requestLine_0_quantity'), '5');

      await tapButton(tester, const Key('requestFormSaveDraftButton'));

      expect(fakeClient.createCalls.length, 1);
      final created = fakeClient.createCalls.first;
      expect(created.branchId, 'branch-1');
      expect(created.requiredByDate, '2026-10-01');
      expect(created.lines.length, 1);
      expect(created.lines.first.workspaceProductId, 'product-1');
      expect(created.lines.first.quantity, '5');
    });

    testWidgets('patches existing draft on second save', (tester) async {
      fakeClient.createResult = PurchaseRequest(
        id: 'req-1',
        branchId: 'branch-1',
        requestedByMembershipId: 'member-1',
        requiredByDate: '2026-10-01',
        status: 'draft',
        lines: [],
        hasIncompleteEstimate: false,
        createdAt: DateTime.now(),
      );
      await pumpForm(tester);

      await tester.tap(find.byKey(const Key('requestFormBranchField')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Main Branch').last);
      await tester.pumpAndSettle();

      await enterText(
        tester,
        const Key('requestFormRequiredByField'),
        '2026-10-01',
      );
      await enterText(
        tester,
        const Key('requestLine_0_productSearch'),
        'product-1',
      );
      await enterText(tester, const Key('requestLine_0_quantity'), '2');

      await tapButton(tester, const Key('requestFormSaveDraftButton'));

      await enterText(tester, const Key('requestLine_0_quantity'), '3');
      await tapButton(tester, const Key('requestFormSaveDraftButton'));

      expect(fakeClient.createCalls.length, 1);
      expect(fakeClient.updateCalls.length, 1);
      expect(fakeClient.updateCalls.first[0], 'req-1');
    });

    testWidgets('submit is disabled when there are zero lines', (tester) async {
      await pumpForm(tester);
      await tapButton(tester, const Key('requestLine_0_removeButton'));

      final submitFinder = find.byKey(const Key('requestFormSubmitButton'));
      await tester.ensureVisible(submitFinder);
      await tester.pumpAndSettle();
      final submitButton = tester.widget<ElevatedButton>(submitFinder);
      expect(submitButton.onPressed, isNull);
    });

    testWidgets('submit calls submitRequest after draft exists', (tester) async {
      fakeClient.createResult = PurchaseRequest(
        id: 'req-1',
        branchId: 'branch-1',
        requestedByMembershipId: 'member-1',
        requiredByDate: '2026-10-01',
        status: 'draft',
        lines: [],
        hasIncompleteEstimate: false,
        createdAt: DateTime.now(),
      );
      await pumpForm(tester);

      await tester.tap(find.byKey(const Key('requestFormBranchField')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Main Branch').last);
      await tester.pumpAndSettle();

      await enterText(
        tester,
        const Key('requestFormRequiredByField'),
        '2026-10-01',
      );
      await enterText(
        tester,
        const Key('requestLine_0_productSearch'),
        'product-1',
      );
      await enterText(tester, const Key('requestLine_0_quantity'), '2');

      await tapButton(tester, const Key('requestFormSaveDraftButton'));
      await tester.pump(const Duration(seconds: 1));
      await tapButton(tester, const Key('requestFormSubmitButton'));

      expect(fakeClient.submitCalls, ['req-1']);
    });

    testWidgets('draft id is remembered after save so submit is available', (
      tester,
    ) async {
      fakeClient.createResult = PurchaseRequest(
        id: 'req-persist',
        branchId: 'branch-1',
        requestedByMembershipId: 'member-1',
        requiredByDate: '2026-10-01',
        status: 'draft',
        lines: [],
        hasIncompleteEstimate: false,
        createdAt: DateTime.now(),
      );
      await pumpForm(tester);

      await tester.tap(find.byKey(const Key('requestFormBranchField')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Main Branch').last);
      await tester.pumpAndSettle();

      await enterText(
        tester,
        const Key('requestFormRequiredByField'),
        '2026-10-01',
      );
      await enterText(
        tester,
        const Key('requestLine_0_productSearch'),
        'product-1',
      );
      await enterText(tester, const Key('requestLine_0_quantity'), '4');

      await tapButton(tester, const Key('requestFormSaveDraftButton'));
      await tester.pump(const Duration(seconds: 1));

      final submitFinder = find.byKey(const Key('requestFormSubmitButton'));
      await tester.ensureVisible(submitFinder);
      await tester.pumpAndSettle();
      final submitButton = tester.widget<ElevatedButton>(submitFinder);
      expect(submitButton.onPressed, isNotNull);

      await tapButton(tester, const Key('requestFormSubmitButton'));

      expect(fakeClient.submitCalls, ['req-persist']);
    });
  });
}
