import 'package:flutter/widgets.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/mobile_api_client.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/auth/auth_service.dart';
import '../../core/auth/biometric_gate.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/offline_queue/offline_queue_service.dart';

/// Provides the app's service layer to feature screens without modifying the
/// core implementations.
class ServiceProvider extends InheritedWidget {
  const ServiceProvider({
    super.key,
    required this.authService,
    required this.biometricGate,
    required this.mobileApiClient,
    required this.approvalsApiClient,
    required this.requestsApiClient,
    required this.i18n,
    this.offlineQueueService,
    required super.child,
  });

  final AuthService authService;
  final BiometricGate biometricGate;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final RequestsApiClient requestsApiClient;
  final I18nLoader i18n;
  final OfflineQueue? offlineQueueService;

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
      requestsApiClient != oldWidget.requestsApiClient ||
      i18n != oldWidget.i18n ||
      offlineQueueService != oldWidget.offlineQueueService;
}
