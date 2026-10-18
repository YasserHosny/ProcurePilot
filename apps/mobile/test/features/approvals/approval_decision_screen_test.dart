import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/approvals/approval_decision_screen.dart';

import '../../test_helpers.dart';

class DelayingRequestsApiClient extends FakeRequestsApiClient {
  Completer<PurchaseRequest>? inFlightCompleter;

  @override
  Future<PurchaseRequest> approveRequest(String requestId, {String? comment}) {
    approveCalls.add(requestId);
    approveComments.add(comment);
    if (inFlightCompleter != null) {
      return inFlightCompleter!.future;
    }
    return super.approveRequest(requestId, comment: comment);
  }

  @override
  Future<PurchaseRequest> rejectRequest(String requestId, {String? comment}) {
    rejectCalls.add(requestId);
    rejectComments.add(comment);
    if (inFlightCompleter != null) {
      return inFlightCompleter!.future;
    }
    return super.rejectRequest(requestId, comment: comment);
  }
}

void main() {
  group('ApprovalDecisionScreen', () {
    late DelayingRequestsApiClient fakeClient;

    setUp(() {
      fakeClient = DelayingRequestsApiClient();
    });

    Future<void> pumpDecision(
      WidgetTester tester,
      PurchaseRequest request, {
      String locale = 'en',
    }) async {
      await pumpWithServices(
        tester,
        locale: locale,
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
      'renders requester name, product name, and formatted quantity, never raw UUIDs',
      (tester) async {
        final req = decisionRequest(
          requesterName: 'Sarah Connor',
          requesterEmail: 'sarah@example.com',
          productName: 'Vegetable Oil 18L',
          quantity: '2.000000',
          packBaseQuantity: '18.000000',
          baseUnit: 'litre',
        );
        await pumpDecision(tester, req);

        expect(find.text('Requester: '), findsOneWidget);
        expect(find.text('Sarah Connor'), findsOneWidget);
        expect(find.textContaining('requester-uuid-1111'), findsNothing);

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
        expect(find.text('Vegetable Oil 18L'), findsOneWidget);
        expect(find.textContaining('product-uuid-2222'), findsNothing);
        expect(find.text('Quantity: 2 × 18 L'), findsOneWidget);
      },
    );

    testWidgets('falls back to requester email when name is missing', (
      tester,
    ) async {
      final req = decisionRequest(
        requesterName: null,
        requesterEmail: 'john@example.com',
      );
      await pumpDecision(tester, req);

      expect(find.text('john@example.com'), findsOneWidget);
      expect(find.textContaining('requester-uuid-1111'), findsNothing);
    });

    testWidgets(
      'falls back to localised unknown requester and unknown product when missing (en)',
      (tester) async {
        final req = decisionRequest(
          requesterName: null,
          requesterEmail: null,
          productName: null,
        );
        await pumpDecision(tester, req, locale: 'en');

        expect(find.text('Unknown requester'), findsOneWidget);
        expect(find.text('Unknown product'), findsOneWidget);
        expect(find.textContaining('requester-uuid-1111'), findsNothing);
        expect(find.textContaining('product-uuid-2222'), findsNothing);
      },
    );

    testWidgets(
      'falls back to localised unknown requester and unknown product when missing (ar)',
      (tester) async {
        final req = decisionRequest(
          requesterName: null,
          requesterEmail: null,
          productName: null,
        );
        await pumpDecision(tester, req, locale: 'ar');

        expect(find.text('مقدم طلب غير معروف'), findsOneWidget);
        expect(find.text('منتج غير معروف'), findsOneWidget);
        expect(find.textContaining('requester-uuid-1111'), findsNothing);
        expect(find.textContaining('product-uuid-2222'), findsNothing);
      },
    );

    testWidgets('formats quantity with Arabic-Indic digits in Arabic', (
      tester,
    ) async {
      final req = decisionRequest(
        quantity: '2.000000',
        packBaseQuantity: '18.000000',
        baseUnit: 'litre',
      );
      await pumpDecision(tester, req, locale: 'ar');

      expect(find.textContaining('٢ × ١٨ لتر'), findsOneWidget);
    });

    testWidgets('approve button disables controls while in flight and pops on success', (
      tester,
    ) async {
      fakeClient.inFlightCompleter = Completer<PurchaseRequest>();
      await pumpDecision(tester, decisionRequest());
      await enterComment(tester, 'Budget approved');

      await tester.tap(find.byKey(const Key('approvalDecisionApproveButton')));
      await tester.pump();

      // Controls must be disabled while in flight
      expect(
        tester.widget<FilledButton>(find.byKey(const Key('approvalDecisionApproveButton'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<FilledButton>(find.byKey(const Key('approvalDecisionRejectButton'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<OutlinedButton>(find.byKey(const Key('approvalDecisionCancelButton'))).onPressed,
        isNull,
      );

      // Complete the call
      fakeClient.inFlightCompleter!.complete(decisionRequest());
      await tester.pumpAndSettle();

      expect(fakeClient.approveCalls, ['req-1']);
      expect(fakeClient.approveComments, ['Budget approved']);

      // Popped back to caller screen
      expect(find.byType(ApprovalDecisionScreen), findsNothing);
      expect(find.text('Open'), findsOneWidget);
    });

    testWidgets('reject button disables controls while in flight and pops on success', (
      tester,
    ) async {
      fakeClient.inFlightCompleter = Completer<PurchaseRequest>();
      await pumpDecision(tester, decisionRequest());
      await enterComment(tester, 'Too expensive');

      await tester.ensureVisible(
        find.byKey(const Key('approvalDecisionRejectButton')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('approvalDecisionRejectButton')));
      await tester.pump();

      // Controls must be disabled while in flight
      expect(
        tester.widget<FilledButton>(find.byKey(const Key('approvalDecisionApproveButton'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<FilledButton>(find.byKey(const Key('approvalDecisionRejectButton'))).onPressed,
        isNull,
      );

      fakeClient.inFlightCompleter!.complete(decisionRequest());
      await tester.pumpAndSettle();

      expect(fakeClient.rejectCalls, ['req-1']);
      expect(fakeClient.rejectComments, ['Too expensive']);

      // Popped back to caller screen
      expect(find.byType(ApprovalDecisionScreen), findsNothing);
      expect(find.text('Open'), findsOneWidget);
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

    testWidgets('a manually drafted request shows no auto-prepared banner', (
      tester,
    ) async {
      await pumpDecision(tester, decisionRequest());
      expect(find.byKey(const Key('requestAutoPreparedBanner')), findsNothing);
    });

    testWidgets(
      'tells the approver a guardrail prepared the request from the winning quote',
      (tester) async {
        await pumpDecision(
          tester,
          decisionRequest(autoPreparedSupplier: 'Nile Bakery'),
        );

        expect(
          find.byKey(const Key('requestAutoPreparedBanner')),
          findsOneWidget,
        );
        expect(find.text('Prepared automatically by a guardrail'), findsOneWidget);
        expect(
          find.text(
            "This request was prepared automatically by a guardrail from Nile Bakery's quote.",
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets('auto-prepared banner is localised in Arabic', (tester) async {
      await pumpDecision(
        tester,
        decisionRequest(autoPreparedSupplier: 'مخبز النور'),
        locale: 'ar',
      );

      expect(find.text('أعدّته الضوابط تلقائيًا'), findsOneWidget);
      expect(
        find.text('أعدّت الضوابط هذا الطلب تلقائيًا من عرض سعر مخبز النور.'),
        findsOneWidget,
      );
    });
  });
}

PurchaseRequest decisionRequest({
  String? requesterName = 'Sarah Connor',
  String? requesterEmail = 'sarah@example.com',
  String? productName = 'Vegetable Oil 18L',
  String quantity = '5',
  String? packBaseQuantity,
  String? baseUnit,
  String? autoPreparedSupplier,
}) {
  return PurchaseRequest(
    id: 'req-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-uuid-1111',
    requesterName: requesterName,
    requesterEmail: requesterEmail,
    requiredByDate: '2026-10-01',
    status: 'submitted',
    lines: [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-uuid-2222',
        productName: productName,
        baseUnit: baseUnit,
        packBaseQuantity: packBaseQuantity,
        quantity: quantity,
        estimatedUnitPrice: const Money(amount: '25.00', currency: 'USD'),
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
    autoPrepared: autoPreparedSupplier == null
        ? null
        : AutoPreparedProvenance(
            guardrailId: 'guardrail-1',
            supplierName: autoPreparedSupplier,
            createdAt: DateTime.utc(2026, 10, 18),
          ),
  );
}
