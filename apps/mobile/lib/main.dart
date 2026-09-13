import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:http/http.dart' as http;
import 'package:local_auth/local_auth.dart';

import 'core/api/approvals_api_client.dart';
import 'core/api/mobile_api_client.dart';
import 'core/api/requests_api_client.dart';
import 'core/auth/auth_service.dart';
import 'core/auth/biometric_gate.dart';
import 'core/camera/camera_capture.dart';
import 'core/i18n/i18n_loader.dart';
import 'core/offline_queue/offline_queue_replay.dart';
import 'core/offline_queue/offline_queue_service.dart';
import 'features/approvals/approval_decision_screen.dart';
import 'features/approvals/approval_queue_screen.dart';
import 'features/auth/biometric_offer_screen.dart';
import 'features/auth/sign_in_screen.dart';
import 'features/auth/splash_screen.dart';
import 'features/delivery/delivery_confirmation_screen.dart';
import 'features/delivery/quality_issue_screen.dart';
import 'features/home/home_screen.dart';
import 'features/low_stock/low_stock_report_screen.dart';
import 'features/notifications/notification_permission.dart';
import 'features/notifications/notification_tap_router.dart';
import 'features/notifications/push_notification_registration.dart';
import 'features/requests/request_detail_screen.dart';
import 'features/requests/request_form_screen.dart';
import 'features/requests/request_list_screen.dart';
import 'features/service_provider.dart';

/// Route table for the mobile app.
///
/// Exposed as a top-level value so static analysis tests can inspect it
/// without needing to instantiate the service layer.
final Map<String, WidgetBuilder> appRoutes = {
  '/': (context) => const SplashScreen(),
  '/signIn': (context) => const SignInScreen(),
  '/biometricOffer': (context) => const BiometricOfferScreen(),
  '/home': (context) => const HomeScreen(),
  '/approvals': (context) => const ApprovalQueueScreen(),
  '/approvals/detail': (context) => const ApprovalDecisionScreen(),
  '/delivery/confirm': (context) => const DeliveryConfirmationScreen(),
  '/delivery/qualityIssue': (context) => const QualityIssueScreen(),
  '/requests': (context) => const RequestListScreen(),
  '/requests/new': (context) => const RequestFormScreen(),
  '/requests/detail': (context) => const RequestDetailScreen(),
  '/lowStock': (context) => const LowStockReportScreen(),
};

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  const supabaseUrl = String.fromEnvironment('SUPABASE_URL', defaultValue: '');
  const supabaseAnonKey = String.fromEnvironment(
    'SUPABASE_ANON_KEY',
    defaultValue: '',
  );
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: '');

  final i18n = I18nLoader();
  await i18n.load(
    const String.fromEnvironment('DEFAULT_LOCALE', defaultValue: 'en'),
  );

  final storage = const FlutterSecureStorageAdapter(FlutterSecureStorage());
  await Hive.initFlutter();
  final offlineQueueBox = await Hive.openBox<String>('offline_queue');
  final httpClient = http.Client();

  final authService = AuthService(
    storage: storage,
    httpClient: httpClient,
    supabaseUrl: supabaseUrl,
    supabaseAnonKey: supabaseAnonKey,
  );

  final mobileApiClient = MobileApiClient(
    apiBaseUrl: apiBaseUrl,
    httpClient: httpClient,
  );
  final approvalsApiClient = ApprovalsApiClient(
    apiBaseUrl: apiBaseUrl,
    httpClient: httpClient,
  );
  final requestsApiClient = RequestsApiClient(
    apiBaseUrl: apiBaseUrl,
    httpClient: httpClient,
  );
  final offlineQueueService = OfflineQueueService(box: offlineQueueBox);

  final biometricGate = BiometricGate(
    biometricAuth: LocalAuthAdapter(LocalAuthentication()),
    authService: authService,
  );

  runApp(
    ProcurePilotApp(
      i18n: i18n,
      authService: authService,
      biometricGate: biometricGate,
      mobileApiClient: mobileApiClient,
      approvalsApiClient: approvalsApiClient,
      requestsApiClient: requestsApiClient,
      cameraCapture: const StandInCameraCapture(),
      offlineQueueService: offlineQueueService,
      notificationPermission: StandInNotificationPermission(),
    ),
  );
}

class ProcurePilotApp extends StatefulWidget {
  const ProcurePilotApp({
    super.key,
    required this.i18n,
    required this.authService,
    required this.biometricGate,
    required this.mobileApiClient,
    required this.approvalsApiClient,
    required this.requestsApiClient,
    this.cameraCapture = const StandInCameraCapture(),
    this.offlineQueueService,
    this.notificationPermission,
  });

