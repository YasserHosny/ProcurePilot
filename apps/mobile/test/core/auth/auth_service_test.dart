import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';

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

class _FakeDeviceRegistrar implements DeviceRegistrar {
  final deleted = <String>[];
  bool fail = false;

  @override
  Future<void> deleteDevice(String deviceId) async {
    deleted.add(deviceId);
    if (fail) throw Exception('network');
  }
}

void main() {
  const supabaseUrl = 'https://test.supabase.co';
  const anonKey = 'test-anon-key';

  group('AuthService', () {
    test('signIn stores access and refresh tokens on success', () async {
      final client = MockClient((request) async {
        expect(
          request.url.toString(),
          '$supabaseUrl/auth/v1/token?grant_type=password',
        );
        expect(request.headers['apikey'], anonKey);
        return http.Response(
          jsonEncode({'access_token': 'ACCESS', 'refresh_token': 'REFRESH'}),
          200,
        );
      });
      final storage = _FakeStorage();
      final auth = AuthService(
        storage: storage,
        httpClient: client,
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      );

      await auth.signIn('user@example.com', 'password');

      expect(auth.accessToken, 'ACCESS');
      expect(auth.refreshToken, 'REFRESH');
      expect(await storage.read('access_token'), 'ACCESS');
      expect(await storage.read('refresh_token'), 'REFRESH');
    });

    test('signIn throws AuthException on failure', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({'error': 'invalid_credentials'}),
          400,
        ),
      );
      final auth = AuthService(
        storage: _FakeStorage(),
        httpClient: client,
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      );

      expect(
        () => auth.signIn('user@example.com', 'bad'),
        throwsA(isA<AuthException>()),
      );
    });

    test('loadStoredSession returns true when tokens exist', () async {
      final storage = _FakeStorage()
        .._values['access_token'] = 'A'
        .._values['refresh_token'] = 'R';
      final auth = AuthService(
        storage: storage,
        httpClient: MockClient((_) async => http.Response('', 500)),
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      );

      final hasSession = await auth.loadStoredSession();

      expect(hasSession, isTrue);
      expect(auth.accessToken, 'A');
      expect(auth.refreshToken, 'R');
    });

    test('refreshSession exchanges refresh token for a new pair', () async {
      final client = MockClient((request) async {
        expect(
          request.url.toString(),
          '$supabaseUrl/auth/v1/token?grant_type=refresh_token',
        );
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['refresh_token'], 'OLD_REFRESH');
        return http.Response(
          jsonEncode({'access_token': 'NEW_A', 'refresh_token': 'NEW_R'}),
          200,
        );
      });
      final storage = _FakeStorage()
        .._values['refresh_token'] = 'OLD_REFRESH';
      final auth = AuthService(
        storage: storage,
        httpClient: client,
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      );

      await auth.refreshSession();

      expect(auth.accessToken, 'NEW_A');
      expect(auth.refreshToken, 'NEW_R');
      expect(await storage.read('access_token'), 'NEW_A');
    });

    test('signOut deletes the device registration and clears tokens', () async {
      final registrar = _FakeDeviceRegistrar();
      final storage = _FakeStorage()
        .._values['access_token'] = 'A'
        .._values['refresh_token'] = 'R';
      final auth = AuthService(
        storage: storage,
        httpClient: MockClient((_) async => http.Response('', 500)),
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      )..registeredDeviceId = 'device-123';

      await auth.signOut(deviceRegistrar: registrar);

      expect(registrar.deleted, ['device-123']);
      expect(auth.accessToken, isNull);
      expect(auth.refreshToken, isNull);
      expect(auth.registeredDeviceId, isNull);
      expect(storage._values, isEmpty);
    });

    test('signOut still clears tokens when device deletion fails', () async {
      final registrar = _FakeDeviceRegistrar()..fail = true;
      final storage = _FakeStorage()
        .._values['access_token'] = 'A';
      final auth = AuthService(
        storage: storage,
        httpClient: MockClient((_) async => http.Response('', 500)),
        supabaseUrl: supabaseUrl,
        supabaseAnonKey: anonKey,
      )..registeredDeviceId = 'device-456';

      await auth.signOut(deviceRegistrar: registrar);

      expect(registrar.deleted, ['device-456']);
      expect(auth.accessToken, isNull);
      expect(storage._values, isEmpty);
    });
  });
}
