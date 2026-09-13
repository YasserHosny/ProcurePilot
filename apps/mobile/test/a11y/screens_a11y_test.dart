import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/features/approvals/approval_decision_screen.dart';
import 'package:procurepilot_mobile/features/approvals/approval_queue_screen.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/features/delivery/delivery_confirmation_screen.dart';
import 'package:procurepilot_mobile/features/delivery/quality_issue_screen.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_form_screen.dart';

import '../test_helpers.dart';

/// Accessibility coverage for the sign-in, home, request form, and low-stock screens
/// (T047, 009-mobile-app-mvp Phase 8), mirroring the RIGOR (not the tooling — Flutter has no
/// axe-core equivalent) of `apps/web/tests/e2e/requests-a11y.spec.ts`'s WCAG 2.1 AA coverage.
///
/// Uses `flutter_test`'s own built-in accessibility-guideline API — the actual Flutter
/// equivalent of axe-core — against the real, already-built widget tree, not a hand-rolled
/// heuristic:
/// - `androidTapTargetGuideline` / `iOSTapTargetGuideline`: every interactive control meets the
///   platform's minimum tap-target size.
/// - `textContrastGuideline`: text meets a WCAG-equivalent contrast ratio against its background.
/// - `labeledTapTargetGuideline`: every tappable control has a semantic label a screen reader
///   can announce.
///
/// Each of these guidelines is checked with `await expectLater(tester, meetsGuideline(...))`
/// inside a `tester.ensureSemantics()` handle, which populates the semantics tree for the
/// duration of the test. The handle is disposed in a `finally` block rather than via
/// `addTearDown` — on this Flutter version, `addTearDown`-scheduled disposal was not reliably
/// observed before the test framework's own end-of-test SemanticsHandle check on the happy path.
Future<void> _checkGuidelines(WidgetTester tester) async {
  final handle = tester.ensureSemantics();
  try {
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  } finally {
    handle.dispose();
  }
}

