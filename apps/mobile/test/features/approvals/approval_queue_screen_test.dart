import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/approvals/approval_queue_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('ApprovalQueueScreen', () {
    late FakeApprovalsApiClient fakeClient;

    setUp(() {
      fakeClient = FakeApprovalsApiClient()
        ..pendingResults = [
          pendingRequest(id: 'req-1', requester: 'member-1'),
          pendingRequest(id: 'req-2', requester: 'member-2'),
        ];
    });

    Future<void> pumpQueue(WidgetTester tester) async {
      await pumpWithServices(
        tester,
        child: const ApprovalQueueScreen(),
        approvalsApiClient: fakeClient,
      );
      await tester.pumpAndSettle();
    }

    testWidgets('renders pending requests from listPendingApprovals', (
      tester,
    ) async {
      await pumpQueue(tester);

      expect(find.text('Approval Queue'), findsOneWidget);
      expect(find.byKey(const Key('approvalQueueList')), findsOneWidget);
      expect(find.text('Requester: member-1'), findsOneWidget);
      expect(find.text('Requester: member-2'), findsOneWidget);
      expect(find.text('USD 125.00'), findsNWidgets(2));
    });

    testWidgets('renders empty state when no approvals are pending', (
      tester,
    ) async {
      fakeClient.pendingResults = [];
      await pumpQueue(tester);

      expect(
        find.text('No requests are currently awaiting your decision.'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('approvalQueueList')), findsNothing);
    });
  });
}

PurchaseRequest pendingRequest({
  required String id,
  required String requester,
}) {
  return PurchaseRequest(
    id: id,
    branchId: 'branch-1',
    requestedByMembershipId: requester,
    requiredByDate: '2026-10-01',
    status: 'submitted',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
      ),
    ],
    estimatedTotal: const Money(amount: '125.00', currency: 'USD'),
    hasIncompleteEstimate: false,
    approvalStep: const ApprovalStep(
      id: 'step-1',
      assignedMembershipId: 'approver-1',
      source: 'threshold_match',
      status: 'pending',
    ),
    createdAt: DateTime.utc(2026, 9, 13),
  );
}
