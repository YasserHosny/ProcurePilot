import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/auth/biometric_gate.dart';
import 'package:procurepilot_mobile/features/notifications/notification_permission.dart';
import 'package:procurepilot_mobile/features/notifications/push_notification_registration.dart';
import 'package:procurepilot_mobile/features/requests/request_list_screen.dart';
import 'package:procurepilot_mobile/main.dart' as app;

import '../../test_helpers.dart';

void main() {
  group('push notifications', () {
    testWidgets('permission granted registers the generated token', (
      tester,
    ) async {
      final permission = FakeNotificationPermission.granted(
        token: 'placeholder-token-1',
      );
      final mobileClient = FakeMobileApiClient();

      await pumpProcurePilotApp(
        tester,
        permission: permission,
        mobileApiClient: mobileClient,
      );
      await tester.pumpAndSettle();

      expect(permission.requestCount, 1);
      expect(mobileClient.registerDeviceCalls, hasLength(1));
      expect(
        mobileClient.registerDeviceCalls.single['pushToken'],
        'placeholder-token-1',
      );
      expect(
        mobileClient.registerDeviceCalls.single['platform'],
        isA<DevicePlatform>(),
      );
    });

    testWidgets('permission declined leaves request navigation functional', (
      tester,
    ) async {
      final permission = FakeNotificationPermission.declined();
      final mobileClient = FakeMobileApiClient();
      final requestsClient = FakeRequestsApiClient()
        ..listResults = [
          decidedRequest(id: 'req-visible', status: 'approved'),
        ];

      await PushNotificationRegistration(
        permission: permission,
        mobileApiClient: mobileClient,
      ).registerIfGranted();

      await pumpWithServices(
        tester,
        child: const RequestListScreen(),
        mobileApiClient: mobileClient,
        requestsApiClient: requestsClient,
      );
      await tester.pumpAndSettle();

      expect(permission.requestCount, 1);
      expect(mobileClient.registerDeviceCalls, isEmpty);
      expect(find.byKey(const Key('requestStatus_approved')), findsOneWidget);

      await tester.tap(find.byKey(const Key('requestListItem_0')));
      await tester.pumpAndSettle();

      expect(find.text('Approved'), findsWidgets);
      expect(find.textContaining('Decision comment'), findsOneWidget);
      expect(find.text('Approved on next open'), findsOneWidget);
    });

    testWidgets('notification tap fetches the request and opens detail', (
      tester,
    ) async {
      final permission = FakeNotificationPermission.granted(
        token: 'placeholder-token-2',
      );
      final requestsClient = FakeRequestsApiClient();
      requestsClient.getRequestResults['req-deep-link'] = decidedRequest(
        id: 'req-deep-link',
        status: 'rejected',
        comment: 'Rejected after review',
      );

      await pumpProcurePilotApp(
        tester,
        permission: permission,
        requestsApiClient: requestsClient,
      );
      await tester.pumpAndSettle();

      permission.tap({'purchase_request_id': 'req-deep-link'});
      await tester.pumpAndSettle();

      expect(requestsClient.getRequestCalls, ['req-deep-link']);
      expect(
        find.byKey(const Key('approvalStepStatus_rejected')),
        findsOneWidget,
      );
      expect(find.text('Rejected after review'), findsOneWidget);
    });
  });
}

class FakeNotificationPermission implements NotificationPermission {
  FakeNotificationPermission._(this._result);

  factory FakeNotificationPermission.granted({required String token}) {
    return FakeNotificationPermission._(
      NotificationPermissionResult.granted(token),
    );
  }

  factory FakeNotificationPermission.declined() {
    return FakeNotificationPermission._(NotificationPermissionResult.declined);
  }

  final NotificationPermissionResult _result;
  final _tapController = StreamController<Map<String, String>>.broadcast();
  int requestCount = 0;

  @override
  Future<NotificationPermissionResult> requestPermission() async {
    requestCount += 1;
    return _result;
  }

  @override
  Stream<Map<String, String>> get notificationTaps => _tapController.stream;

  void tap(Map<String, String> payload) {
    _tapController.add(payload);
  }
}

Future<void> pumpProcurePilotApp(
  WidgetTester tester, {
  required FakeNotificationPermission permission,
  FakeMobileApiClient? mobileApiClient,
  FakeRequestsApiClient? requestsApiClient,
}) async {
  final authService = FakeAuthService(
    storage: FakeStorage(),
    httpClient: defaultTestHttpClient(),
    supabaseUrl: 'https://test.supabase.co',
    supabaseAnonKey: 'test-anon-key',
  )..accessToken = makeAccessToken('branch_manager');
  final biometricGate = BiometricGate(
    biometricAuth: FakeBiometricAuth(),
    authService: authService,
  );

  await tester.pumpWidget(
    app.ProcurePilotApp(
      i18n: await loadTestI18n(),
      authService: authService,
      biometricGate: biometricGate,
      mobileApiClient: mobileApiClient ?? FakeMobileApiClient(),
      approvalsApiClient: ApprovalsApiClient(apiBaseUrl: 'https://test.api'),
      requestsApiClient: requestsApiClient ?? FakeRequestsApiClient(),
      notificationPermission: permission,
    ),
  );
}

PurchaseRequest decidedRequest({
  required String id,
  required String status,
  String comment = 'Approved on next open',
}) {
  return PurchaseRequest(
    id: id,
    branchId: 'branch-1',
    requestedByMembershipId: 'member-1',
    requiredByDate: '2026-10-01',
    status: status,
    lines: [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '3',
      ),
    ],
    hasIncompleteEstimate: false,
    approvalStep: ApprovalStep(
      id: 'step-1',
      assignedMembershipId: 'approver-1',
      source: 'threshold_match',
      status: status,
      comment: comment,
      decidedByMembershipId: 'approver-1',
      decidedAt: DateTime.utc(2026, 9, 12, 10, 0, 0),
    ),
    createdAt: DateTime.utc(2026, 9, 12, 9, 0, 0),
  );
}
