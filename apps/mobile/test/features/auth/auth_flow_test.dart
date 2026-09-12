import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/features/auth/splash_screen.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';

import '../../test_helpers.dart';

void main() {
  group('Auth flow', () {
    testWidgets('first sign-in reaches the home screen', (tester) async {
      final auth = FakeAuthService(
        storage: FakeStorage(),
        httpClient: defaultTestHttpClient(),
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      )..tokenRole = 'branch_manager';

      await pumpWithServices(
        tester,
        child: const SignInScreen(),
        authService: auth,
        biometricAuth: FakeBiometricAuth(available: false),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('signInEmailField')),
        'user@example.com',
      );
      await tester.enterText(
        find.byKey(const Key('signInPasswordField')),
        'password',
      );
      await tester.tap(find.byKey(const Key('signInSubmitButton')));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Branch Manager'), findsOneWidget);
      expect(find.byKey(const Key('homeRequestItemsButton')), findsOneWidget);
      expect(auth.signInCalls, [
        ['user@example.com', 'password'],
      ]);
    });

    testWidgets('biometric-enable offer appears when hardware is available', (
      tester,
    ) async {
      final auth = FakeAuthService(
        storage: FakeStorage(),
        httpClient: defaultTestHttpClient(),
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      );

      await pumpWithServices(
        tester,
        child: const SignInScreen(),
        authService: auth,
        biometricAuth: FakeBiometricAuth(available: true),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('signInEmailField')),
        'user@example.com',
      );
      await tester.enterText(
        find.byKey(const Key('signInPasswordField')),
        'password',
      );
      await tester.tap(find.byKey(const Key('signInSubmitButton')));
      await tester.pumpAndSettle();

      expect(find.text('Enable biometric?'), findsWidgets);

      await tester.tap(find.byKey(const Key('biometricEnableButton')));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsOneWidget);
      expect(await auth.storage.read('biometric_enabled'), 'true');
    });

    testWidgets('no biometric offer when hardware is unavailable', (
      tester,
    ) async {
      final auth = FakeAuthService(
        storage: FakeStorage(),
        httpClient: defaultTestHttpClient(),
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      );

      await pumpWithServices(
        tester,
        child: const SignInScreen(),
        authService: auth,
        biometricAuth: FakeBiometricAuth(available: false),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('signInEmailField')),
        'user@example.com',
      );
      await tester.enterText(
        find.byKey(const Key('signInPasswordField')),
        'password',
      );
      await tester.tap(find.byKey(const Key('signInSubmitButton')));
      await tester.pumpAndSettle();

      expect(find.text('Enable biometric?'), findsNothing);
      expect(find.text('Home'), findsOneWidget);
      expect(await auth.storage.read('biometric_enabled'), isNull);
    });

    testWidgets(
      'next-launch biometric unlock reaches home without credentials',
      (tester) async {
        final storage = FakeStorage()
          ..values['access_token'] = makeAccessToken('branch_manager')
          ..values['refresh_token'] = 'refresh-token'
          ..values['biometric_enabled'] = 'true';

        final auth =
            FakeAuthService(
                storage: storage,
                httpClient: defaultTestHttpClient(),
                supabaseUrl: 'https://test.supabase.co',
                supabaseAnonKey: 'test-anon-key',
              )
              ..loadStoredSessionValue = true
              ..tokenRole = 'branch_manager';

        await pumpWithServices(
          tester,
          child: const SplashScreen(),
          authService: auth,
          biometricAuth: FakeBiometricAuth(
            available: true,
            authenticateResult: true,
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Home'), findsOneWidget);
        expect(find.text('Branch Manager'), findsOneWidget);
        expect(auth.signInCalls, isEmpty);
      },
    );

    testWidgets('sign-out invokes AuthService.signOut and returns to sign-in', (
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
      await auth.storage.write('access_token', auth.accessToken!);
      await auth.storage.write('refresh_token', auth.refreshToken!);

      await pumpWithServices(
        tester,
        child: const HomeScreen(),
        authService: auth,
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('signOutButton')));
      await tester.pumpAndSettle();

      expect(auth.signOutCalls, hasLength(1));
      expect(auth.accessToken, isNull);
      expect(auth.refreshToken, isNull);
      expect((auth.storage as FakeStorage).values, isEmpty);
      expect(find.byKey(const Key('signInEmailField')), findsOneWidget);
    });
  });
}
