import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/core/auth/biometric_gate.dart';
import 'package:procurepilot_mobile/core/i18n/i18n_loader.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_service.dart';
import 'package:procurepilot_mobile/features/auth/biometric_offer_screen.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_form_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_list_screen.dart';
import 'package:procurepilot_mobile/features/service_provider.dart';

/// A bundle that serves a minimal English catalogue for widget tests.
class TestAssetBundle extends AssetBundle {
  TestAssetBundle(this._data);

  final Map<String, String> _data;

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final value = _data[key];
    if (value == null) throw FlutterError('Missing asset: $key');
    return value;
  }

  @override
  Future<ByteData> load(String key) => throw UnimplementedError();
}

/// Returns a loaded [I18nLoader] backed by a minimal English catalogue.
Future<I18nLoader> loadTestI18n() async {
  final bundle = TestAssetBundle({
    '../../packages/i18n/en.json': jsonEncode({
      'common': {
        'brandName': 'ProcurePilot',
        'loading': 'Loading...',
        'comingSoon': 'Coming Soon',
        'roles': {
          'owner': 'Owner',
          'buyer': 'Buyer',
          'branch_manager': 'Branch Manager',
          'approver': 'Approver',
          'viewer': 'Viewer',
        },
      },
      'auth': {
        'signin': {
          'title': 'Sign in',
          'subtitle': 'Enter credentials',
          'emailLabel': 'Email',
          'emailPlaceholder': 'you@example.com',
          'emailRequired': 'Email required',
          'emailInvalid': 'Invalid email',
          'passwordLabel': 'Password',
          'passwordPlaceholder': 'Password',
          'passwordRequired': 'Password required',
          'submitButton': 'Sign In',
          'submittingButton': 'Signing in...',
          'genericError': 'Sign in failed',
          'invalidCredentialsError': 'Invalid email or password.',
          'rateLimitedError':
              'Too many sign-in attempts. Please wait and try again.',
          'showPassword': 'Show',
          'hidePassword': 'Hide',
        },
        'biometric': {
          'enableTitle': 'Enable biometric?',
          'enableMessage': 'Use biometric next time',
          'enableButton': 'Enable',
          'declineButton': 'Not now',
          'unlockTitle': 'Unlock',
          'unlockPrompt': 'Use biometric',
          'fallbackButton': 'Use password',
        },
      },
      'mobileHome': {
        'title': 'Home',
        'roleLabel': 'Your role',
        'requestItems': 'Request items',
        'pendingApprovalsCount': '{{count}} pending',
        'pendingCountError': 'Count error',
        'signOut': 'Sign out',
      },
      'requests': {
        'title': 'Purchase Requests',
        'subtitle': 'Create and track purchase requests',
        'status': {
          'draft': 'Draft',
          'submitted': 'Submitted',
          'pending': 'Pending',
          'approved': 'Approved',
          'rejected': 'Rejected',
          'withdrawn': 'Withdrawn',
        },
        'columns': {
          'status': 'Status',
          'requiredByDate': 'Required By',
          'estimatedTotal': 'Estimated Total',
        },
        'form': {
          'createTitle': 'New Purchase Request',
          'editTitle': 'Edit Purchase Request',
          'branchLabel': 'Branch',
          'branchRequired': 'Branch is required.',
          'costCentreLabel': 'Cost Centre (optional)',
          'requiredByDateLabel': 'Required By',
          'linesTitle': 'Line Items',
          'addLineButton': 'Add Line',
          'removeLineButton': 'Remove line',
          'productLabel': 'Product',
          'productRequired': 'Select a product.',
          'quantityLabel': 'Quantity',
          'quantityRequired': 'Quantity must be greater than zero',
          'noteLabel': 'Note (optional)',
          'cancelButton': 'Cancel',
          'saveDraftButton': 'Save Draft',
          'submitButton': 'Submit Request',
          'submittingButton': 'Submitting...',
          'atLeastOneLineRequired': 'At least one line item is required',
        },
        'empty': 'No purchase requests yet',
        'createSuccess': 'Purchase request saved as a draft',
        'submitSuccess': 'Purchase request submitted for approval',
        'genericError': 'Unable to save the purchase request',
        'incompleteEstimateBadge': 'Estimate incomplete',
        'approval': {
          'sectionTitle': 'Approval',
          'assignedTo': 'Assigned to',
          'comment': 'Decision comment',
          'decidedAt': 'Decided on',
          'pending': 'Pending approval',
        },
      },
      'mobileRequests': {
        'productSearchHint': 'Search products by name...',
        'queuedMessage':
            'Purchase request queued — will submit when back online.',
      },
      'lowStock': {
        'title': 'Low Stock Report',
        'actionLabel': 'Running low',
        'countRemainingLabel': 'Count remaining',
        'submittedMessage': 'Low stock report submitted.',
        'queuedMessage':
            'Low stock report queued — will send when back online.',
      },
    }),
    '../../packages/i18n/ar.json': jsonEncode({}),
  });
  final i18n = I18nLoader(bundle: bundle);
  await i18n.load('en');
  return i18n;
}

