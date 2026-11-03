import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/features/approvals/approval_queue_screen.dart';

import '../../test_helpers.dart';
import 'split_approval_fixtures.dart';

void main() {
  group('ApprovalQueueScreen', () {
    late FakeApprovalsApiClient fakeClient;
    late FakeRequestsApiClient fakeRequestsClient;

    setUp(() {
      fakeRequestsClient = FakeRequestsApiClient();
      fakeClient = FakeApprovalsApiClient()
        ..pendingResults = [
          pendingRequest(
            id: 'req-1',
            requester: 'member-uuid-1111',
            requesterName: 'Sarah Connor',
          ),
          pendingRequest(
            id: 'req-2',
            requester: 'member-uuid-2222',
            requesterEmail: 'john@example.com',
          ),
        ];
    });

    Future<void> pumpQueue(WidgetTester tester, {String locale = 'en'}) async {
      await tester.pumpWidget(const SizedBox.shrink());
      await pumpWithServices(
        tester,
        child: const ApprovalQueueScreen(),
        approvalsApiClient: fakeClient,
        requestsApiClient: fakeRequestsClient,
        locale: locale,
      );
      await tester.pumpAndSettle();
    }

    final loadMore = find.byKey(const Key('approvalQueueLoadMore'));
    final status = find.byKey(const Key('approvalQueueStatus'));

    void servePages() {
      fakeClient.pendingPage = (cursor, limit) async => cursor == null
          ? PendingApprovalsList(
              items: fakeClient.pendingResults,
              nextCursor: 'opaque-page-2',
            )
          : PendingApprovalsList(
              items: [
                fakeClient.pendingResults.last,
                pendingRequest(
                  id: 'req-3',
                  requester: 'third',
                  requesterName: 'Third',
                ),
              ],
            );
    }

    testWidgets('pages append with overlap de-duplicated and request counts', (
      tester,
    ) async {
      servePages();
      await pumpQueue(tester);
      expect(find.text('Requester: Sarah Connor'), findsOneWidget);
      expect(find.text('Showing 2 requests, more available'), findsOneWidget);
      expect(find.text('Load more'), findsOneWidget);
      expect(tester.widget<FilledButton>(loadMore).onPressed, isNotNull);
      expect(
        tester
            .widget<Semantics>(
              find.ancestor(of: status, matching: find.byType(Semantics)).first,
            )
            .properties
            .liveRegion,
        isTrue,
      );
      expect(fakeClient.pendingCalls, [(cursor: null, limit: 50)]);

      await tester.tap(loadMore);
      await tester.pumpAndSettle();
      expect(find.text('Requester: Third'), findsOneWidget);
      expect(find.text('Requester: john@example.com'), findsOneWidget);
      expect(find.byType(ListTile), findsNWidgets(3));
      expect(find.text('Showing 3 requests'), findsOneWidget);
      expect(loadMore, findsNothing);
      expect(fakeClient.pendingCalls.last, (
        cursor: 'opaque-page-2',
        limit: 50,
      ));
    });

    testWidgets(
      'double tap sends one page request and disables loading button',
      (tester) async {
        servePages();
        await pumpQueue(tester);
        final page = Completer<PendingApprovalsList>();
        fakeClient.pendingPage = (cursor, limit) => page.future;
        await tester.tap(loadMore);
        await tester.tap(loadMore);
        await tester.pump();
        expect(fakeClient.pendingCalls.length, 2);
        expect(tester.widget<FilledButton>(loadMore).onPressed, isNull);
        expect(find.text('Loading...'), findsOneWidget);
        expect(
          find.descendant(
            of: loadMore,
            matching: find.byType(CircularProgressIndicator),
          ),
          findsOneWidget,
        );
        page.complete(const PendingApprovalsList(items: []));
        await tester.pumpAndSettle();
        expect(loadMore, findsNothing);
      },
    );

    testWidgets(
      'load-more failure keeps rows and cursor, announces error and retries',
      (tester) async {
        servePages();
        await pumpQueue(tester);
        fakeClient.pendingPage = (cursor, limit) async =>
            throw Exception('offline');
        await tester.tap(loadMore);
        await tester.pumpAndSettle();
        expect(find.byType(ListTile), findsNWidgets(2));
        final error = find.text(
          'Unable to load more requests. Please try again.',
        );
        expect(error, findsOneWidget);
        expect(
          tester.widget<Text>(error).style!.color,
          Theme.of(tester.element(error)).colorScheme.error,
        );
        expect(
          tester
              .widget<Semantics>(
                find
                    .ancestor(of: error, matching: find.byType(Semantics))
                    .first,
              )
              .properties
              .liveRegion,
          isTrue,
        );
        expect(tester.widget<FilledButton>(loadMore).onPressed, isNotNull);
        servePages();
        await tester.tap(loadMore);
        await tester.pumpAndSettle();
        expect(error, findsNothing);
        expect(find.text('Showing 3 requests'), findsOneWidget);
        expect(fakeClient.pendingCalls.map((call) => call.cursor), [
          null,
          'opaque-page-2',
          'opaque-page-2',
        ]);
      },
    );

    testWidgets(
      'decision reload resets paging and ignores a late page response',
      (tester) async {
        servePages();
        await pumpQueue(tester);
        final stalePage = Completer<PendingApprovalsList>();
        fakeClient.pendingPage = (cursor, limit) => stalePage.future;
        await tester.tap(loadMore);
        await tester.pump();
        await tester.tap(find.byKey(const Key('approvalQueueItem_0')));
        // The page spinner remains active beneath the decision route.
        await tester.pump();
        await tester.pump(const Duration(seconds: 1));
        final fresh = pendingRequest(
          id: 'fresh',
          requester: 'fresh',
          requesterName: 'Fresh',
        );
        fakeClient.pendingPage = (cursor, limit) async =>
            PendingApprovalsList(items: [fresh], nextCursor: 'fresh-cursor');
        await tester.tap(
          find.byKey(const Key('approvalDecisionApproveButton')),
        );
        await tester.pumpAndSettle();
        expect(find.text('Requester: Fresh'), findsOneWidget);
        expect(find.text('Requester: Sarah Connor'), findsNothing);
        expect(fakeClient.pendingCalls.last, (cursor: null, limit: 50));
        expect(tester.widget<FilledButton>(loadMore).onPressed, isNotNull);

        final freshPage = Completer<PendingApprovalsList>();
        fakeClient.pendingPage = (cursor, limit) => freshPage.future;
        await tester.tap(loadMore);
        await tester.pump();
        expect(fakeClient.pendingCalls.last, (
          cursor: 'fresh-cursor',
          limit: 50,
        ));
        stalePage.complete(
          PendingApprovalsList(
            items: [
              pendingRequest(
                id: 'stale',
                requester: 'stale',
                requesterName: 'Stale',
              ),
            ],
            nextCursor: 'stale-cursor',
          ),
        );
        await tester.pump();
        expect(find.text('Requester: Stale'), findsNothing);
        expect(tester.widget<FilledButton>(loadMore).onPressed, isNull);
        freshPage.complete(const PendingApprovalsList(items: []));
        await tester.pumpAndSettle();
        expect(find.text('Showing 1 request'), findsOneWidget);
        expect(loadMore, findsNothing);
      },
    );

    testWidgets(
      'a split arriving on page two counts requests and opens its decision screen',
      (tester) async {
        fakeClient.pendingPage = (cursor, limit) async => cursor == null
            ? PendingApprovalsList(
                items: [fakeClient.pendingResults.first],
                nextCursor: 'split-page',
              )
            : PendingApprovalsList(items: splitApprovalRequests());
        await pumpQueue(tester);
        await tester.tap(loadMore);
        await tester.pumpAndSettle();
        expect(find.byType(ListTile), findsNWidgets(2));
        expect(find.text('Showing 3 requests'), findsOneWidget);
        await tester.tap(find.byKey(const Key('approvalQueueItem_1')));
        await tester.pumpAndSettle();
        expect(find.text('الذهبي'), findsOneWidget);
        expect(find.text('الوفرة'), findsOneWidget);
        expect(
          find.byKey(const Key('approvalDecisionApproveButton')),
          findsOneWidget,
        );
      },
    );

    testWidgets('Arabic pagination fits narrow width with large text', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 1000);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      // Group cards avoid unrelated single-card trailing money constraints.
      final split = splitApprovalRequests();
      fakeClient.pendingResults = [
        ...split,
        PurchaseRequest.fromJson({...split.first.toJson(), 'id': 'third'}),
      ];
      servePages();
      await pumpQueue(tester, locale: 'ar');
      expect(find.text('عرض 3 طلبات، ويتوفر المزيد'), findsOneWidget);
      expect(find.text('تحميل المزيد'), findsOneWidget);
      expect(Directionality.of(tester.element(status)), TextDirection.rtl);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'renders requester name or email, never the raw membership UUID',
      (tester) async {
        await pumpQueue(tester);

        expect(find.text('Approval Queue'), findsOneWidget);
        expect(find.byKey(const Key('approvalQueueList')), findsOneWidget);
        expect(find.text('Requester: Sarah Connor'), findsOneWidget);
        expect(find.text('Requester: john@example.com'), findsOneWidget);
        expect(find.textContaining('member-uuid-1111'), findsNothing);
        expect(find.textContaining('member-uuid-2222'), findsNothing);
        expect(find.text('USD 125'), findsNWidgets(2));
      },
    );

    testWidgets(
      'falls back to localised unknown requester when name and email are missing',
      (tester) async {
        fakeClient.pendingResults = [
          pendingRequest(id: 'req-3', requester: 'member-uuid-3333'),
        ];
        await pumpQueue(tester);
        expect(find.text('Requester: Unknown requester'), findsOneWidget);
        expect(find.textContaining('member-uuid-3333'), findsNothing);

        await pumpQueue(tester, locale: 'ar');
        expect(find.textContaining('مقدم طلب غير معروف'), findsOneWidget);
        expect(find.textContaining('member-uuid-3333'), findsNothing);
      },
    );

    testWidgets('renders empty state when no approvals are pending', (
      tester,
    ) async {
      fakeClient.pendingResults = [];
      await pumpQueue(tester);

      expect(
        find.text('No requests are currently awaiting your decision.'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('approvalQueueList')), findsNothing);
    });

    testWidgets('collapses a split into one card and keeps single requests', (
      tester,
    ) async {
      final single = fakeClient.pendingResults.first;
      fakeClient.pendingResults = [
        splitApprovalRequests()[1],
        single,
        splitApprovalRequests()[0],
      ];
      await pumpQueue(tester);

      expect(find.byType(ListTile), findsNWidgets(2));
      expect(
        find.text(
          'Split from RFQ rfq-1234 · 2 requests · SAR 4,063 · saves SAR 74',
        ),
        findsOneWidget,
      );
      expect(find.text('Requester: Sarah Connor'), findsOneWidget);
      expect(find.text('USD 125'), findsOneWidget);
      expect(find.text('Required By: Oct 1, 2026'), findsOneWidget);
      expect(find.text('SAR 2,773'), findsNothing);
      expect(find.text('SAR 1,290'), findsNothing);
    });

    testWidgets('renders the split card in Arabic with RTL money', (
      tester,
    ) async {
      fakeClient.pendingResults = splitApprovalRequests();
      await pumpQueue(tester, locale: 'ar');

      final card = find.byKey(const Key('approvalQueueItem_0'));
      expect(find.byType(ListTile), findsOneWidget);
      expect(
        find.textContaining('تقسيم من طلب تسعير rfq-1234 · طلبان'),
        findsOneWidget,
      );
      expect(find.textContaining('٤٬٠٦٣ ر.س'), findsOneWidget);
      expect(find.textContaining('يوفر \u2068٧٤ ر.س\u2069'), findsOneWidget);
      expect(Directionality.of(tester.element(card)), TextDirection.rtl);
      expect(tester.takeException(), isNull);
    });

    testWidgets('opens a split with both suppliers and their totals', (
      tester,
    ) async {
      fakeClient.pendingResults = splitApprovalRequests();
      await pumpQueue(tester);
      await tester.tap(find.byKey(const Key('approvalQueueItem_0')));
      await tester.pumpAndSettle();

      expect(find.text('الذهبي'), findsOneWidget);
      expect(find.text('الوفرة'), findsOneWidget);
      expect(find.text('SAR 2,773'), findsOneWidget);
      expect(find.text('SAR 1,290'), findsOneWidget);
      expect(find.text('SAR 4,063'), findsOneWidget);
    });

    testWidgets('a group approval removes the single split card after reload', (
      tester,
    ) async {
      fakeClient.pendingResults = splitApprovalRequests();
      await pumpQueue(tester);
      await tester.tap(find.byKey(const Key('approvalQueueItem_0')));
      await tester.pumpAndSettle();
      fakeClient.pendingResults = [];

      final approve = find.byKey(const Key('approvalDecisionApproveButton'));
      await tester.ensureVisible(approve);
      await tester.pumpAndSettle();
      await tester.tap(approve);
      await tester.pumpAndSettle();

      expect(fakeClient.approveGroupCalls, [splitGroupId]);
      expect(fakeRequestsClient.approveCalls, isEmpty);
      expect(
        find.text('No requests are currently awaiting your decision.'),
        findsOneWidget,
      );
    });

    testWidgets('does not display a saving when the API has none', (
      tester,
    ) async {
      fakeClient.pendingResults = [
        for (final request in splitApprovalRequests())
          PurchaseRequest.fromJson({
            ...request.toJson(),
            'request_group': {
              ...request.requestGroup!.toJson(),
              'saving': null,
            },
          }),
      ];
      await pumpQueue(tester);

      expect(find.byType(ListTile), findsOneWidget);
      expect(
        find.text('Split from RFQ rfq-1234 · 2 requests · SAR 4,063'),
        findsOneWidget,
      );
      expect(find.textContaining('saves'), findsNothing);
    });

    testWidgets('formats money in English and Arabic', (tester) async {
      fakeClient.pendingResults = [
        pendingRequest(
          id: 'req-egp',
          requester: 'member-egp',
          requesterName: 'Ahmed',
          total: const Money(amount: '12500', currency: 'EGP'),
        ),
      ];
      await pumpQueue(tester);
      expect(find.text('EGP 12,500'), findsOneWidget);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('١٢٬٥٠٠'), findsOneWidget);
      expect(find.byType(Directionality), findsWidgets);
    });

    testWidgets('formats required-by date in English and Arabic', (
      tester,
    ) async {
      fakeClient.pendingResults = [
        PurchaseRequest(
          id: 'req-date',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requesterName: 'Sarah Connor',
          requiredByDate: '2026-10-28',
          status: 'submitted',
          lines: const [
            PurchaseRequestLine(
              id: 'line-1',
              workspaceProductId: 'product-1',
              quantity: '5',
            ),
          ],
          estimatedTotal: const Money(amount: '125.00', currency: 'USD'),
          hasIncompleteEstimate: false,
          approvalStep: const ApprovalStep(
            id: 'step-1',
            assignedMembershipId: 'approver-1',
            source: 'threshold_match',
            status: 'pending',
          ),
          createdAt: DateTime.utc(2026, 9, 13),
        ),
      ];

      await pumpQueue(tester, locale: 'en');
      expect(find.text('Required By: Oct 28, 2026'), findsOneWidget);
      expect(find.textContaining('2026-10-28'), findsNothing);

      await pumpQueue(tester, locale: 'ar');
      expect(find.textContaining('مطلوب قبل: ٢٨ أكتوبر ٢٠٢٦'), findsOneWidget);
      expect(find.textContaining('2026-10-28'), findsNothing);
    });

    testWidgets('navigating to decision screen and approving reloads queue', (
      tester,
    ) async {
      await pumpQueue(tester);
      expect(find.byKey(const Key('approvalQueueItem_0')), findsOneWidget);

      // Simulate backend having 0 pending items once approved
      fakeClient.pendingResults = [];

      await tester.tap(find.byKey(const Key('approvalQueueItem_0')));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('approvalDecisionApproveButton')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('approvalDecisionApproveButton')));
      await tester.pumpAndSettle();

      // Popped back to ApprovalQueueScreen
      expect(find.byType(ApprovalQueueScreen), findsOneWidget);
      expect(
        find.byKey(const Key('approvalDecisionApproveButton')),
        findsNothing,
      );

      // Reloaded queue
      expect(
        find.text('No requests are currently awaiting your decision.'),
        findsOneWidget,
      );
    });
  });
}

PurchaseRequest pendingRequest({
  required String id,
  required String requester,
  String? requesterName,
  String? requesterEmail,
  Money total = const Money(amount: '125.00', currency: 'USD'),
}) {
  return PurchaseRequest(
    id: id,
    branchId: 'branch-1',
    requestedByMembershipId: requester,
    requesterName: requesterName,
    requesterEmail: requesterEmail,
    requiredByDate: '2026-10-01',
    status: 'submitted',
    lines: const [
      PurchaseRequestLine(
        id: 'line-1',
        workspaceProductId: 'product-1',
        quantity: '5',
      ),
    ],
    estimatedTotal: total,
    hasIncompleteEstimate: false,
    approvalStep: const ApprovalStep(
      id: 'step-1',
      assignedMembershipId: 'approver-1',
      source: 'threshold_match',
      status: 'pending',
    ),
    createdAt: DateTime.utc(2026, 9, 13),
  );
}
