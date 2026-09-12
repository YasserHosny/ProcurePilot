import 'package:flutter/material.dart';

import '../../core/auth/biometric_gate.dart';
import '../service_provider.dart';
import 'auth_session.dart';
import 'biometric_preference.dart';

/// App launch gate.
///
/// On a fresh install, routes to the credential sign-in screen. On a return
/// visit with a stored session and biometric unlock enabled, it uses the
/// existing [BiometricGate] to unlock and refresh silently. If biometric is
/// unavailable, not enrolled, cancelled, or fails, it falls back to plain
/// credential sign-in — biometric is never a hard requirement.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _decideRoute());
  }

  Future<void> _decideRoute() async {
    final services = ServiceProvider.of(context);
    final hasSession = await services.authService.loadStoredSession();

    if (!hasSession) {
      _goSignIn();
      return;
    }

    final biometricEnabled = await BiometricPreference(
      services.authService.storage,
    ).isEnabled();
    if (!biometricEnabled) {
      _goSignIn();
      return;
    }

    final result = await services.biometricGate.unlock();
    if (!mounted) return;

    switch (result) {
      case BiometricResult.success:
        _syncApiTokens();
        _goHome();
      case BiometricResult.notAvailable:
      case BiometricResult.cancelled:
      case BiometricResult.failed:
        _goSignIn();
    }
  }

  void _syncApiTokens() {
    final services = ServiceProvider.of(context);
    final token = services.authService.accessToken;
    services.mobileApiClient.accessToken = token;
    services.approvalsApiClient.accessToken = token;
  }

  void _goSignIn() {
    Navigator.pushReplacementNamed(context, '/signIn');
  }

  void _goHome() {
    final session = parseMemberSession(
      ServiceProvider.of(context).authService.accessToken ?? '',
    );
    Navigator.pushReplacementNamed(context, '/home', arguments: session);
  }

  @override
  Widget build(BuildContext context) {
    final i18n = ServiceProvider.of(context).i18n;
    return Scaffold(body: Center(child: Text(i18n.t('common.loading'))));
  }
}
