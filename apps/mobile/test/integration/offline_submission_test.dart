import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_replay.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_service.dart';
import 'package:procurepilot_mobile/features/low_stock/low_stock_report_screen.dart';
import 'package:procurepilot_mobile/features/requests/request_form_screen.dart';

import '../test_helpers.dart';

/// Simulates the device having no connectivity: a plain (non-[ApiException])
/// exception, matching what the real `http` client throws on a dropped
/// connection.
class _OfflineError implements Exception {}

/// Pure in-memory [OfflineQueue] double for widget-level tests.
///
/// [OfflineQueueService]'s real implementation does file I/O via Hive, which
/// is already covered directly (no widget involved) by the `test()`-style
/// cases in `test/core/offline_queue/offline_queue_replay_test.dart`. Real
/// file I/O triggered from inside a widget's tap handler does not resolve
/// reliably under `TestWidgetsFlutterBinding`'s fake-async test zone, so this
/// double keeps these end-to-end screen tests fast and deterministic while
/// still exercising the real screen code and the real [OfflineQueueReplay].
class _FakeOfflineQueue implements OfflineQueue {
  final _items = <String, QueueItem>{};

  @override
  Future<QueueItem> createAndEnqueue({
    required String endpoint,
    required Map<String, dynamic> payload,
    String? idempotencyKey,
  }) async {
    final item = QueueItem(
      idempotencyKey: idempotencyKey ?? 'fake-${_items.length}',
      endpoint: endpoint,
      payload: payload,
      status: QueueItemStatus.queued,
      createdAt: DateTime.now().toUtc(),
      retries: 0,
    );
    _items[item.idempotencyKey] = item;
    return item;
  }

  @override
  List<QueueItem> get pending => _items.values
      .where(
        (item) =>
            item.status == QueueItemStatus.queued ||
            item.status == QueueItemStatus.failed,
      )
      .toList();

  @override
  Future<void> markConfirmed(String idempotencyKey) async {
    final item = _items[idempotencyKey];
    if (item == null) return;
    _items[idempotencyKey] = item.copyWith(status: QueueItemStatus.confirmed);
  }

  @override
  Future<void> markFailed(String idempotencyKey) async {
    final item = _items[idempotencyKey];
    if (item == null) return;
    _items[idempotencyKey] = item.copyWith(
      status: QueueItemStatus.failed,
      retries: item.retries + 1,
    );
  }
}

