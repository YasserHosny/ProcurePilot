@Tags(['docs'])
library;

import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';
import 'package:procurepilot_mobile/core/camera/camera_capture.dart';
import 'package:procurepilot_mobile/core/i18n/i18n_loader.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_service.dart';
import 'package:procurepilot_mobile/features/approvals/approval_decision_screen.dart';
import 'package:procurepilot_mobile/features/approvals/approval_queue_screen.dart';
import 'package:procurepilot_mobile/features/auth/biometric_offer_screen.dart';
import 'package:procurepilot_mobile/features/auth/sign_in_screen.dart';
import 'package:procurepilot_mobile/features/auth/splash_screen.dart';
import 'package:procurepilot_mobile/features/delivery/delivery_confirmation_screen.dart';
import 'package:procurepilot_mobile/features/delivery/quality_issue_screen.dart';
import 'package:procurepilot_mobile/features/home/home_screen.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_detail_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_form_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_list_screen.dart';

import '../test_helpers.dart';

final Map<String, ByteData> _cachedBytes = {};
final Map<String, String> _cachedStrings = {};

Future<void> _loadAppFontsAndAssets() async {
  Future<ByteData> loadBytes(String path) async {
    final bytes = await File(path).readAsBytes();
    return ByteData.sublistView(Uint8List.fromList(bytes));
  }

  final readex = FontLoader('Readex Pro');
  readex.addFont(loadBytes('assets/fonts/ReadexPro-Regular.ttf'));
  readex.addFont(loadBytes('assets/fonts/ReadexPro-Medium.ttf'));
  readex.addFont(loadBytes('assets/fonts/ReadexPro-SemiBold.ttf'));
  await readex.load();

  final noto = FontLoader('Noto Kufi Arabic');
  noto.addFont(loadBytes('assets/fonts/NotoKufiArabic-Regular.ttf'));
  noto.addFont(loadBytes('assets/fonts/NotoKufiArabic-Medium.ttf'));
  noto.addFont(loadBytes('assets/fonts/NotoKufiArabic-SemiBold.ttf'));
  noto.addFont(loadBytes('assets/fonts/NotoKufiArabic-Bold.ttf'));
  await noto.load();

  final flutterRoot =
      Platform.environment['FLUTTER_ROOT'] ?? '/home/yasserhosny/flutter';
  final iconsPath =
      '$flutterRoot/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf';
  final icons = FontLoader('MaterialIcons');
  icons.addFont(loadBytes(iconsPath));
  await icons.load();

  for (final name in [
    'assets/brand/procurepilot-arabic-horizontal-1436px.png',
    'assets/brand/procurepilot-horizontal-1436px.png',
    'assets/brand/procurepilot-mark-192px.png',
  ]) {
    _cachedBytes[name] = await loadBytes(name);
  }

  for (final name in ['assets/i18n/en.json', 'assets/i18n/ar.json']) {
    _cachedStrings[name] = await File(name).readAsString();
  }
}

class _DocMemoryAssetBundle extends AssetBundle {
  @override
  Future<ByteData> load(String key) async {
    final cached = _cachedBytes[key];
    if (cached != null) return cached;
    return rootBundle.load(key);
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final cached = _cachedStrings[key];
    if (cached != null) return cached;
    return rootBundle.loadString(key, cache: cache);
  }
}

final _DocMemoryAssetBundle _bundle = _DocMemoryAssetBundle();

// Cairo restaurant group test fixtures (Nile Kitchens)
final List<Branch> _branches = [
  Branch(
    id: 'branch-maadi',
    name: 'Maadi Branch',
    isActive: true,
    createdAt: DateTime(2026, 1, 1),
  ),
  Branch(
    id: 'branch-zamalek',
    name: 'Zamalek Branch',
    isActive: true,
    createdAt: DateTime(2026, 1, 1),
  ),
];

final List<CostCentre> _costCentres = [
  CostCentre(
    id: 'cc-kitchen',
    name: 'Kitchen Operations',
    code: 'KITCHEN-01',
    isArchived: false,
    createdAt: DateTime(2026, 1, 1),
  ),
  CostCentre(
    id: 'cc-foh',
    name: 'Front of House',
    code: 'FOH-01',
    isArchived: false,
    createdAt: DateTime(2026, 1, 1),
  ),
];