/// In-memory secure storage for tests.
class FakeStorage implements SecureStorage {
  final _values = <String, String>{};

  /// Exposed so tests can assert on stored values.
  Map<String, String> get values => _values;

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async => _values[key] = value;

  @override
  Future<void> delete(String key) async => _values.remove(key);

  @override
  Future<void> deleteAll() async => _values.clear();
}

/// Fake biometric implementation for tests.
class FakeBiometricAuth implements BiometricAuth {
  FakeBiometricAuth({this.available = true, this.authenticateResult = true});

  bool available;
  bool authenticateResult;
  String? lastReason;

  @override
  Future<bool> isAvailable() async => available;

  @override
  Future<bool> authenticate({required String localizedReason}) async {
    lastReason = localizedReason;
    return authenticateResult;
  }
}

/// Fake device registrar for tests.
class FakeDeviceRegistrar implements DeviceRegistrar {
  final deleted = <String>[];

  @override
  Future<void> deleteDevice(String deviceId) async {
    deleted.add(deviceId);
  }
}

/// Fake requests API client for widget tests.
class FakeRequestsApiClient extends RequestsApiClient {
  FakeRequestsApiClient()
    : super(apiBaseUrl: 'https://test.api', httpClient: http.Client());

  final createCalls = <PurchaseRequestCreate>[];
  final createIdempotencyKeys = <String?>[];
  final updateCalls = <List<dynamic>>[];
  final submitCalls = <String>[];
  final submitIdempotencyKeys = <String?>[];
  final getRequestCalls = <String>[];
  PurchaseRequest? createResult;
  PurchaseRequest? updateResult;
  PurchaseRequest? submitResult;
  Exception? createError;
  Exception? submitError;
  final getRequestResults = <String, PurchaseRequest>{};

  List<PurchaseRequest> listResults = [];
  List<Branch> branches = [];
  List<CostCentre> costCentres = [];
  List<CatalogueProduct> catalogueSearchResults = [];

  @override
  Future<PurchaseRequestList> listRequests({
    String? status,
    String? branchId,
    String? cursor,
    int limit = 50,
  }) async {
    final filtered = status == null || status.isEmpty
        ? listResults
        : listResults.where((r) => r.status == status).toList();
    return PurchaseRequestList(items: filtered);
  }

  @override
  Future<PurchaseRequest> createRequest(
    PurchaseRequestCreate body, {
    String? idempotencyKey,
  }) async {
    createCalls.add(body);
    createIdempotencyKeys.add(idempotencyKey);
    if (createError != null) throw createError!;
    if (createResult != null) return createResult!;
    return PurchaseRequest(
      id: '00000000-0000-0000-0000-000000000001',
      branchId: body.branchId,
      costCentreId: body.costCentreId,
      requestedByMembershipId: '00000000-0000-0000-0000-000000000000',
      requiredByDate: body.requiredByDate,
      status: 'draft',
      lines: [],
      hasIncompleteEstimate: false,
      createdAt: DateTime.now(),
    );
  }

  @override
  Future<PurchaseRequest> updateRequest(
    String requestId,
    PurchaseRequestUpdate body,
  ) async {
    updateCalls.add([requestId, body]);
    if (updateResult != null) return updateResult!;
    return PurchaseRequest(
      id: requestId,
      branchId: body.branchId ?? '',
      costCentreId: body.costCentreId,
      requestedByMembershipId: '00000000-0000-0000-0000-000000000000',
      requiredByDate: body.requiredByDate ?? '',
      status: 'draft',
      lines: [],
      hasIncompleteEstimate: false,
      createdAt: DateTime.now(),
    );
  }

  @override
  Future<PurchaseRequest> getRequest(String requestId) async {
    getRequestCalls.add(requestId);
    final result = getRequestResults[requestId];
    if (result != null) return result;
    return listResults.firstWhere((request) => request.id == requestId);
  }

