import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/delivery/delivery_confirmation_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('DeliveryConfirmationScreen', () {
    late FakeRequestsApiClient fakeClient;

    setUp(() {
      fakeClient = FakeRequestsApiClient();
    });

    Future<void> pumpDelivery(
      WidgetTester tester,
      PurchaseRequest request,
    ) async {
      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: request),
                  builder: (_) => const DeliveryConfirmationScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: fakeClient,
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
    }

    testWidgets('renders one pre-filled received quantity field per line', (
      tester,
    ) async {
      await pumpDelivery(tester, orderedRequest());

      expect(find.byKey(const Key('deliveryQuantityField_0')), findsOneWidget);
      expect(find.byKey(const Key('deliveryQuantityField_1')), findsOneWidget);
      expect(_fieldText('deliveryQuantityField_0', tester), '5');
      expect(_fieldText('deliveryQuantityField_1', tester), '2.5');
      expect(find.text('Ordered quantity: 5'), findsOneWidget);
      expect(find.text('Ordered quantity: 2.5'), findsOneWidget);
    });

    testWidgets('submitting calls confirmDelivery with edited values', (
      tester,
    ) async {
      fakeClient.confirmDeliveryResult = deliveredRequest();
      await pumpDelivery(tester, orderedRequest());

      await tester.enterText(
        find.byKey(const Key('deliveryQuantityField_1')),
        '1.75',
      );
      // The submit row sits below the content ListView's default fold, so its
      // element is not mounted until the sliver scrolls it into reach.
      await tester.dragUntilVisible(
        find.byKey(const Key('deliverySubmitButton')),
        find.byType(Scrollable).first,
        const Offset(0, -300),
      );
      await tester.tap(find.byKey(const Key('deliverySubmitButton')));
      await tester.pumpAndSettle();

      expect(fakeClient.confirmDeliveryCalls, ['req-1']);
      expect(fakeClient.confirmDeliveryLines.single, hasLength(2));
      expect(
        fakeClient.confirmDeliveryLines.single.map((line) => line.toJson()),
        [
          {'purchase_request_line_id': 'line-1', 'quantity_received': '5'},
          {'purchase_request_line_id': 'line-2', 'quantity_received': '1.75'},
        ],
      );
    });

    testWidgets('success shows message and returned confirmed quantities', (
      tester,
    ) async {
      fakeClient.confirmDeliveryResult = deliveredRequest();
      await pumpDelivery(tester, orderedRequest());

      await tester.dragUntilVisible(
        find.byKey(const Key('deliverySubmitButton')),
        find.byType(Scrollable).first,
        const Offset(0, -300),
      );
      await tester.tap(find.byKey(const Key('deliverySubmitButton')));
      await tester.pumpAndSettle();

      expect(find.text('Delivery confirmed.'), findsOneWidget);
      // RequestInfoRow renders "$label: " and the value as two separate Text
      // widgets (see RequestInfoRow.build) -- the status becomes the server's
      // confirmed "delivered" once _request is replaced with the response.
      expect(find.text('Status: '), findsOneWidget);
      expect(find.text('Delivered'), findsOneWidget);
    });

    testWidgets('not-ordered API error shows inline error message', (
      tester,
    ) async {
      fakeClient.confirmDeliveryError = const ApiException(
        statusCode: 409,
        code: 'conflict',
        message: 'Not ordered',
        details: {'reason': 'not_ordered'},
        traceId: 'trace-1',
      );
      await pumpDelivery(tester, orderedRequest());

      await tester.dragUntilVisible(
        find.byKey(const Key('deliverySubmitButton')),
        find.byType(Scrollable).first,
        const Offset(0, -300),
      );
      await tester.tap(find.byKey(const Key('deliverySubmitButton')));
      await tester.pumpAndSettle();

      expect(
        find.text('This request is not ready for delivery receipt.'),
        findsOneWidget,
      );
      expect(
        find.text('Unable to confirm delivery. Please try again.'),
        findsNothing,
      );
    });
  });

  group('RequestDetailScreen delivery entry point', () {
    testWidgets('ordered request shows confirm delivery button', (
      tester,
    ) async {
      await pumpWithServices(
        tester,
        child: const RequestDetailScreen(),
        requestsApiClient: FakeRequestsApiClient(),
      );
      final context = tester.element(find.byType(RequestDetailScreen));
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          settings: RouteSettings(arguments: orderedRequest()),
          builder: (_) => const RequestDetailScreen(),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestConfirmDeliveryButton')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('requestConfirmDeliveryButton')));
      await tester.pumpAndSettle();
      expect(find.byType(DeliveryConfirmationScreen), findsOneWidget);
    });

    testWidgets('submitted request does not show confirm delivery button', (
      tester,
    ) async {
      await pumpWithServices(
        tester,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  settings: RouteSettings(arguments: submittedRequest()),
                  builder: (_) => const RequestDetailScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
        requestsApiClient: FakeRequestsApiClient(),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('requestConfirmDeliveryButton')),
        findsNothing,
      );
    });
  });
}

String _fieldText(String key, WidgetTester tester) {
  final field = tester.widget<TextField>(find.byKey(Key(key)));
  return field.controller?.text ?? '';
}

PurchaseRequest orderedRequest() {
  return PurchaseRequest(
    id: 'req-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'ordered',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
        estimatedUnitPrice: Money(amount: '25.00', currency: 'USD'),
      ),
      PurchaseRequestLine(
        id: 'line-2',
        workspaceProductId: 'product-2',
        quantity: '2.5',
      ),
    ],
    estimatedTotal: const Money(amount: '125.00', currency: 'USD'),
    hasIncompleteEstimate: false,
    createdAt: DateTime.utc(2026, 9, 13),
  );
}

PurchaseRequest deliveredRequest() {
  return PurchaseRequest(
    id: 'req-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'delivered',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
        quantityReceived: '5',
      ),
      PurchaseRequestLine(
        id: 'line-2',
        workspaceProductId: 'product-2',
        quantity: '2.5',
        quantityReceived: '1.75',
      ),
    ],
    hasIncompleteEstimate: false,
    createdAt: DateTime.utc(2026, 9, 13),
    deliveredAt: DateTime.utc(2026, 9, 14),
    deliveryConfirmedByMembershipId: 'receiver-1',
    hasDeliveryDiscrepancy: true,
  );
}

PurchaseRequest submittedRequest() {
  final request = orderedRequest();
  return PurchaseRequest(
    id: request.id,
    branchId: request.branchId,
    requestedByMembershipId: request.requestedByMembershipId,
    requiredByDate: request.requiredByDate,
    status: 'submitted',
    lines: request.lines,
    hasIncompleteEstimate: request.hasIncompleteEstimate,
    createdAt: request.createdAt,
  );
}