final _prodOil = CatalogueProduct(
  id: 'prod-oil',
  tenantName: 'Extra Virgin Olive Oil 5L',
  canonicalName: 'Olive Oil Extra Virgin',
  baseUnit: 'litre',
  status: 'active',
  createdAt: DateTime(2026, 1, 1),
);

final _prodRice = CatalogueProduct(
  id: 'prod-rice',
  tenantName: 'Basmati Rice 25kg',
  canonicalName: 'Basmati Rice',
  baseUnit: 'kilogram',
  status: 'active',
  createdAt: DateTime(2026, 1, 1),
);

final _prodMilk = CatalogueProduct(
  id: 'prod-milk',
  tenantName: 'Fresh Whole Milk 1L',
  canonicalName: 'Whole Milk 1L',
  baseUnit: 'litre',
  status: 'active',
  createdAt: DateTime(2026, 1, 1),
);

final _prodCoffee = CatalogueProduct(
  id: 'prod-coffee',
  tenantName: 'Espresso Coffee Beans 1kg',
  canonicalName: 'Espresso Beans',
  baseUnit: 'kilogram',
  status: 'active',
  createdAt: DateTime(2026, 1, 1),
);

final _requestOrdered = PurchaseRequest(
  id: 'pr-001',
  branchId: 'branch-maadi',
  costCentreId: 'cc-kitchen',
  requestedByMembershipId: 'mem-tarek',
  requesterName: 'Tarek Mansour',
  requesterEmail: 'tarek@nilekitchens.com',
  requiredByDate: '2026-10-28',
  status: 'ordered',
  lines: [
    const PurchaseRequestLine(
      id: 'prl-001',
      workspaceProductId: 'prod-oil',
      productName: 'Extra Virgin Olive Oil 5L',
      quantity: '4',
      baseUnit: 'litre',
      packBaseQuantity: '5',
      estimatedUnitPrice: Money(amount: '450.00', currency: 'EGP'),
      quantityReceived: '4',
    ),
    const PurchaseRequestLine(
      id: 'prl-002',
      workspaceProductId: 'prod-rice',
      productName: 'Basmati Rice 25kg',
      quantity: '2',
      baseUnit: 'kilogram',
      packBaseQuantity: '25',
      estimatedUnitPrice: Money(amount: '825.00', currency: 'EGP'),
      quantityReceived: '2',
    ),
  ],
  estimatedTotal: const Money(amount: '3450.00', currency: 'EGP'),
  hasIncompleteEstimate: false,
  budgetStatus: const BudgetStatus(
    remainingAmount: Money(amount: '18500.00', currency: 'EGP'),
    exceeds: false,
  ),
  approvalStep: ApprovalStep(
    id: 'step-001',
    assignedMembershipId: 'mem-sarah',
    assignedEmail: 'sarah.manager@sanad-demo.example',
    source: 'branch_manager',
    status: 'approved',
    comment: 'Approved for Maadi kitchen weekly stock.',
    decidedAt: DateTime.parse('2026-10-24T14:30:00Z'),
    decidedByMembershipId: 'mem-sarah',
  ),
  createdAt: DateTime.parse('2026-10-24T10:00:00Z'),
);

final _requestSubmitted = PurchaseRequest(
  id: 'pr-002',
  branchId: 'branch-zamalek',
  costCentreId: 'cc-kitchen',
  requestedByMembershipId: 'mem-tarek',
  requesterName: 'Tarek Mansour',
  requesterEmail: 'tarek@nilekitchens.com',
  requiredByDate: '2026-10-29',
  status: 'submitted',
  lines: [
    const PurchaseRequestLine(
      id: 'prl-003',
      workspaceProductId: 'prod-coffee',
      productName: 'Espresso Coffee Beans 1kg',
      quantity: '8',
      baseUnit: 'kilogram',
      packBaseQuantity: '1',
      estimatedUnitPrice: Money(amount: '380.00', currency: 'EGP'),
    ),
    const PurchaseRequestLine(
      id: 'prl-004',
      workspaceProductId: 'prod-milk',
      productName: 'Fresh Whole Milk 1L',
      quantity: '40',
      baseUnit: 'litre',
      packBaseQuantity: '1',
      estimatedUnitPrice: Money(amount: '42.50', currency: 'EGP'),
    ),
  ],
  estimatedTotal: const Money(amount: '4740.00', currency: 'EGP'),
  hasIncompleteEstimate: false,
  budgetStatus: const BudgetStatus(
    remainingAmount: Money(amount: '12260.00', currency: 'EGP'),
    exceeds: false,
  ),
  approvalStep: const ApprovalStep(
    id: 'step-002',
    assignedMembershipId: 'mem-sarah',
    source: 'branch_manager',
    status: 'pending',
  ),
  createdAt: DateTime.parse('2026-10-24T11:15:00Z'),
);