  @override
  Future<PurchaseRequest> submitRequest(
    String requestId, {
    String? idempotencyKey,
  }) async {
    submitCalls.add(requestId);
    submitIdempotencyKeys.add(idempotencyKey);
    if (submitError != null) throw submitError!;
    if (submitResult != null) return submitResult!;
    return PurchaseRequest(
      id: requestId,
      branchId: '',
      requestedByMembershipId: '00000000-0000-0000-0000-000000000000',
      requiredByDate: '',
      status: 'submitted',
      lines: [],
      hasIncompleteEstimate: false,
      createdAt: DateTime.now(),
    );
  }

  @override
  Future<BranchList> listBranches({String? cursor, int limit = 100}) async {
    return BranchList(items: branches);
  }

  @override
  Future<CostCentreList> listCostCentres({
    String? cursor,
    int limit = 100,
  }) async {
    return CostCentreList(items: costCentres);
  }

  @override
  Future<CatalogueProductList> searchCatalogue({
    required String query,
    String? cursor,
    int limit = 20,
  }) async {
    return CatalogueProductList(items: catalogueSearchResults);
  }
}

/// Fake mobile API client for widget tests.
class FakeMobileApiClient extends MobileApiClient {
  FakeMobileApiClient()
    : super(apiBaseUrl: 'https://test.api', httpClient: http.Client());

  final createLowStockCalls = <Map<String, dynamic>>[];
  final deleteDeviceCalls = <String>[];
  final registerDeviceCalls = <Map<String, dynamic>>[];

  LowStockReport? createLowStockResult;
  Exception? createLowStockError;
  List<LowStockReport> listLowStockResults = [];

  @override
  Future<DeviceRegistration> registerDevice({
    required DevicePlatform platform,
    required String pushToken,
    String? idempotencyKey,
  }) async {
    registerDeviceCalls.add({
      'platform': platform,
      'pushToken': pushToken,
      'idempotencyKey': idempotencyKey,
    });
    return DeviceRegistration(
      id: '00000000-0000-0000-0000-000000000001',
      memberId: '00000000-0000-0000-0000-000000000000',
      platform: platform,
      pushToken: pushToken,
      lastSeenAt: DateTime.now(),
    );
  }

  @override
  Future<LowStockReportList> listLowStockReports({
    String? branchId,
    String? workspaceProductId,
    String? cursor,
    int limit = 50,
  }) async {
    return LowStockReportList(items: listLowStockResults, nextCursor: null);
  }

  @override
  Future<LowStockReport> createLowStockReport({
    required String branchId,
    required String workspaceProductId,
    String? countRemaining,
    String? idempotencyKey,
  }) async {
    createLowStockCalls.add({
      'branchId': branchId,
      'workspaceProductId': workspaceProductId,
      'countRemaining': countRemaining,
      'idempotencyKey': idempotencyKey,
    });
    if (createLowStockError != null) throw createLowStockError!;
    if (createLowStockResult != null) return createLowStockResult!;
    return LowStockReport(
      id: '00000000-0000-0000-0000-000000000001',
      branchId: branchId,
      memberId: '00000000-0000-0000-0000-000000000000',
      workspaceProductId: workspaceProductId,
      countRemaining: countRemaining,
      createdAt: DateTime.now(),
    );
  }
}

/// Builds a fake access token containing [member_role]. No signature is
/// included because the mobile UI only decodes claims; verification is the
/// API's job.
String makeAccessToken(String role) {
  String encode(String input) {
    return base64Url.encode(utf8.encode(input)).replaceAll('=', '');
  }

  final header = encode(jsonEncode({'alg': 'none'}));
  final payload = encode(
    jsonEncode({
      'sub': '00000000-0000-0000-0000-000000000000',
      'tenant_id': '00000000-0000-0000-0000-000000000000',
      'member_role': role,
    }),
  );
  return '$header.$payload.';
}

/// A fake [AuthService] that records calls and never hits the network.
class FakeAuthService extends AuthService {
  FakeAuthService({
    required super.storage,
    required super.httpClient,
    required super.supabaseUrl,
    required super.supabaseAnonKey,
  });

  final signInCalls = <List<String>>[];
  final signOutCalls = <DeviceRegistrar?>[];
  bool loadStoredSessionValue = false;
  String tokenRole = 'branch_manager';
  bool refreshShouldFail = false;
  AuthException? signInException;

  Future<void> _writeTokens() async {
    await storage.write('access_token', accessToken ?? '');
    await storage.write('refresh_token', refreshToken ?? '');
  }

