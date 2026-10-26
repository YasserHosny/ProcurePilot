import 'package:flutter/widgets.dart';

import '../../core/api/approvals_api_client.dart';
import '../../core/api/mobile_api_client.dart';
import '../../core/api/requests_api_client.dart';
import '../../core/auth/auth_service.dart';
import '../../core/auth/biometric_gate.dart';
import '../../core/camera/camera_capture.dart';
import '../../core/i18n/i18n_loader.dart';
import '../../core/offline_queue/offline_queue_service.dart';
import '../../core/platform/link_opener.dart';
import '../../core/platform/version_provider.dart';

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
    required this.cameraCapture,
    required this.i18n,
    this.offlineQueueService,
    this.webOrigin = const String.fromEnvironment(
      'WEB_ORIGIN',
      defaultValue: 'https://procurepilot.iron-sys.com',
    ),
    this.linkOpener = const UrlLauncherLinkOpener(),
    this.versionProvider = const PackageInfoVersionProvider(),
    required super.child,
  });

  final AuthService authService;
  final BiometricGate biometricGate;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final RequestsApiClient requestsApiClient;
  final CameraCapture cameraCapture;
  final I18nLoader i18n;
  final OfflineQueue? offlineQueueService;
  final String webOrigin;
  final LinkOpener linkOpener;
  final AppVersionProvider versionProvider;

  static ServiceProvider of(BuildContext context) {
    final provider = context
        .dependOnInheritedWidgetOfExactType<ServiceProvider>();
    assert(provider != null, 'No ServiceProvider found in context');
    return provider!;
  }

  static ServiceProvider? maybeOf(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<ServiceProvider>();
  }

  @override
  bool updateShouldNotify(ServiceProvider oldWidget) =>
      authService != oldWidget.authService ||
      biometricGate != oldWidget.biometricGate ||
      mobileApiClient != oldWidget.mobileApiClient ||
      approvalsApiClient != oldWidget.approvalsApiClient ||
      requestsApiClient != oldWidget.requestsApiClient ||
      cameraCapture != oldWidget.cameraCapture ||
      i18n != oldWidget.i18n ||
      offlineQueueService != oldWidget.offlineQueueService ||
      webOrigin != oldWidget.webOrigin ||
      linkOpener != oldWidget.linkOpener ||
      versionProvider != oldWidget.versionProvider;
}
