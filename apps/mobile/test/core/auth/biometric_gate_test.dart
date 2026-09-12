import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
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
}
