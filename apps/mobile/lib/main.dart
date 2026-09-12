import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:local_auth/local_auth.dart';

import 'core/api/approvals_api_client.dart';
import 'core/api/mobile_api_client.dart';
import 'core/auth/auth_service.dart';
import 'core/auth/biometric_gate.dart';
import 'core/i18n/i18n_loader.dart';
import 'features/auth/biometric_offer_screen.dart';
import 'features/auth/sign_in_screen.dart';
import 'features/auth/splash_screen.dart';
import 'features/home/home_screen.dart';
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
    ),
  );
}

class ProcurePilotApp extends StatelessWidget {
  const ProcurePilotApp({
    super.key,
    required this.i18n,
    required this.authService,
    required this.biometricGate,
    required this.mobileApiClient,
    required this.approvalsApiClient,
  });

  final I18nLoader i18n;
  final AuthService authService;
  final BiometricGate biometricGate;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: i18n,
      builder: (context, _) {
        return ServiceProvider(
          authService: authService,
          biometricGate: biometricGate,
          mobileApiClient: mobileApiClient,
          approvalsApiClient: approvalsApiClient,
          i18n: i18n,
          child: MaterialApp(
            title: i18n.t('common.brandName'),
            locale: Locale(i18n.locale),
            builder: (context, child) {
              return Directionality(
                textDirection: i18n.textDirection,
                child: child ?? const SizedBox.shrink(),
              );
            },
            routes: appRoutes,
          ),
        );
      },
    );
  }
}
