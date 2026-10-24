import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/approvals/approval_queue_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('ApprovalQueueScreen', () {
    late FakeApprovalsApiClient fakeClient;
    late FakeRequestsApiClient fakeRequestsClient;

    setUp(() {
      fakeRequestsClient = FakeRequestsApiClient();
      fakeClient = FakeApprovalsApiClient()
        ..pendingResults = [
          pendingRequest(
            id: 'req-1',
            requester: 'member-uuid-1111',
            requesterName: 'Sarah Connor',
          ),
          pendingRequest(
            id: 'req-2',
            requester: 'member-uuid-2222',
            requesterEmail: 'john@example.com',
          ),
        ];
    });

    Future<void> pumpQueue(WidgetTester tester, {String locale = 'en'}) async {
      await tester.pumpWidget(const SizedBox.shrink());
      await pumpWithServices(
        tester,
        child: const ApprovalQueueScreen(),
        approvalsApiClient: fakeClient,
        requestsApiClient: fakeRequestsClient,
        locale: locale,
      );
      await tester.pumpAndSettle();
    }

    testWidgets('renders requester name or email, never the raw membership UUID', (
      tester,
    ) async {
      await pumpQueue(tester);

      expect(find.text('Approval Queue'), findsOneWidget);
      expect(find.byKey(const Key('approvalQueueList')), findsOneWidget);
      expect(find.text('Requester: Sarah Connor'), findsOneWidget);
      expect(find.text('Requester: john@example.com'), findsOneWidget);
      expect(find.textContaining('member-uuid-1111'), findsNothing);
      expect(find.textContaining('member-uuid-2222'), findsNothing);
      expect(find.text('USD 125.00'), findsNWidgets(2));
    });

    testWidgets('falls back to localised unknown requester when name and email are missing', (
      tester,
    ) async {
      fakeClient.pendingResults = [
        pendingRequest(
          id: 'req-3',
          requester: 'member-uuid-3333',
        ),
      ];
      await pumpQueue(tester);
      expect(find.text('Requester: Unknown requester'), findsOneWidget);
      expect(find.textContaining('member-uuid-3333'), findsNothing);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('مقدم طلب غير معروف'), findsOneWidget);
      expect(find.textContaining('member-uuid-3333'), findsNothing);
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
          requesterName: 'Ahmed',
          total: const Money(amount: '12500', currency: 'EGP'),
        ),
      ];
      await pumpQueue(tester);
      expect(find.text('EGP 12,500.00'), findsOneWidget);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('١٢٬٥٠٠٫٠٠'), findsOneWidget);
      expect(find.byType(Directionality), findsWidgets);
    });

    testWidgets('formats required-by date in English and Arabic', (tester) async {
      fakeClient.pendingResults = [
        PurchaseRequest(
          id: 'req-date',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requesterName: 'Sarah Connor',
          requiredByDate: '2026-10-28',
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
        ),
      ];

      await pumpQueue(tester, locale: 'en');
      expect(find.text('Required By: Oct 28, 2026'), findsOneWidget);
      expect(find.textContaining('2026-10-28'), findsNothing);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('مطلوب قبل: ٢٨ أكتوبر ٢٠٢٦'), findsOneWidget);
      expect(find.textContaining('2026-10-28'), findsNothing);
    });

    testWidgets('navigating to decision screen and approving reloads queue', (
      tester,
    ) async {
      await pumpQueue(tester);
      expect(find.byKey(const Key('approvalQueueItem_0')), findsOneWidget);

      // Simulate backend having 0 pending items once approved
      fakeClient.pendingResults = [];

      await tester.tap(find.byKey(const Key('approvalQueueItem_0')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('approvalDecisionApproveButton')), findsOneWidget);
      await tester.tap(find.byKey(const Key('approvalDecisionApproveButton')));
      await tester.pumpAndSettle();

      // Popped back to ApprovalQueueScreen
      expect(find.byType(ApprovalQueueScreen), findsOneWidget);
      expect(find.byKey(const Key('approvalDecisionApproveButton')), findsNothing);

      // Reloaded queue
      expect(
        find.text('No requests are currently awaiting your decision.'),
        findsOneWidget,
      );
    });
  });
}

PurchaseRequest pendingRequest({
  required String id,
  required String requester,
  String? requesterName,
  String? requesterEmail,
  Money total = const Money(amount: '125.00', currency: 'USD'),
}) {
  return PurchaseRequest(
    id: id,
    branchId: 'branch-1',
    requestedByMembershipId: requester,
    requesterName: requesterName,
    requesterEmail: requesterEmail,
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
