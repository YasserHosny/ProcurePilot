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

    Future<void> pumpQueue(WidgetTester tester, {String locale = 'en'}) async {
      await tester.pumpWidget(const SizedBox.shrink());
      await pumpWithServices(
        tester,
        child: const ApprovalQueueScreen(),
        approvalsApiClient: fakeClient,
        locale: locale,
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

    testWidgets('formats money in English and Arabic', (tester) async {
      fakeClient.pendingResults = [
        pendingRequest(
          id: 'req-egp',
          requester: 'member-egp',
          total: const Money(amount: '12500', currency: 'EGP'),
        ),
      ];
      await pumpQueue(tester);
      expect(find.text('EGP 12,500.00'), findsOneWidget);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('١٢٬٥٠٠٫٠٠'), findsOneWidget);
      expect(find.byType(Directionality), findsWidgets);
    });
  });
}

PurchaseRequest pendingRequest({
  required String id,
  required String requester,
  Money total = const Money(amount: '125.00', currency: 'USD'),
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
    estimatedTotal: total,
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
