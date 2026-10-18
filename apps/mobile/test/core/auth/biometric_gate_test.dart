import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:local_auth/local_auth.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/core/auth/biometric_gate.dart';

class _FakeStorage implements SecureStorage {
  final _values = <String, String>{};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async => _values[key] = value;

  @override
  Future<void> delete(String key) async => _values.remove(key);

  @override
  Future<void> deleteAll() async => _values.clear();
}

class _FakeBiometricAuth implements BiometricAuth {
  _FakeBiometricAuth({this.available = true, this.authenticateResult = true});

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

AuthService _authService({required int refreshStatus}) {
  final client = MockClient((request) async {
    return http.Response(
      jsonEncode({'access_token': 'A', 'refresh_token': 'R'}),
      refreshStatus,
    );
  });
  final storage = _FakeStorage().._values['refresh_token'] = 'R';
  return AuthService(
    storage: storage,
    httpClient: client,
    supabaseUrl: 'https://test.supabase.co',
    supabaseAnonKey: 'key',
  );
}

void main() {
  group('BiometricGate', () {
    test('returns notAvailable when device has no biometrics', () async {
      final gate = BiometricGate(
        biometricAuth: _FakeBiometricAuth(available: false),
        authService: _authService(refreshStatus: 200),
      );

      final result = await gate.unlock(localizedReason: 'Authenticate to unlock');

      expect(result, BiometricResult.notAvailable);
    });

    test('returns cancelled when user cancels biometric prompt', () async {
      final gate = BiometricGate(
        biometricAuth: _FakeBiometricAuth(authenticateResult: false),
        authService: _authService(refreshStatus: 200),
      );

      final result = await gate.unlock(localizedReason: 'Authenticate to unlock');

      expect(result, BiometricResult.cancelled);
    });

    test('returns success when biometric passes and refresh succeeds', () async {
      final gate = BiometricGate(
        biometricAuth: _FakeBiometricAuth(),
        authService: _authService(refreshStatus: 200),
      );

      final result = await gate.unlock(localizedReason: 'Authenticate to unlock');

      expect(result, BiometricResult.success);
    });

    test('returns failed when biometric passes but refresh fails', () async {
      final gate = BiometricGate(
        biometricAuth: _FakeBiometricAuth(),
        authService: _authService(refreshStatus: 401),
      );

      final result = await gate.unlock(localizedReason: 'Authenticate to unlock');

      expect(result, BiometricResult.failed);
    });
  });

  group('LocalAuthAdapter and BiometricGate with platform fakes', () {
    test('returns false and notAvailable when plugin throws PlatformException', () async {
      final fake = _FakePlatformExceptionLocalAuth();
      final adapter = LocalAuthAdapter(fake, isWeb: false);

      expect(await adapter.isAvailable(), isFalse);
      expect(await adapter.authenticate(localizedReason: 'Test'), isFalse);

      final gate = BiometricGate(
        biometricAuth: adapter,
        authService: _authService(refreshStatus: 200),
      );
      final result = await gate.unlock(localizedReason: 'Test');
      expect(result, BiometricResult.notAvailable);
      expect(fake.canCheckBiometricsCalls, greaterThanOrEqualTo(1));
    });

    test('returns false and notAvailable when plugin throws MissingPluginException', () async {
      final fake = _FakeMissingPluginExceptionLocalAuth();
      final adapter = LocalAuthAdapter(fake, isWeb: false);

      expect(await adapter.isAvailable(), isFalse);
      expect(await adapter.authenticate(localizedReason: 'Test'), isFalse);

      final gate = BiometricGate(
        biometricAuth: adapter,
        authService: _authService(refreshStatus: 200),
      );
      final result = await gate.unlock(localizedReason: 'Test');
      expect(result, BiometricResult.notAvailable);
      expect(fake.canCheckBiometricsCalls, greaterThanOrEqualTo(1));
    });

    test('returns false when isWeb: true and fake is never called', () async {
      final fake = _FakePlatformExceptionLocalAuth();
      final adapter = LocalAuthAdapter(fake, isWeb: true);

      expect(await adapter.isAvailable(), isFalse);
      expect(await adapter.authenticate(localizedReason: 'Test'), isFalse);

      final gate = BiometricGate(
        biometricAuth: adapter,
        authService: _authService(refreshStatus: 200),
      );
      final result = await gate.unlock(localizedReason: 'Test');
      expect(result, BiometricResult.notAvailable);

      expect(fake.canCheckBiometricsCalls, equals(0));
      expect(fake.getAvailableBiometricsCalls, equals(0));
      expect(fake.authenticateCalls, equals(0));
    });

    test('returns true when normal fake has biometrics enrolled (regression)', () async {
      final fake = _FakeEnrolledLocalAuth();
      final adapter = LocalAuthAdapter(fake, isWeb: false);

      expect(await adapter.isAvailable(), isTrue);
      expect(await adapter.authenticate(localizedReason: 'Test'), isTrue);

      final gate = BiometricGate(
        biometricAuth: adapter,
        authService: _authService(refreshStatus: 200),
      );
      final result = await gate.unlock(localizedReason: 'Test');
      expect(result, BiometricResult.success);

      expect(fake.canCheckBiometricsCalls, greaterThanOrEqualTo(1));
      expect(fake.getAvailableBiometricsCalls, greaterThanOrEqualTo(1));
      expect(fake.authenticateCalls, equals(2));
    });
  });
}

class _FakePlatformExceptionLocalAuth extends LocalAuthentication {
  int canCheckBiometricsCalls = 0;
  int getAvailableBiometricsCalls = 0;
  int authenticateCalls = 0;

