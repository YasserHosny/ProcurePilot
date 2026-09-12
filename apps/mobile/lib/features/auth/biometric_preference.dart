import '../../core/auth/auth_service.dart';

/// Persists whether the member chose to enable biometric unlock for return
/// visits.
///
/// This is a thin wrapper around the same [SecureStorage] used by
/// [AuthService] so the preference is cleared automatically on sign-out.
class BiometricPreference {
  BiometricPreference(this._storage);

  final SecureStorage _storage;
  static const _key = 'biometric_enabled';

  Future<bool> isEnabled() async {
    final value = await _storage.read(_key);
    return value == 'true';
  }

  Future<void> setEnabled(bool enabled) async {
    await _storage.write(_key, enabled.toString());
  }

  Future<void> clear() async {
    await _storage.delete(_key);
  }
}