final _requestDraft = PurchaseRequest(
  id: 'pr-003',
  branchId: 'branch-maadi',
  costCentreId: 'cc-foh',
  requestedByMembershipId: 'mem-karim',
  requesterName: 'Karim Fahmy',
  requesterEmail: 'karim@nilekitchens.com',
  requiredByDate: '2026-10-31',
  status: 'draft',
  lines: [
    const PurchaseRequestLine(
      id: 'prl-005',
      workspaceProductId: 'prod-milk',
      productName: 'Fresh Whole Milk 1L',
      quantity: '20',
      baseUnit: 'litre',
      packBaseQuantity: '1',
      estimatedUnitPrice: Money(amount: '42.50', currency: 'EGP'),
    ),
  ],
  estimatedTotal: const Money(amount: '850.00', currency: 'EGP'),
  hasIncompleteEstimate: false,
  budgetStatus: const BudgetStatus(
    remainingAmount: Money(amount: '15000.00', currency: 'EGP'),
    exceeds: false,
  ),
  createdAt: DateTime.parse('2026-10-24T12:00:00Z'),
);

final _requestDelivered = PurchaseRequest(
  id: 'pr-004',
  branchId: 'branch-maadi',
  costCentreId: 'cc-kitchen',
  requestedByMembershipId: 'mem-tarek',
  requesterName: 'Tarek Mansour',
  requesterEmail: 'tarek@nilekitchens.com',
  requiredByDate: '2026-10-22',
  status: 'delivered',
  deliveredAt: DateTime.parse('2026-10-23T15:00:00Z'),
  deliveryConfirmedByMembershipId: 'mem-tarek',
  lines: [
    const PurchaseRequestLine(
      id: 'prl-006',
      workspaceProductId: 'prod-oil',
      productName: 'Extra Virgin Olive Oil 5L',
      quantity: '6',
      quantityReceived: '6',
      baseUnit: 'litre',
      packBaseQuantity: '5',
      estimatedUnitPrice: Money(amount: '450.00', currency: 'EGP'),
    ),
  ],
  estimatedTotal: const Money(amount: '2700.00', currency: 'EGP'),
  hasIncompleteEstimate: false,
  budgetStatus: const BudgetStatus(
    remainingAmount: Money(amount: '15800.00', currency: 'EGP'),
    exceeds: false,
  ),
  createdAt: DateTime.parse('2026-10-22T09:00:00Z'),
);

class _HangingAuthService extends FakeAuthService {
  _HangingAuthService()
      : super(
          storage: FakeStorage(),
          httpClient: defaultTestHttpClient(),
          supabaseUrl: 'https://test.supabase.co',
          supabaseAnonKey: 'test-anon-key',
        );

  final Completer<bool> _completer = Completer<bool>();

  @override
  Future<bool> loadStoredSession() => _completer.future;
}

