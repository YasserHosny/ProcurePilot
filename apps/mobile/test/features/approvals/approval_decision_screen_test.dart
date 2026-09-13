import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/approvals/approval_decision_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('ApprovalDecisionScreen', () {
    late FakeRequestsApiClient fakeClient;

    setUp(() {
      fakeClient = FakeRequestsApiClient();
    });

    Future<void> pumpDecision(
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
                  builder: (_) => const ApprovalDecisionScreen(),
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

    Future<void> enterComment(WidgetTester tester, String comment) async {
      await tester.enterText(
        find.byKey(const Key('approvalDecisionCommentField')),
        comment,
      );
      await tester.pumpAndSettle();
    }

    testWidgets(
      'renders lines, estimated total, budget status and requester identity',
      (tester) async {
        await pumpDecision(tester, decisionRequest());

        // RequestInfoRow renders "$label: " and the value as two separate
        // Text widgets (see RequestInfoRow.build), not one combined string.
        expect(find.text('Requester: '), findsOneWidget);
        expect(find.text('requester-1'), findsOneWidget);
        expect(find.text('Estimated Total: '), findsOneWidget);
        expect(find.text('USD 125.00'), findsOneWidget);
        expect(find.text('Remaining budget: '), findsOneWidget);
        expect(find.text('USD 40.00'), findsOneWidget);
        expect(
          find.text(
            'This request would exceed the remaining budget for its scope.',
          ),
          findsOneWidget,
        );
        expect(find.byKey(const Key('requestDetailLine_0')), findsOneWidget);
        expect(find.text('product-1'), findsOneWidget);
        expect(find.text('Quantity: 5'), findsOneWidget);
      },
    );

    testWidgets('approve button calls approveRequest with comment', (
      tester,
    ) async {
      await pumpDecision(tester, decisionRequest());
      await enterComment(tester, 'Budget approved');

      await tester.tap(find.byKey(const Key('approvalDecisionApproveButton')));
      await tester.pumpAndSettle();

      expect(fakeClient.approveCalls, ['req-1']);
      expect(fakeClient.approveComments, ['Budget approved']);
      expect(find.text('Request approved.'), findsOneWidget);
    });

    testWidgets('reject button calls rejectRequest with comment', (
      tester,
    ) async {
      await pumpDecision(tester, decisionRequest());
      await enterComment(tester, 'Too expensive');

      await tester.ensureVisible(
        find.byKey(const Key('approvalDecisionRejectButton')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('approvalDecisionRejectButton')));
      await tester.pumpAndSettle();

      expect(fakeClient.rejectCalls, ['req-1']);
      expect(fakeClient.rejectComments, ['Too expensive']);
      expect(find.text('Request rejected.'), findsOneWidget);
    });

    testWidgets('409 no_pending_approval shows already-decided message', (
      tester,
    ) async {
      fakeClient.approveError = const ApiException(
        statusCode: 409,
        code: 'conflict',
        message: 'No pending approval',
        details: {'reason': 'no_pending_approval'},
        traceId: 'trace-1',
      );
      await pumpDecision(tester, decisionRequest());

      await tester.tap(find.byKey(const Key('approvalDecisionApproveButton')));
      await tester.pumpAndSettle();

      expect(
        find.text('This request has already been decided by someone else.'),
        findsOneWidget,
      );
      expect(
        find.text('Unable to record the decision. Please try again.'),
        findsNothing,
      );
    });
  });
}

PurchaseRequest decisionRequest() {
  return PurchaseRequest(
    id: 'req-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: 'submitted',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
        estimatedUnitPrice: Money(amount: '25.00', currency: 'USD'),
      ),
    ],
    estimatedTotal: const Money(amount: '125.00', currency: 'USD'),
    hasIncompleteEstimate: false,
    budgetStatus: const BudgetStatus(
      remainingAmount: Money(amount: '40.00', currency: 'USD'),
      exceeds: true,
    ),
    approvalStep: const ApprovalStep(
      id: 'step-1',
      assignedMembershipId: 'approver-1',
      source: 'threshold_match',
      status: 'pending',
    ),
    createdAt: DateTime.utc(2026, 9, 13),
  );
}