  final I18nLoader i18n;
  final AuthService authService;
  final BiometricGate biometricGate;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final RequestsApiClient requestsApiClient;
  final CameraCapture cameraCapture;
  final OfflineQueue? offlineQueueService;
  final NotificationPermission? notificationPermission;

  @override
  State<ProcurePilotApp> createState() => _ProcurePilotAppState();
}

class _ProcurePilotAppState extends State<ProcurePilotApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  late final _notificationRouteObserver = _NotificationRouteObserver(
    onRouteChanged: _registerNotificationsIfSignedIn,
  );
  StreamSubscription<Map<String, String>>? _notificationTapSubscription;
  OfflineQueueReplay? _offlineQueueReplay;
  bool _notificationRegistrationStarted = false;

  @override
  void initState() {
    super.initState();
    _startOfflineReplay();
    _startNotifications();
  }

  @override
  void didUpdateWidget(ProcurePilotApp oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.notificationPermission != oldWidget.notificationPermission ||
        widget.mobileApiClient != oldWidget.mobileApiClient ||
        widget.requestsApiClient != oldWidget.requestsApiClient) {
      _notificationTapSubscription?.cancel();
      _notificationTapSubscription = null;
      _notificationRegistrationStarted = false;
      _startNotifications();
    }
    if (widget.offlineQueueService != oldWidget.offlineQueueService ||
        widget.mobileApiClient != oldWidget.mobileApiClient ||
        widget.requestsApiClient != oldWidget.requestsApiClient) {
      _offlineQueueReplay?.stop();
      _offlineQueueReplay = null;
      _startOfflineReplay();
    }
  }

  @override
  void dispose() {
    _notificationTapSubscription?.cancel();
    _offlineQueueReplay?.stop();
    super.dispose();
  }

  void _startOfflineReplay() {
    final queue = widget.offlineQueueService;
    if (queue == null) return;
    _offlineQueueReplay = OfflineQueueReplay(
      queue: queue,
      apiClient: widget.mobileApiClient,
      requestsApiClient: widget.requestsApiClient,
    )..start();
  }

  void _startNotifications() {
    final permission = widget.notificationPermission;
    if (permission == null) return;

    final router = NotificationTapRouter(
      requestsApiClient: widget.requestsApiClient,
      navigatorKey: _navigatorKey,
    );
    _notificationTapSubscription = permission.notificationTaps.listen((
      payload,
    ) {
      router.route(payload).catchError((Object error) {
        debugPrint('Failed to route notification tap: $error');
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _registerNotificationsIfSignedIn();
    });
  }

  void _registerNotificationsIfSignedIn() {
    if (_notificationRegistrationStarted) return;
    final permission = widget.notificationPermission;
    if (permission == null) return;

    final token = widget.authService.accessToken;
    if (token == null || token.isEmpty) return;

    _notificationRegistrationStarted = true;
    widget.mobileApiClient.accessToken = token;
    widget.approvalsApiClient.accessToken = token;
    widget.requestsApiClient.accessToken = token;

    PushNotificationRegistration(
      permission: permission,
      mobileApiClient: widget.mobileApiClient,
    ).registerIfGranted().catchError((Object error) {
      debugPrint('Failed to register notification device: $error');
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.i18n,
      builder: (context, _) {
        return ServiceProvider(
          authService: widget.authService,
          biometricGate: widget.biometricGate,
          mobileApiClient: widget.mobileApiClient,
          approvalsApiClient: widget.approvalsApiClient,
          requestsApiClient: widget.requestsApiClient,
          cameraCapture: widget.cameraCapture,
          offlineQueueService: widget.offlineQueueService,
          i18n: widget.i18n,
          child: MaterialApp(
            navigatorKey: _navigatorKey,
            title: widget.i18n.t('common.brandName'),
            locale: Locale(widget.i18n.locale),
            builder: (context, child) {
              return Directionality(
                textDirection: widget.i18n.textDirection,
                child: child ?? const SizedBox.shrink(),
              );
            },
            navigatorObservers: [_notificationRouteObserver],
            routes: appRoutes,
          ),
        );
      },
    );
  }
}

class _NotificationRouteObserver extends NavigatorObserver {
  _NotificationRouteObserver({required this.onRouteChanged});

  final VoidCallback onRouteChanged;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    onRouteChanged();
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    onRouteChanged();
  }
}