  @override
  Future<bool> get canCheckBiometrics {
    canCheckBiometricsCalls++;
    throw PlatformException(code: 'ERROR', message: 'Biometrics unavailable');
  }

  @override
  Future<List<BiometricType>> getAvailableBiometrics() {
    getAvailableBiometricsCalls++;
    throw PlatformException(code: 'ERROR', message: 'Biometrics unavailable');
  }

  @override
  Future<bool> authenticate({
    required String localizedReason,
    Iterable<dynamic>? authMessages,
    AuthenticationOptions options = const AuthenticationOptions(),
  }) {
    authenticateCalls++;
    throw PlatformException(code: 'ERROR', message: 'Biometrics unavailable');
  }
}

class _FakeMissingPluginExceptionLocalAuth extends LocalAuthentication {
  int canCheckBiometricsCalls = 0;
  int getAvailableBiometricsCalls = 0;
  int authenticateCalls = 0;

  @override
  Future<bool> get canCheckBiometrics {
    canCheckBiometricsCalls++;
    throw MissingPluginException(
      'No implementation found for method canCheckBiometrics on channel plugins.flutter.io/local_auth',
    );
  }

  @override
  Future<List<BiometricType>> getAvailableBiometrics() {
    getAvailableBiometricsCalls++;
    throw MissingPluginException(
      'No implementation found for method getAvailableBiometrics on channel plugins.flutter.io/local_auth',
    );
  }

  @override
  Future<bool> authenticate({
    required String localizedReason,
    Iterable<dynamic>? authMessages,
    AuthenticationOptions options = const AuthenticationOptions(),
  }) {
    authenticateCalls++;
    throw MissingPluginException(
      'No implementation found for method authenticate on channel plugins.flutter.io/local_auth',
    );
  }
}

class _FakeEnrolledLocalAuth extends LocalAuthentication {
  int canCheckBiometricsCalls = 0;
  int getAvailableBiometricsCalls = 0;
  int authenticateCalls = 0;

  @override
  Future<bool> get canCheckBiometrics async {
    canCheckBiometricsCalls++;
    return true;
  }

  @override
  Future<List<BiometricType>> getAvailableBiometrics() async {
    getAvailableBiometricsCalls++;
    return const [BiometricType.fingerprint];
  }

  @override
  Future<bool> authenticate({
    required String localizedReason,
    Iterable<dynamic>? authMessages,
    AuthenticationOptions options = const AuthenticationOptions(),
  }) async {
    authenticateCalls++;
    return true;
  }
}
