import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('HomeScreen', () {
    ApprovalsApiClient pendingClient({required int count}) {
      return ApprovalsApiClient(
        apiBaseUrl: 'https://test.api',
        httpClient: MockClient((request) async {
          final items = List<Map<String, dynamic>>.generate(
            count,
            (_) => <String, dynamic>{},
          );
          return http.Response(
            jsonEncode({'items': items, 'next_cursor': null}),
            200,
          );
        }),
      );
    }

    /// FR-009: no approve/reject *control* may exist on the home screen. The
    /// role label "Approver" is read-only text, not a control, so it is
    /// excluded from this check.
    Finder approvalControl() => find.descendant(
      of: find.byWidgetPredicate(
        (widget) =>
            widget is ButtonStyleButton ||
            widget is IconButton ||
            widget is InkWell ||
            widget is GestureDetector,
      ),
      matching: find.textContaining('approve', findRichText: true),
    );

    Finder rejectionControl() => find.descendant(
      of: find.byWidgetPredicate(
        (widget) =>
            widget is ButtonStyleButton ||
            widget is IconButton ||
            widget is InkWell ||
            widget is GestureDetector,
      ),
      matching: find.textContaining('reject', findRichText: true),
    );

    testWidgets('branch manager sees primary action and no approval controls', (
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

      expect(find.byKey(const Key('homeRequestItemsButton')), findsOneWidget);
      expect(find.byKey(const Key('pendingApprovalsCount')), findsNothing);
      expect(approvalControl(), findsNothing);
      expect(rejectionControl(), findsNothing);
    });

    testWidgets('approver sees pending count and no approval controls', (
      tester,
    ) async {
      final auth =
          FakeAuthService(
              storage: FakeStorage(),
              httpClient: defaultTestHttpClient(),
              supabaseUrl: 'https://test.supabase.co',
              supabaseAnonKey: 'test-anon-key',
            )
            ..accessToken = makeAccessToken('approver')
            ..refreshToken = 'refresh-token'
            ..tokenRole = 'approver';

      await pumpWithServices(
        tester,
        child: const HomeScreen(),
        authService: auth,
        approvalsApiClient: pendingClient(count: 3),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('homeRequestItemsButton')), findsNothing);
      expect(find.text('3 pending'), findsOneWidget);
      expect(find.byKey(const Key('pendingApprovalsCount')), findsOneWidget);
      expect(approvalControl(), findsNothing);
      expect(rejectionControl(), findsNothing);
    });

    testWidgets('zero pending count is shown for an approver', (tester) async {
      final auth =
          FakeAuthService(
              storage: FakeStorage(),
              httpClient: defaultTestHttpClient(),
              supabaseUrl: 'https://test.supabase.co',
              supabaseAnonKey: 'test-anon-key',
            )
            ..accessToken = makeAccessToken('approver')
            ..refreshToken = 'refresh-token'
            ..tokenRole = 'approver';

      await pumpWithServices(
        tester,
        child: const HomeScreen(),
        authService: auth,
        approvalsApiClient: pendingClient(count: 0),
      );
      await tester.pumpAndSettle();

      expect(find.text('0 pending'), findsOneWidget);
      expect(approvalControl(), findsNothing);
      expect(rejectionControl(), findsNothing);
    });
  });
}
