import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/core/auth/biometric_gate.dart';
import 'package:procurepilot_mobile/core/i18n/i18n_loader.dart';
import 'package:procurepilot_mobile/features/auth/biometric_offer_screen.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';
import 'package:procurepilot_mobile/features/service_provider.dart';

/// A bundle that serves a minimal English catalogue for widget tests.
class TestAssetBundle extends AssetBundle {
  TestAssetBundle(this._data);

  final Map<String, String> _data;

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final value = _data[key];
    if (value == null) throw FlutterError('Missing asset: $key');
    return value;
  }

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

/// Returns a loaded [I18nLoader] backed by a minimal English catalogue.
Future<I18nLoader> loadTestI18n() async {
  final bundle = TestAssetBundle({
    '../../packages/i18n/en.json': jsonEncode({
      'common': {
        'brandName': 'ProcurePilot',
        'loading': 'Loading...',
        'comingSoon': 'Coming Soon',
        'roles': {
          'owner': 'Owner',
          'buyer': 'Buyer',
          'branch_manager': 'Branch Manager',
          'approver': 'Approver',
          'viewer': 'Viewer',
        },
      },
      'auth': {
        'signin': {
          'title': 'Sign in',
          'subtitle': 'Enter credentials',
          'emailLabel': 'Email',
          'emailPlaceholder': 'you@example.com',
          'emailRequired': 'Email required',
          'emailInvalid': 'Invalid email',
          'passwordLabel': 'Password',
          'passwordPlaceholder': 'Password',
          'passwordRequired': 'Password required',
          'submitButton': 'Sign In',
          'submittingButton': 'Signing in...',
          'genericError': 'Sign in failed',
          'showPassword': 'Show',
          'hidePassword': 'Hide',
        },
        'biometric': {
          'enableTitle': 'Enable biometric?',
          'enableMessage': 'Use biometric next time',
          'enableButton': 'Enable',
          'declineButton': 'Not now',
          'unlockTitle': 'Unlock',
          'unlockPrompt': 'Use biometric',
          'fallbackButton': 'Use password',
        },
      },
      'mobileHome': {
        'title': 'Home',
        'roleLabel': 'Your role',
        'requestItems': 'Request items',
        'pendingApprovalsCount': '{{count}} pending',
        'pendingCountError': 'Count error',
        'signOut': 'Sign out',
      },
    }),
    '../../packages/i18n/ar.json': jsonEncode({}),
  });
  final i18n = I18nLoader(bundle: bundle);
  await i18n.load('en');
  return i18n;
}

/// In-memory secure storage for tests.
class FakeStorage implements SecureStorage {
  final _values = <String, String>{};

  /// Exposed so tests can assert on stored values.
  Map<String, String> get values => _values;

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async => _values[key] = value;

  @override
  Future<void> delete(String key) async => _values.remove(key);

  @override
  Future<void> deleteAll() async => _values.clear();
}

/// Fake biometric implementation for tests.
class FakeBiometricAuth implements BiometricAuth {
  FakeBiometricAuth({this.available = true, this.authenticateResult = true});

  bool available;
  bool authenticateResult;
  String? lastReason;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<bool> authenticate({required String localizedReason}) async {
    lastReason = localizedReason;
    return authenticateResult;
  }
}

/// Fake device registrar for tests.
class FakeDeviceRegistrar implements DeviceRegistrar {
  final deleted = <String>[];

  @override
  Future<void> deleteDevice(String deviceId) async {
    deleted.add(deviceId);
  }
}

/// Builds a fake access token containing [member_role]. No signature is
/// included because the mobile UI only decodes claims; verification is the
/// API's job.
String makeAccessToken(String role) {
  String encode(String input) {
    return base64Url.encode(utf8.encode(input)).replaceAll('=', '');
  }

  final header = encode(jsonEncode({'alg': 'none'}));
  final payload = encode(
    jsonEncode({
      'sub': '00000000-0000-0000-0000-000000000000',
      'tenant_id': '00000000-0000-0000-0000-000000000000',
      'member_role': role,
    }),
  );
  return '$header.$payload.';
}