void main() {
  group('Sign-in screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      await pumpWithServices(
        tester,
        child: const SignInScreen(),
        authService: FakeAuthService(
          storage: FakeStorage(),
          httpClient: defaultTestHttpClient(),
          supabaseUrl: 'https://test.supabase.co',
          supabaseAnonKey: 'test-anon-key',
        ),
        biometricAuth: FakeBiometricAuth(available: false),
      );
      await tester.pumpAndSettle();

      await _checkGuidelines(tester);

      // Screen-reader-navigation smoke check: the key controls a screen reader user needs are
      // actually reachable in the semantics tree, not just visually present.
      expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
      expect(find.byKey(const Key('signInPasswordField')), findsOneWidget);
      expect(find.byKey(const Key('signInSubmitButton')), findsOneWidget);
    });
  });

  group('Home screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      final auth =
          FakeAuthService(
              storage: FakeStorage(),
              httpClient: defaultTestHttpClient(),
              supabaseUrl: 'https://test.supabase.co',
              supabaseAnonKey: 'test-anon-key',
            )
            ..accessToken = makeAccessToken('branch_manager')
            ..refreshToken = 'refresh-token'
            ..tokenRole = 'branch_manager';

      await pumpWithServices(
        tester,
        child: const HomeScreen(),
        authService: auth,
      );
      await tester.pumpAndSettle();

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('homeRequestItemsButton')), findsOneWidget);
    });
  });

  group('Request form screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      final fakeClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'branch-1',
            name: 'Main Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ];

      await pumpWithServices(
        tester,
        child: const RequestFormScreen(),
        requestsApiClient: fakeClient,
      );
      await tester.pumpAndSettle();

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('requestFormBranchField')), findsOneWidget);
      expect(find.byKey(const Key('requestFormSubmitButton')), findsOneWidget);
    });
  });

  group('Low-stock report screen accessibility', () {
    final testProduct = CatalogueProduct(
      id: 'product-1',
      tenantName: 'Fresh Whole Milk 2L',
      canonicalName: 'Fresh Whole Milk 2L',
      baseUnit: 'bottle',
      status: 'active',
      createdAt: DateTime.now(),
    );

    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      final fakeRequestsClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'branch-1',
            name: 'Downtown Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ]
        ..catalogueSearchResults = [testProduct];

      await pumpWithServices(
        tester,
        child: LowStockReportScreen(
          initialProduct: testProduct,
          initialBranchId: 'branch-1',
        ),
        requestsApiClient: fakeRequestsClient,
      );
      await tester.pumpAndSettle();

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('lowStockSubmitButton')), findsOneWidget);
    });
  });

  // T035 (010-mobile-approvals-receipt): the four screens this chunk adds. Approval decision,
  // delivery confirmation, and quality-issue report all read a PurchaseRequest from their
  // route arguments rather than a constructor parameter, so each is reached via a real
  // Navigator push (mirroring how this codebase's own widget tests for these screens already
  // do it) rather than pumped as `child` directly.
  group('Approval queue screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      final fakeApprovals = FakeApprovalsApiClient()
        ..pendingResults = [_sampleRequest(status: 'submitted')];

      await pumpWithServices(
        tester,
        child: const ApprovalQueueScreen(),
        approvalsApiClient: fakeApprovals,
      );
      await tester.pumpAndSettle();

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('approvalQueueList')), findsOneWidget);
    });
  });

  group('Approval decision screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      await _pumpArgScreen(
        tester,
        request: _sampleRequest(status: 'submitted'),
        builder: (_) => const ApprovalDecisionScreen(),
      );

      await _checkGuidelines(tester);

      expect(
        find.byKey(const Key('approvalDecisionApproveButton')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('approvalDecisionRejectButton')),
        findsOneWidget,
      );
    });
  });

  group('Delivery confirmation screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      await _pumpArgScreen(
        tester,
        request: _sampleRequest(status: 'ordered'),
        builder: (_) => const DeliveryConfirmationScreen(),
      );

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('deliverySubmitButton')), findsOneWidget);
    });
  });

  group('Quality issue report screen accessibility', () {
    testWidgets('meets tap-target, contrast, and label guidelines', (
      tester,
    ) async {
      await _pumpArgScreen(
        tester,
        request: _sampleRequest(status: 'delivered'),
        builder: (_) => const QualityIssueScreen(),
      );

      await _checkGuidelines(tester);

      expect(find.byKey(const Key('qualityIssueSubmitButton')), findsOneWidget);
    });
  });
}

/// Pushes [builder]'s screen with [request] as its route argument, the same
/// Navigator-push pattern this codebase's own widget tests for these
/// argument-driven screens already use (they read `PurchaseRequest` from
/// `ModalRoute.of(context)?.settings.arguments`, not a constructor field).
Future<void> _pumpArgScreen(
  WidgetTester tester, {
  required PurchaseRequest request,
  required WidgetBuilder builder,
}) async {
  await pumpWithServices(
    tester,
    child: Builder(
      builder: (context) => ElevatedButton(
        onPressed: () {
          Navigator.of(context).push(
            MaterialPageRoute(
              settings: RouteSettings(arguments: request),
              builder: builder,
            ),
          );
        },
        child: const Text('Open'),
      ),
    ),
    requestsApiClient: FakeRequestsApiClient(),
    cameraCapture: FakeCameraCapture(available: false),
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

PurchaseRequest _sampleRequest({required String status}) {
  return PurchaseRequest(
    id: 'req-a11y-1',
    branchId: 'branch-1',
    requestedByMembershipId: 'requester-1',
    requiredByDate: '2026-10-01',
    status: status,
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
    approvalStep: const ApprovalStep(
      id: 'step-1',
      assignedMembershipId: 'approver-1',
      source: 'threshold_match',
      status: 'pending',
    ),
    createdAt: DateTime.utc(2026, 9, 13),
  );
}