/// End-to-end proof of FR-011/FR-012 through the real screens, not just the
/// underlying [OfflineQueueService]/[OfflineQueueReplay] primitives (those
/// already have unit coverage in `test/core/offline_queue/`): building and
/// submitting a request or low-stock report while offline shows the honest
/// "queued" state rather than a false "confirmed" one, and once connectivity
/// returns the queued item sends exactly once.
void main() {
  group('Offline submission — request form', () {
    late _FakeOfflineQueue queue;
    late FakeRequestsApiClient requestsClient;

    setUp(() {
      queue = _FakeOfflineQueue();
      requestsClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'branch-1',
            name: 'Main Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ];
    });

    testWidgets(
      'a brand-new request that fails to create offline is shown queued, '
      'then replays exactly once when connectivity returns',
      (tester) async {
        requestsClient.createError = _OfflineError();

        await pumpWithServices(
          tester,
          child: RequestFormScreen(offlineQueueService: queue),
          requestsApiClient: requestsClient,
        );
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(const Key('requestFormBranchField')));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Main Branch').last);
        await tester.pumpAndSettle();

        final requiredByField = find.byKey(
          const Key('requestFormRequiredByField'),
        );
        await tester.ensureVisible(requiredByField);
        await tester.enterText(requiredByField, '2026-10-01');
        await tester.pumpAndSettle();

        final productField = find.byKey(
          const Key('requestLine_0_productSearch'),
        );
        await tester.ensureVisible(productField);
        await tester.enterText(productField, 'product-1');
        await tester.pumpAndSettle();

        final quantityField = find.byKey(const Key('requestLine_0_quantity'));
        await tester.ensureVisible(quantityField);
        await tester.enterText(quantityField, '5');
        await tester.pumpAndSettle();

        final submitButton = find.byKey(const Key('requestFormSubmitButton'));
        await tester.ensureVisible(submitButton);
        await tester.tap(submitButton);
        await tester.pumpAndSettle();

        // Honestly shown as queued, never as confirmed (FR-012).
        expect(
          find.byKey(const Key('submissionQueuedBanner')),
          findsOneWidget,
        );
        expect(requestsClient.submitCalls, isEmpty);

        final pending = queue.pending;
        expect(pending, hasLength(1));
        expect(pending.single.endpoint, 'requests');
        final stampedKey = pending.single.idempotencyKey;

        // Connectivity returns.
        requestsClient.createError = null;
        requestsClient.createResult = PurchaseRequest(
          id: 'req-replayed',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requiredByDate: '2026-10-01',
          status: 'draft',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.now(),
        );
        final replay = OfflineQueueReplay(
          queue: queue,
          apiClient: FakeMobileApiClient(),
          requestsApiClient: requestsClient,
        );
        await replay.processQueue();

        // Two createRequest calls total: the original failed attempt (whose
        // body was still recorded before it threw) plus the replay's
        // successful one — both carrying the same stamped idempotency key,
        // never a fresh one generated at send time (FR-011).
        expect(requestsClient.createCalls, hasLength(2));
        expect(requestsClient.createIdempotencyKeys, [stampedKey, stampedKey]);
        expect(requestsClient.submitCalls, ['req-replayed']);
        expect(queue.pending, isEmpty);
      },
    );

    testWidgets(
      'a draft already saved online whose later submit fails offline is '
      'shown queued, then replays exactly once when connectivity returns',
      (tester) async {
        requestsClient.createResult = PurchaseRequest(
          id: 'req-existing-draft',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requiredByDate: '2026-10-01',
          status: 'draft',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.now(),
        );

        await pumpWithServices(
          tester,
          child: RequestFormScreen(offlineQueueService: queue),
          requestsApiClient: requestsClient,
        );
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(const Key('requestFormBranchField')));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Main Branch').last);
        await tester.pumpAndSettle();

        final requiredByField = find.byKey(
          const Key('requestFormRequiredByField'),
        );
        await tester.ensureVisible(requiredByField);
        await tester.enterText(requiredByField, '2026-10-01');
        await tester.pumpAndSettle();

        final productField = find.byKey(
          const Key('requestLine_0_productSearch'),
        );
        await tester.ensureVisible(productField);
        await tester.enterText(productField, 'product-1');
        await tester.pumpAndSettle();

        final quantityField = find.byKey(const Key('requestLine_0_quantity'));
        await tester.ensureVisible(quantityField);
        await tester.enterText(quantityField, '5');
        await tester.pumpAndSettle();

        // Save Draft succeeds online (goes through the direct API call).
        final saveDraftButton = find.byKey(
          const Key('requestFormSaveDraftButton'),
        );
        await tester.ensureVisible(saveDraftButton);
        await tester.tap(saveDraftButton);
        await tester.pumpAndSettle();
        // Let the save-success SnackBar's own auto-dismiss timer clear
        // before tapping Submit, or the still-visible SnackBar can obscure
        // the submit button from the hit test (established pattern, see
        // request_form_test.dart's "submit calls submitRequest" test).
        await tester.pump(const Duration(seconds: 2));
        await tester.pumpAndSettle();
        expect(requestsClient.createCalls, hasLength(1));

        // Connectivity drops before Submit.
        requestsClient.submitError = _OfflineError();
        final submitButton = find.byKey(const Key('requestFormSubmitButton'));
        await tester.ensureVisible(submitButton);
        await tester.tap(submitButton);
        await tester.pumpAndSettle();

        expect(
          find.byKey(const Key('submissionQueuedBanner')),
          findsOneWidget,
        );
        final pending = queue.pending;
        expect(pending, hasLength(1));
        expect(pending.single.endpoint, 'requests/submit');

        // Connectivity returns — only the submit call replays, no second
        // create.
        requestsClient.submitError = null;
        final replay = OfflineQueueReplay(
          queue: queue,
          apiClient: FakeMobileApiClient(),
          requestsApiClient: requestsClient,
        );
        await replay.processQueue();

        // No second create — only the submit call replays. It appears twice
        // in submitCalls because the original failed attempt was recorded
        // before it threw, same as the create-side assertions above.
        expect(requestsClient.createCalls, hasLength(1));
        expect(requestsClient.submitCalls, [
          'req-existing-draft',
          'req-existing-draft',
        ]);
        expect(queue.pending, isEmpty);
      },
    );
  });

  group('Offline submission — low-stock report', () {
    late _FakeOfflineQueue queue;
    late FakeMobileApiClient mobileClient;
    late FakeRequestsApiClient requestsClient;

    final testProduct = CatalogueProduct(
      id: 'product-1',
      tenantName: 'Fresh Whole Milk 2L',
      canonicalName: 'Fresh Whole Milk 2L',
      baseUnit: 'bottle',
      status: 'active',
      createdAt: DateTime.now(),
    );

    setUp(() {
      queue = _FakeOfflineQueue();
      mobileClient = FakeMobileApiClient();
      requestsClient = FakeRequestsApiClient()
        ..branches = [
          Branch(
            id: 'branch-1',
            name: 'Downtown Branch',
            isActive: true,
            createdAt: DateTime.now(),
          ),
        ]
        ..catalogueSearchResults = [testProduct];
    });

    testWidgets(
      'a low-stock report that fails to send offline is shown queued, then '
      'replays exactly once when connectivity returns',
      (tester) async {
        mobileClient.createLowStockError = _OfflineError();

        await pumpWithServices(
          tester,
          child: LowStockReportScreen(
            initialProduct: testProduct,
            initialBranchId: 'branch-1',
            offlineQueueService: queue,
          ),
          mobileApiClient: mobileClient,
          requestsApiClient: requestsClient,
        );
        await tester.pumpAndSettle();

        final submitButton = find.byKey(const Key('lowStockSubmitButton'));
        await tester.ensureVisible(submitButton);
        await tester.tap(submitButton);
        await tester.pumpAndSettle();

        // Honestly shown as queued, never as the confirmed message.
        expect(
          find.byKey(const Key('submissionQueuedBanner')),
          findsOneWidget,
        );
        expect(find.byKey(const Key('lowStockSuccessIcon')), findsNothing);

        final pending = queue.pending;
        expect(pending, hasLength(1));
        expect(pending.single.endpoint, 'low-stock-reports');
        final stampedKey = pending.single.idempotencyKey;

        // Connectivity returns.
        mobileClient.createLowStockError = null;
        final replay = OfflineQueueReplay(
          queue: queue,
          apiClient: mobileClient,
          requestsApiClient: requestsClient,
        );
        await replay.processQueue();

        // Two calls total: the original failed attempt plus the replay's
        // successful one, both carrying the same stamped idempotency key,
        // never a fresh one generated at send time (FR-011).
        expect(mobileClient.createLowStockCalls, hasLength(2));
        expect(
          mobileClient.createLowStockCalls.map((c) => c['idempotencyKey']),
          [stampedKey, stampedKey],
        );
        expect(queue.pending, isEmpty);
      },
    );
  });
}