/// A fake [AuthService] that records calls and never hits the network.
class FakeAuthService extends AuthService {
  FakeAuthService({
    required super.storage,
    required super.httpClient,
    required super.supabaseUrl,
    required super.supabaseAnonKey,
  });

  final signInCalls = <List<String>>[];
  final signOutCalls = <DeviceRegistrar?>[];
  bool loadStoredSessionValue = false;
  String tokenRole = 'branch_manager';
  bool refreshShouldFail = false;

  Future<void> _writeTokens() async {
    await storage.write('access_token', accessToken ?? '');
    await storage.write('refresh_token', refreshToken ?? '');
  }

  @override
  Future<void> signIn(String email, String password) async {
    signInCalls.add([email, password]);
    accessToken = makeAccessToken(tokenRole);
    refreshToken = 'refresh-token';
    await _writeTokens();
  }

  @override
  Future<bool> loadStoredSession() async {
    if (loadStoredSessionValue) {
      accessToken = makeAccessToken(tokenRole);
      refreshToken = 'refresh-token';
      await _writeTokens();
    }
    return loadStoredSessionValue;
  }

  @override
  Future<void> refreshSession() async {
    if (refreshShouldFail) {
      throw const AuthException('Refresh failed');
    }
    accessToken = makeAccessToken(tokenRole);
    refreshToken = 'refresh-token';
    await _writeTokens();
  }

  @override
  Future<void> signOut({DeviceRegistrar? deviceRegistrar}) async {
    signOutCalls.add(deviceRegistrar);
    if (registeredDeviceId != null &&
        registeredDeviceId!.isNotEmpty &&
        deviceRegistrar != null) {
      await deviceRegistrar.deleteDevice(registeredDeviceId!);
    }
    await storage.deleteAll();
    accessToken = null;
    refreshToken = null;
    registeredDeviceId = null;
  }
}

/// A default HTTP client that never issues a real request.
http.Client defaultTestHttpClient() =>
    MockClient((_) async => http.Response('', 500));

/// Wraps [child] with a fully wired, test-only service layer and a route table
/// that mirrors the production app.
class TestServiceProvider extends StatelessWidget {
  const TestServiceProvider({
    super.key,
    required this.authService,
    required this.biometricAuth,
    required this.mobileApiClient,
    required this.approvalsApiClient,
    required this.i18n,
    required this.child,
  });

  final AuthService authService;
  final BiometricAuth biometricAuth;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final I18nLoader i18n;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ServiceProvider(
      authService: authService,
      biometricGate: BiometricGate(
        biometricAuth: biometricAuth,
        authService: authService,
      ),
      mobileApiClient: mobileApiClient,
      approvalsApiClient: approvalsApiClient,
      i18n: i18n,
      child: MaterialApp(
        locale: const Locale('en'),
        builder: (context, child) => Directionality(
          textDirection: TextDirection.ltr,
          child: child ?? const SizedBox.shrink(),
        ),
        routes: {
          '/signIn': (_) => const SignInScreen(),
          '/biometricOffer': (_) => const BiometricOfferScreen(),
          '/home': (_) => const HomeScreen(),
        },
        home: child,
      ),
    );
  }
}

/// Pumps a feature screen with a fully wired, test-only service layer.
Future<TestServiceProvider> pumpWithServices(
  WidgetTester tester, {
  required Widget child,
  AuthService? authService,
  BiometricAuth? biometricAuth,
  MobileApiClient? mobileApiClient,
  ApprovalsApiClient? approvalsApiClient,
  I18nLoader? i18n,
}) async {
  final i18nValue = i18n ?? await loadTestI18n();
  final authServiceValue =
      authService ??
      FakeAuthService(
        storage: FakeStorage(),
        httpClient: defaultTestHttpClient(),
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      );
  final widget = TestServiceProvider(
    authService: authServiceValue,
    biometricAuth: biometricAuth ?? FakeBiometricAuth(),
    mobileApiClient:
        mobileApiClient ?? MobileApiClient(apiBaseUrl: 'https://test.api'),
    approvalsApiClient:
        approvalsApiClient ??
        ApprovalsApiClient(apiBaseUrl: 'https://test.api'),
    i18n: i18nValue,
    child: child,
  );
  await tester.pumpWidget(widget);
  return widget;
}
