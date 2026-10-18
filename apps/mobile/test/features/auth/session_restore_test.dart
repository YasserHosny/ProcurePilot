import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/features/auth/splash_screen.dart';

import '../../test_helpers.dart';

void main() {
  for (final web in [true, false]) {
    for (final biometric in [true, false]) {
      testWidgets(
        'stored session web=$web biometric=$biometric restores only when allowed',
        (tester) async {
          var refreshes = 0;
          final storage = FakeStorage()
            ..values['access_token'] = 'expired'
            ..values['refresh_token'] = 'stored-refresh'
            ..values['biometric_enabled'] = '$biometric';
          final token = makeAccessToken('branch_manager');
          final auth = AuthService(
            storage: storage,
            httpClient: MockClient((request) async {
              refreshes++;
              expect(
                request.url.queryParameters['grant_type'],
                'refresh_token',
              );
              expect(
                jsonDecode(request.body)['refresh_token'],
                'stored-refresh',
              );
              return http.Response(
                jsonEncode({'access_token': token, 'refresh_token': 'rotated'}),
                200,
              );
            }),
            supabaseUrl: 'https://auth.test',
            supabaseAnonKey: 'test-key',
          );
          final services = await pumpWithServices(
            tester,
            child: SplashScreen(isWeb: web),
            authService: auth,
            biometricAuth: web ? _UnexpectedBiometric() : FakeBiometricAuth(),
          );
          await tester.pumpAndSettle();
          final restores = web || biometric;
          expect(refreshes, restores ? 1 : 0);
          expect(find.text('Home'), restores ? findsOneWidget : findsNothing);
          expect(
            find.byKey(const Key('signInEmailField')),
            restores ? findsNothing : findsOneWidget,
          );
          if (restores) {
            expect(services.mobileApiClient.accessToken, token);
            expect(services.approvalsApiClient.accessToken, token);
            expect(services.requestsApiClient.accessToken, token);
            expect(storage.values['refresh_token'], 'rotated');
          }
        },
      );
    }
  }
  testWidgets('web refresh failure clears session and reaches sign-in', (
    tester,
  ) async {
    final storage = FakeStorage()
      ..values['access_token'] = 'expired'
      ..values['refresh_token'] = 'revoked';
    final auth = AuthService(
      storage: storage,
      httpClient: MockClient((_) async => http.Response('{}', 400)),
      supabaseUrl: 'https://auth.test',
      supabaseAnonKey: 'test-key',
    );
    await pumpWithServices(
      tester,
      child: const SplashScreen(isWeb: true),
      authService: auth,
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
    expect(auth.accessToken, isNull);
    expect(auth.refreshToken, isNull);
    expect(storage.values, isEmpty);
  });
  testWidgets('web without stored session reaches sign-in without refresh', (
    tester,
  ) async {
    await pumpWithServices(tester, child: const SplashScreen(isWeb: true));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
  });
  testWidgets('native cancelled biometric does not refresh', (tester) async {
    final auth = FakeAuthService(
      storage: FakeStorage()..values['biometric_enabled'] = 'true',
      httpClient: defaultTestHttpClient(),
      supabaseUrl: 'https://auth.test',
      supabaseAnonKey: 'test-key',
    )..loadStoredSessionValue = true;
    await pumpWithServices(
      tester,
      child: const SplashScreen(isWeb: false),
      authService: auth,
      biometricAuth: FakeBiometricAuth(authenticateResult: false),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
  });
}

class _UnexpectedBiometric extends FakeBiometricAuth {
  @override
  Future<bool> isAvailable() =>
      throw StateError('Web queried biometric hardware');
}