Future<void> _renderAndCapture({
  required WidgetTester tester,
  required String fileName,
  required Widget child,
  String locale = 'en',
  AuthService? authService,
  ApprovalsApiClient? approvalsApiClient,
  RequestsApiClient? requestsApiClient,
  MobileApiClient? mobileApiClient,
  CameraCapture? cameraCapture,
  OfflineQueue? offlineQueue,
  Future<void> Function(WidgetTester tester)? beforeCapture,
  bool settle = true,
}) async {
  final boundaryKey = GlobalKey();
  final i18n = I18nLoader(bundle: _bundle);
  await i18n.load(locale);

  await pumpWithServices(
    tester,
    child: DefaultAssetBundle(
      bundle: _bundle,
      child: RepaintBoundary(
        key: boundaryKey,
        child: child,
      ),
    ),
    i18n: i18n,
    authService: authService,
    approvalsApiClient: approvalsApiClient,
    requestsApiClient: requestsApiClient,
    mobileApiClient: mobileApiClient,
    cameraCapture: cameraCapture,
    offlineQueueService: offlineQueue,
    locale: locale,
  );

  // Precache images
  await tester.runAsync(() async {
    final ctx = boundaryKey.currentContext!;
    await precacheImage(
      const AssetImage('assets/brand/procurepilot-horizontal-1436px.png'),
      ctx,
    );
    await precacheImage(
      const AssetImage('assets/brand/procurepilot-arabic-horizontal-1436px.png'),
      ctx,
    );
    await precacheImage(
      const AssetImage('assets/brand/procurepilot-mark-192px.png'),
      ctx,
    );
  });

  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  if (beforeCapture != null) {
    await beforeCapture(tester);
    if (settle) {
      await tester.pumpAndSettle();
    } else {
      await tester.pump();
    }
  }

  await tester.runAsync(() async {
    final boundary =
        boundaryKey.currentContext!.findRenderObject() as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 2.0);
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    final bytes = byteData!.buffer.asUint8List();

    final file = File('../../docs/user/screenshots/mobile/$fileName');
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(bytes);
  });
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting();
    await _loadAppFontsAndAssets();
  });

  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  testWidgets('01-sign-in', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '01-sign-in.png',
      child: const SignInScreen(),
    );
  });

  testWidgets('01-sign-in-ar', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '01-sign-in-ar.png',
      locale: 'ar',
      child: const SignInScreen(),
    );
  });

  testWidgets('02-biometric-enable', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '02-biometric-enable.png',
      child: const BiometricOfferScreen(),
    );
  });

  testWidgets('03-biometric-unlock', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '03-biometric-unlock.png',
      authService: _HangingAuthService(),
      settle: false,
      child: const SplashScreen(),
    );
  });

  testWidgets('04-home-branch-manager', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final auth = FakeAuthService(
      storage: FakeStorage(),
      httpClient: defaultTestHttpClient(),
      supabaseUrl: 'https://test.supabase.co',
      supabaseAnonKey: 'test-anon-key',
    )
      ..accessToken = makeAccessToken('branch_manager')
      ..tokenRole = 'branch_manager';

    await _renderAndCapture(
      tester: tester,
      fileName: '04-home-branch-manager.png',
      authService: auth,
      child: const HomeScreen(),
    );
  });

  testWidgets('04b-home-approver', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final auth = FakeAuthService(
      storage: FakeStorage(),
      httpClient: defaultTestHttpClient(),
      supabaseUrl: 'https://test.supabase.co',
      supabaseAnonKey: 'test-anon-key',
    )
      ..accessToken = makeAccessToken('approver')
      ..tokenRole = 'approver';

    final approvals = FakeApprovalsApiClient()
      ..pendingResults = [
        _requestSubmitted,
        _requestDraft,
      ];

    await _renderAndCapture(
      tester: tester,
      fileName: '04b-home-approver.png',
      authService: auth,
      approvalsApiClient: approvals,
      child: const HomeScreen(),
    );
  });

  testWidgets('04-home-branch-manager-ar', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final auth = FakeAuthService(
      storage: FakeStorage(),
      httpClient: defaultTestHttpClient(),
      supabaseUrl: 'https://test.supabase.co',
      supabaseAnonKey: 'test-anon-key',
    )
      ..accessToken = makeAccessToken('branch_manager')
      ..tokenRole = 'branch_manager';

    await _renderAndCapture(
      tester: tester,
      fileName: '04-home-branch-manager-ar.png',
      locale: 'ar',
      authService: auth,
      child: const HomeScreen(),
    );
  });

  testWidgets('05-new-request', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final requests = FakeRequestsApiClient()
      ..branches = _branches
      ..costCentres = _costCentres
      ..catalogueSearchResults = [_prodOil, _prodRice, _prodMilk, _prodCoffee];

    await _renderAndCapture(
      tester: tester,
      fileName: '05-new-request.png',
      requestsApiClient: requests,
      child: const RequestFormScreen(),
    );
  });

  testWidgets('06-my-requests-list', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final requests = FakeRequestsApiClient()
      ..listResults = [
        _requestOrdered,
        _requestSubmitted,
        _requestDraft,
      ];

    await _renderAndCapture(
      tester: tester,
      fileName: '06-my-requests-list.png',
      requestsApiClient: requests,
      child: const RequestListScreen(),
    );
  });

  testWidgets('06b-my-requests-empty', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final requests = FakeRequestsApiClient()..listResults = [];

    await _renderAndCapture(
      tester: tester,
      fileName: '06b-my-requests-empty.png',
      requestsApiClient: requests,
      child: const RequestListScreen(),
    );
  });

  testWidgets('07-request-detail', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '07-request-detail.png',
      child: Navigator(
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: RouteSettings(
            name: '/requests/detail',
            arguments: _requestOrdered,
          ),
          builder: (_) => const RequestDetailScreen(),
        ),
      ),
    );
  });

  testWidgets('08-low-stock-report', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final requests = FakeRequestsApiClient()
      ..branches = _branches
      ..catalogueSearchResults = [_prodMilk];

    await _renderAndCapture(
      tester: tester,
      fileName: '08-low-stock-report.png',
      requestsApiClient: requests,
      child: LowStockReportScreen(
        initialProduct: _prodMilk,
        initialBranchId: 'branch-maadi',
      ),
    );
  });

  testWidgets('08b-low-stock-report-success', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final requests = FakeRequestsApiClient()
      ..branches = _branches
      ..catalogueSearchResults = [_prodMilk];

    final mobile = FakeMobileApiClient()
      ..createLowStockResult = LowStockReport(
        id: 'ls-001',
        branchId: 'branch-maadi',
        memberId: 'mem-tarek',
        workspaceProductId: 'prod-milk',
        countRemaining: '12',
        createdAt: DateTime.now(),
      );

    await _renderAndCapture(
      tester: tester,
      fileName: '08b-low-stock-report-success.png',
      requestsApiClient: requests,
      mobileApiClient: mobile,
      child: LowStockReportScreen(
        initialProduct: _prodMilk,
        initialBranchId: 'branch-maadi',
      ),
      beforeCapture: (tester) async {
        await tester.enterText(
          find.byKey(const Key('lowStockCountRemainingField')),
          '12',
        );
        await tester.tap(find.byKey(const Key('lowStockSubmitButton')));
      },
    );
  });

  testWidgets('10-approval-queue', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final approvals = FakeApprovalsApiClient()
      ..pendingResults = [
        _requestSubmitted,
        _requestDraft,
      ];

    await _renderAndCapture(
      tester: tester,
      fileName: '10-approval-queue.png',
      approvalsApiClient: approvals,
      child: const ApprovalQueueScreen(),
    );
  });

  testWidgets('10b-approval-decision', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '10b-approval-decision.png',
      child: Navigator(
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: RouteSettings(
            name: '/approvals/detail',
            arguments: _requestSubmitted,
          ),
          builder: (_) => const ApprovalDecisionScreen(),
        ),
      ),
    );
  });

  testWidgets('11-delivery-confirmation', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '11-delivery-confirmation.png',
      child: Navigator(
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: RouteSettings(
            name: '/delivery/confirm',
            arguments: _requestOrdered,
          ),
          builder: (_) => const DeliveryConfirmationScreen(),
        ),
      ),
    );
  });

  testWidgets('11b-quality-issue', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    await _renderAndCapture(
      tester: tester,
      fileName: '11b-quality-issue.png',
      cameraCapture: FakeCameraCapture(available: true),
      child: Navigator(
        onGenerateRoute: (settings) => MaterialPageRoute(
          settings: RouteSettings(
            name: '/delivery/qualityIssue',
            arguments: _requestDelivered,
          ),
          builder: (_) => const QualityIssueScreen(),
        ),
      ),
    );
  });
}
