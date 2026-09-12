import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';

import 'auth_service.dart';

/// Outcome of a biometric unlock attempt.
enum BiometricResult {
  success,
  cancelled,
  failed,
  notAvailable,
}

/// Abstraction over the platform biometric API so tests can inject a fake.
abstract class BiometricAuth {
  Future<bool> isAvailable();
  Future<bool> authenticate({required String localizedReason});
}

/// Adapter around [LocalAuthentication].
class LocalAuthAdapter implements BiometricAuth {
  const LocalAuthAdapter(this._localAuth);

  final LocalAuthentication _localAuth;

  @override
  Future<bool> isAvailable() async {
    final available = await _localAuth.canCheckBiometrics;
    final enrolled = await _localAuth.getAvailableBiometrics();
    return available && enrolled.isNotEmpty;
  }

  @override
  Future<bool> authenticate({required String localizedReason}) async {
    try {
      return await _localAuth.authenticate(
        localizedReason: localizedReason,
        options: const AuthenticationOptions(
          biometricOnly: true,
          stickyAuth: true,
        ),
      );
    } on Exception {
      return false;
    }
  }
}

/// Client-only biometric gate.
///
/// The biometric check ONLY ever gates *using* an already-stored refresh token
/// to silently refresh the session. It is never treated as a standalone
/// credential. If the device has no biometric hardware or none enrolled, the
/// app falls back to ordinary credential sign-in.
@immutable
class BiometricGate {
  const BiometricGate({
    required this.biometricAuth,
    required this.authService,
  });

  final BiometricAuth biometricAuth;
  final AuthService authService;

  /// Attempts biometric authentication and, if successful, refreshes the
  /// session from the stored refresh token.
  ///
  /// Returns [BiometricResult.notAvailable] when the device cannot support
  /// biometrics, allowing the caller to route to password sign-in.
  ///
  /// [localizedReason] is shown by the OS-level biometric dialog itself, so it
  /// must come from the caller's own `I18nLoader` (`auth.biometric.unlockPrompt`)
  /// rather than being hardcoded here — this class has no i18n access of its own.
  Future<BiometricResult> unlock({required String localizedReason}) async {
    final available = await biometricAuth.isAvailable();
    if (!available) {
      return BiometricResult.notAvailable;
    }

    final authenticated = await biometricAuth.authenticate(
      localizedReason: localizedReason,
    );
    if (!authenticated) {
      return BiometricResult.cancelled;
    }

    try {
      await authService.refreshSession();
      return BiometricResult.success;
    } on AuthException {
      return BiometricResult.failed;
    }
  }
}
