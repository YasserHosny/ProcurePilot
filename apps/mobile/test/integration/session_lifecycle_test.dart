import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';
import 'package:procurepilot_mobile/core/api/session_http_client.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/core/auth/biometric_gate.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/main.dart';

import '../test_helpers.dart';

void main() {
  for (final fails in [false, true]) {
    testWidgets(
      'runtime refresh failure=$fails synchronizes clients and navigation',
      (tester) async {
        final token = makeAccessToken('branch_manager');
        final auth = AuthService(
          storage: FakeStorage(),
          httpClient: MockClient((request) async {
            if (request.url.queryParameters['grant_type'] == 'refresh_token' &&
                fails) {
              return http.Response('{}', 400);
            }
            return http.Response(
              jsonEncode({
                'access_token':
                    request.url.queryParameters['grant_type'] == 'password'
                    ? '${token}initial'
                    : token,
                'refresh_token': 'refresh',
              }),
              200,
            );
          }),
          supabaseUrl: 'https://auth.test',
          supabaseAnonKey: 'test-key',
        );
        var attempts = 0;
        final transport = SessionHttpClient(
          inner: MockClient((_) async {
            attempts++;
            return http.Response(
              attempts == 1 ? '{}' : '{"items":[]}',
              attempts == 1 ? 401 : 200,
            );
          }),
          authService: auth,
          apiBaseUrl: 'https://api.test',
        );
        final mobile = MobileApiClient(
          apiBaseUrl: 'https://api.test',
          httpClient: transport,
        );
        final approvals = ApprovalsApiClient(
          apiBaseUrl: 'https://api.test',
          httpClient: transport,
        );
        final requests = RequestsApiClient(
          apiBaseUrl: 'https://api.test',
          httpClient: transport,
        );
        await tester.pumpWidget(
          ProcurePilotApp(
            i18n: await loadTestI18n(),
            authService: auth,
            biometricGate: BiometricGate(
              biometricAuth: FakeBiometricAuth(),
              authService: auth,
            ),
            mobileApiClient: mobile,
            approvalsApiClient: approvals,
            requestsApiClient: requests,
          ),
        );
        await tester.pumpAndSettle();
        await auth.signIn('test@example.com', 'test-password');
        Navigator.of(tester.element(find.byType(SignInScreen)))
            .pushNamed('/home');
        await tester.pumpAndSettle();
        expect(find.text('Home'), findsOneWidget);
        if (fails) {
          await expectLater(
            approvals.listPendingApprovals(),
            throwsA(isA<AuthException>()),
          );
        } else {
          await approvals.listPendingApprovals();
        }
        await tester.pumpAndSettle();
        expect(mobile.accessToken, fails ? isNull : token);
        expect(approvals.accessToken, fails ? isNull : token);
        expect(requests.accessToken, fails ? isNull : token);
        if (fails) {
          expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
          expect(
            Navigator.of(tester.element(find.byType(SignInScreen))).canPop(),
            isFalse,
          );
        } else {
          await tester.tap(find.byKey(const Key('signOutButton')));
          await tester.pumpAndSettle();
          expect(mobile.accessToken, isNull);
          expect(approvals.accessToken, isNull);
          expect(requests.accessToken, isNull);
          expect((auth.storage as FakeStorage).values, isEmpty);
          expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
        }
      },
    );
  }
}