  @override
  Future<void> signIn(String email, String password) async {
    signInCalls.add([email, password]);
    if (signInException != null) throw signInException!;
    accessToken = makeAccessToken(tokenRole);
    refreshToken = 'refresh-token';
    await _writeTokens();
  }

  @override
  Future<bool> loadStoredSession() async {
    if (loadStoredSessionValue) {
      accessToken = makeAccessToken(tokenRole);
      refreshToken = 'refresh-token';
      await _writeTokens();
    }
    return loadStoredSessionValue;
  }

  @override
  Future<void> refreshSession() async {
    if (refreshShouldFail) {
      throw const AuthException('Refresh failed');
    }
    accessToken = makeAccessToken(tokenRole);
    refreshToken = 'refresh-token';
    await _writeTokens();
  }

  @override
  Future<void> signOut({DeviceRegistrar? deviceRegistrar}) async {
    signOutCalls.add(deviceRegistrar);
    if (registeredDeviceId != null &&
        registeredDeviceId!.isNotEmpty &&
        deviceRegistrar != null) {
      await deviceRegistrar.deleteDevice(registeredDeviceId!);
    }
    await storage.deleteAll();
    accessToken = null;
    refreshToken = null;
    registeredDeviceId = null;
  }
}

/// A default HTTP client that never issues a real request.
http.Client defaultTestHttpClient() =>
    MockClient((_) async => http.Response('', 500));

/// Wraps [child] with a fully wired, test-only service layer and a route table
/// that mirrors the production app.
class TestServiceProvider extends StatelessWidget {
  const TestServiceProvider({
    super.key,
    required this.authService,
    required this.biometricAuth,
    required this.mobileApiClient,
    required this.approvalsApiClient,
    required this.requestsApiClient,
    required this.i18n,
    this.offlineQueueService,
    required this.child,
  });

  final AuthService authService;
  final BiometricAuth biometricAuth;
  final MobileApiClient mobileApiClient;
  final ApprovalsApiClient approvalsApiClient;
  final RequestsApiClient requestsApiClient;
  final I18nLoader i18n;
  final OfflineQueueService? offlineQueueService;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ServiceProvider(
      authService: authService,
      biometricGate: BiometricGate(
        biometricAuth: biometricAuth,
        authService: authService,
      ),
      mobileApiClient: mobileApiClient,
      approvalsApiClient: approvalsApiClient,
      requestsApiClient: requestsApiClient,
      i18n: i18n,
      offlineQueueService: offlineQueueService,
      child: MaterialApp(
        locale: const Locale('en'),
        builder: (context, child) => Directionality(
          textDirection: TextDirection.ltr,
          child: child ?? const SizedBox.shrink(),
        ),
        routes: {
          '/signIn': (_) => const SignInScreen(),
          '/biometricOffer': (_) => const BiometricOfferScreen(),
          '/home': (_) => const HomeScreen(),
          '/requests': (_) => const RequestListScreen(),
          '/requests/new': (_) => const RequestFormScreen(),
          '/requests/detail': (_) => const RequestDetailScreen(),
          '/lowStock': (_) => const LowStockReportScreen(),
        },
        home: child,
      ),
    );
  }
}

/// Pumps a feature screen with a fully wired, test-only service layer.
Future<TestServiceProvider> pumpWithServices(
  WidgetTester tester, {
  required Widget child,
  AuthService? authService,
  BiometricAuth? biometricAuth,
  MobileApiClient? mobileApiClient,
  ApprovalsApiClient? approvalsApiClient,
  RequestsApiClient? requestsApiClient,
  OfflineQueueService? offlineQueueService,
  I18nLoader? i18n,
}) async {
  final i18nValue = i18n ?? await loadTestI18n();
  final authServiceValue =
      authService ??
      FakeAuthService(
        storage: FakeStorage(),
        httpClient: defaultTestHttpClient(),
        supabaseUrl: 'https://test.supabase.co',
        supabaseAnonKey: 'test-anon-key',
      );
  final widget = TestServiceProvider(
    authService: authServiceValue,
    biometricAuth: biometricAuth ?? FakeBiometricAuth(),
    mobileApiClient: mobileApiClient ?? FakeMobileApiClient(),
    approvalsApiClient:
        approvalsApiClient ??
        ApprovalsApiClient(apiBaseUrl: 'https://test.api'),
    requestsApiClient:
        requestsApiClient ?? RequestsApiClient(apiBaseUrl: 'https://test.api'),
    i18n: i18nValue,
    offlineQueueService: offlineQueueService,
    child: child,
  );
  await tester.pumpWidget(widget);
  return widget;
}
