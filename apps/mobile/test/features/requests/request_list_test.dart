import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_list_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('RequestListScreen', () {
    late FakeRequestsApiClient fakeClient;

    setUp(() {
      fakeClient = FakeRequestsApiClient()
        ..listResults = [
          PurchaseRequest(
            id: 'req-1',
            branchId: 'branch-1',
            requestedByMembershipId: 'member-1',
            requiredByDate: '2026-10-01',
            status: 'submitted',
            lines: [],
            hasIncompleteEstimate: false,
            createdAt: DateTime.now(),
          ),
          PurchaseRequest(
            id: 'req-2',
            branchId: 'branch-1',
            requestedByMembershipId: 'member-1',
            requiredByDate: '2026-10-05',
            status: 'approved',
            lines: [],
            hasIncompleteEstimate: false,
            createdAt: DateTime.now(),
          ),
        ];
    });

    Future<void> pumpList(WidgetTester tester) async {
      await pumpWithServices(
        tester,
        child: const RequestListScreen(),
        requestsApiClient: fakeClient,
      );
      await tester.pumpAndSettle();
    }

    testWidgets('displays status chips for each request', (tester) async {
      await pumpList(tester);
      expect(find.byKey(const Key('requestList')), findsOneWidget);
      expect(find.byKey(const Key('requestStatus_submitted')), findsOneWidget);
      expect(find.byKey(const Key('requestStatus_approved')), findsOneWidget);
    });

    testWidgets('filters requests by status', (tester) async {
      await pumpList(tester);
      await tester.tap(find.byKey(const Key('requestListStatusFilter')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Approved').last);
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('requestStatus_approved')), findsOneWidget);
      expect(find.byKey(const Key('requestStatus_submitted')), findsNothing);
    });
  });

  group('RequestDetailScreen', () {
    Future<void> pumpDetail(
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
                  builder: (_) => const RequestDetailScreen(),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
    }

    testWidgets('renders decided approval step comment and decided_at', (
      tester,
    ) async {
      final request = PurchaseRequest(
        id: 'req-1',
        branchId: 'branch-1',
        requestedByMembershipId: 'member-1',
        requiredByDate: '2026-10-01',
        status: 'approved',
        lines: [
          PurchaseRequestLine(
            id: 'line-1',
            workspaceProductId: 'product-1',
            quantity: '5',
          ),
        ],
        hasIncompleteEstimate: false,
        approvalStep: ApprovalStep(
          id: 'step-1',
          assignedMembershipId: 'approver-1',
          source: 'threshold_match',
          status: 'approved',
          comment: 'Approved by branch policy',
          decidedByMembershipId: 'approver-1',
          decidedAt: DateTime.utc(2026, 9, 10, 12, 0, 0),
        ),
        createdAt: DateTime.now(),
      );
      await pumpDetail(tester, request);

      expect(find.text('Approved by branch policy'), findsOneWidget);
      expect(
        find.text(DateTime.utc(2026, 9, 10, 12, 0, 0).toIso8601String()),
        findsOneWidget,
      );
    });

    testWidgets('does not render comment for pending approval step', (
      tester,
    ) async {
      final request = PurchaseRequest(
        id: 'req-2',
        branchId: 'branch-1',
        requestedByMembershipId: 'member-1',
        requiredByDate: '2026-10-01',
        status: 'submitted',
        lines: [],
        hasIncompleteEstimate: false,
        approvalStep: ApprovalStep(
          id: 'step-2',
          assignedMembershipId: 'approver-1',
          source: 'threshold_match',
          status: 'pending',
        ),
        createdAt: DateTime.now(),
      );
      await pumpDetail(tester, request);

      expect(find.text('Decision comment'), findsNothing);
      expect(find.text('Decided on'), findsNothing);
    });
  });
}
