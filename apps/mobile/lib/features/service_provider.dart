import 'package:flutter/widgets.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/mobile_api_client.dart';
import '../../core/auth/auth_service.dart';
import '../../core/auth/biometric_gate.dart';
import '../../core/i18n/i18n_loader.dart';

/// Provides the app's service layer to feature screens without modifying the
/// core implementations.
class ServiceProvider extends InheritedWidget {
  const ServiceProvider({
    super.key,
    required this.authService,
    required this.biometricGate,
    required this.mobileApiClient,
    required this.approvalsApiClient,
    required this.i18n,
    required super.child,
  });

  final AuthService authService;
  final BiometricGate biometricGate;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final I18nLoader i18n;

  static ServiceProvider of(BuildContext context) {
    final provider = context
        .dependOnInheritedWidgetOfExactType<ServiceProvider>();
    assert(provider != null, 'No ServiceProvider found in context');
    return provider!;
  }

  @override
  bool updateShouldNotify(ServiceProvider oldWidget) =>
      authService != oldWidget.authService ||
      biometricGate != oldWidget.biometricGate ||
      mobileApiClient != oldWidget.mobileApiClient ||
      approvalsApiClient != oldWidget.approvalsApiClient ||
      i18n != oldWidget.i18n;
}
