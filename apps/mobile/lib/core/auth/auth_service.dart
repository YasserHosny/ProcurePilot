import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// Abstraction over secure token storage so tests can inject a fake.
abstract class SecureStorage {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
  Future<void> deleteAll();
}

/// Adapter around [FlutterSecureStorage].
class FlutterSecureStorageAdapter implements SecureStorage {
  const FlutterSecureStorageAdapter(this._storage);

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);

  @override
  Future<void> deleteAll() => _storage.deleteAll();
}

/// Interface for the sign-out device-deletion call so auth core does not
/// depend directly on the API client.
abstract class DeviceRegistrar {
  Future<void> deleteDevice(String deviceId);
}

/// Exception surfaced by [AuthService].
///
/// [statusCode] is the raw HTTP status from Supabase Auth's own `/auth/v1/token` endpoint (mobile
/// talks to it directly, unlike web which goes through apps/api's own proxy) — callers use it to
/// map to a translated `auth.signin.*Error` key rather than showing [message], which is Supabase's
/// own untranslated `error_description` (PR review finding: a failed sign-in was rendering raw
/// server copy verbatim, bypassing `packages/i18n` entirely for Arabic sessions).
@immutable
class AuthException implements Exception {
  const AuthException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => 'AuthException: $message';
}

/// Mobile auth core.
///
/// Sign-in/refresh hit the same Supabase Auth endpoints the web app uses
/// (`/auth/v1/token`). Tokens are persisted through [SecureStorage].
class AuthService {
  AuthService({
    required this.storage,
    required this.httpClient,
    required this.supabaseUrl,
    required this.supabaseAnonKey,
  });

  final SecureStorage storage;
  final http.Client httpClient;
  final String supabaseUrl;
  final String supabaseAnonKey;

  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';

  String? accessToken;
  String? refreshToken;

  /// The device id returned by [POST /devices] when the push-permission flow
  /// registers this install. Wired by T038; kept here so sign-out can delete it.
  String? registeredDeviceId;

  /// Calls Supabase Auth's password grant and stores the token pair.
  Future<void> signIn(String email, String password) async {
    final uri = Uri.parse('$supabaseUrl/auth/v1/token?grant_type=password');
    final response = await httpClient.post(
      uri,
      headers: {
        'apikey': supabaseAnonKey,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode != 200) {
      final decoded = _tryDecode(response.body);
      final message =
          decoded?['error_description'] as String? ??
          decoded?['error'] as String? ??
          'Sign in failed (${response.statusCode})';
      throw AuthException(message, statusCode: response.statusCode);
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    await _setTokens(
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
    );
  }

  /// Loads tokens from secure storage into memory.
  Future<bool> loadStoredSession() async {
    accessToken = await storage.read(_accessTokenKey);
    refreshToken = await storage.read(_refreshTokenKey);
    return accessToken != null && accessToken!.isNotEmpty;
  }

  /// Silently refreshes the session using the stored refresh token.
  Future<void> refreshSession() async {
    final token = refreshToken ?? await storage.read(_refreshTokenKey);
    if (token == null || token.isEmpty) {
      throw const AuthException('No refresh token available');
    }

    final uri = Uri.parse('$supabaseUrl/auth/v1/token?grant_type=refresh_token');
    final response = await httpClient.post(
      uri,
      headers: {
        'apikey': supabaseAnonKey,
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'refresh_token': token}),
    );

    if (response.statusCode != 200) {
      throw AuthException(
        'Refresh failed (${response.statusCode}): ${response.body}',
      );
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    await _setTokens(
      accessToken: data['access_token'] as String,
      refreshToken: data['refresh_token'] as String,
    );
  }

  /// Clears the local session and, if a device id has been recorded, calls
  /// [DELETE /devices/{id}] for this install's own registration.
  Future<void> signOut({DeviceRegistrar? deviceRegistrar}) async {
    final deviceId = registeredDeviceId;
    if (deviceId != null && deviceId.isNotEmpty && deviceRegistrar != null) {
      try {
        await deviceRegistrar.deleteDevice(deviceId);
      } catch (_) {
        // Best-effort deletion: local session is still cleared so the user is
        // signed out even if the network call fails.
      }
    }

    await storage.deleteAll();
    accessToken = null;
    refreshToken = null;
    registeredDeviceId = null;
  }

  Future<void> _setTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    await storage.write(_accessTokenKey, accessToken);
    await storage.write(_refreshTokenKey, refreshToken);
  }

  Map<String, dynamic>? _tryDecode(String body) {
    try {
      return jsonDecode(body) as Map<String, dynamic>;
    } on FormatException {
      return null;
    }
  }
}
