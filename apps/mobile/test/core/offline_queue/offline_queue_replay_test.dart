import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_replay.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_service.dart';

import '../../test_helpers.dart';

class _OfflineError implements Exception {}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('procurepilot_replay_test');
    Hive.init(tempDir.path);
  });

  tearDownAll(() async {
    Hive.resetAdapters();
    await tempDir.delete(recursive: true);
  });

  group('OfflineQueueReplay', () {
    late Box<String> box;
    late OfflineQueueService queue;
    late FakeMobileApiClient mobileClient;
    late FakeRequestsApiClient requestsClient;
    late OfflineQueueReplay replay;

    setUp(() async {
      box = await Hive.openBox<String>('replay_queue_test');
      await box.clear();
      queue = OfflineQueueService(box: box);
      mobileClient = FakeMobileApiClient();
      requestsClient = FakeRequestsApiClient();
      replay = OfflineQueueReplay(
        queue: queue,
        apiClient: mobileClient,
        requestsApiClient: requestsClient,
      );
    });

    tearDown(() async {
      await box.deleteFromDisk();
    });

    test(
      'replays queued request by creating then submitting with same key',
      () async {
        final item = await queue.createAndEnqueue(
          endpoint: 'requests',
          payload: {
            'branch_id': 'branch-1',
            'required_by_date': '2026-10-01',
            'lines': [
              {'workspace_product_id': 'product-1', 'quantity': '4'},
            ],
          },
          idempotencyKey: 'request-key-1',
        );
        requestsClient.createResult = PurchaseRequest(
          id: 'req-1',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requiredByDate: '2026-10-01',
          status: 'draft',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.now(),
        );

        await replay.processQueue();

        expect(requestsClient.createCalls.single.branchId, 'branch-1');
        expect(requestsClient.createCalls.single.lines.single.quantity, '4');
        expect(requestsClient.createIdempotencyKeys, [item.idempotencyKey]);
        expect(requestsClient.submitCalls, ['req-1']);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'treats not_draft submit replay as success when request moved on',
      () async {
        await queue.createAndEnqueue(
          endpoint: 'requests',
          payload: {
            'branch_id': 'branch-1',
            'required_by_date': '2026-10-01',
            'lines': [
              {'workspace_product_id': 'product-1', 'quantity': '4'},
            ],
          },
          idempotencyKey: 'request-key-2',
        );
        requestsClient.createResult = PurchaseRequest(
          id: 'req-submitted',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requiredByDate: '2026-10-01',
          status: 'submitted',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.now(),
        );
        requestsClient.submitError = const ApiException(
          statusCode: 409,
          code: 'conflict',
          message: 'Request is not draft',
          details: {'reason': 'not_draft'},
          traceId: 'trace-1',
        );
        requestsClient.getRequestResults['req-submitted'] = PurchaseRequest(
          id: 'req-submitted',
          branchId: 'branch-1',
          requestedByMembershipId: 'member-1',
          requiredByDate: '2026-10-01',
          status: 'submitted',
          lines: const [],
          hasIncompleteEstimate: false,
          createdAt: DateTime.now(),
        );

        await replay.processQueue();

        expect(requestsClient.getRequestCalls, ['req-submitted']);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'marks request replay failed when create still cannot reach API',
      () async {
        final item = await queue.createAndEnqueue(
          endpoint: 'requests',
          payload: {
            'branch_id': 'branch-1',
            'required_by_date': '2026-10-01',
            'lines': [
              {'workspace_product_id': 'product-1', 'quantity': '4'},
            ],
          },
          idempotencyKey: 'request-key-3',
        );
        requestsClient.createError = _OfflineError();

        await replay.processQueue();

        final pending = queue.pending.single;
        expect(pending.idempotencyKey, item.idempotencyKey);
        expect(pending.status, QueueItemStatus.failed);
        expect(pending.retries, 1);
        expect(requestsClient.submitCalls, isEmpty);
      },
    );

    test(
      'replays a submit-only queue item for a draft already created online',
      () async {
        await queue.createAndEnqueue(
          endpoint: 'requests/submit',
          payload: {'request_id': 'req-existing-draft'},
          idempotencyKey: 'submit-key-1',
        );

        await replay.processQueue();

        expect(requestsClient.createCalls, isEmpty);
        expect(requestsClient.submitCalls, ['req-existing-draft']);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'treats a submit-only replay not_draft conflict as success when moved on',
      () async {
        await queue.createAndEnqueue(
          endpoint: 'requests/submit',
          payload: {'request_id': 'req-existing-draft-2'},
          idempotencyKey: 'submit-key-2',
        );
        requestsClient.submitError = const ApiException(
          statusCode: 409,
          code: 'conflict',
          message: 'Request is not draft',
          details: {'reason': 'not_draft'},
          traceId: 'trace-2',
        );
        requestsClient.getRequestResults['req-existing-draft-2'] =
            PurchaseRequest(
              id: 'req-existing-draft-2',
              branchId: 'branch-1',
              requestedByMembershipId: 'member-1',
              requiredByDate: '2026-10-01',
              status: 'submitted',
              lines: const [],
              hasIncompleteEstimate: false,
              createdAt: DateTime.now(),
            );

        await replay.processQueue();

        expect(requestsClient.getRequestCalls, ['req-existing-draft-2']);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'marks a submit-only replay failed on a genuine, non-conflict error',
      () async {
        final item = await queue.createAndEnqueue(
          endpoint: 'requests/submit',
          payload: {'request_id': 'req-existing-draft-3'},
          idempotencyKey: 'submit-key-3',
        );
        requestsClient.submitError = const ApiException(
          statusCode: 422,
          code: 'no_lines',
          message: 'Request has no lines',
          details: null,
          traceId: 'trace-3',
        );

        await replay.processQueue();

        final pending = queue.pending.single;
        expect(pending.idempotencyKey, item.idempotencyKey);
        expect(pending.status, QueueItemStatus.failed);
      },
    );

    test(
      'replays queued quality issue with photo by creating issue then uploading photo',
      () async {
        await queue.createAndEnqueue(
          endpoint: 'quality-issues',
          payload: {
            'request_id': 'req-delivered-1',
            'description': 'Damaged packaging and broken bottle',
            'photo_local_path': '/documents/stable_photo.jpg',
          },
          idempotencyKey: 'qi-key-1',
        );
        requestsClient.reportQualityIssueResult = QualityIssue(
          id: 'issue-created-1',
          purchaseRequestId: 'req-delivered-1',
          reportedByMembershipId: 'member-1',
          description: 'Damaged packaging and broken bottle',
          photos: const [],
          createdAt: DateTime.now(),
        );

        await replay.processQueue();

        expect(requestsClient.reportQualityIssueCalls, [
          {
            'requestId': 'req-delivered-1',
            'description': 'Damaged packaging and broken bottle',
          },
        ]);
        expect(requestsClient.uploadQualityIssuePhotoCalls, [
          {
            'issueId': 'issue-created-1',
            'filePath': '/documents/stable_photo.jpg',
          },
        ]);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'replays queued quality issue without photo (only creates issue, no photo upload)',
      () async {
        await queue.createAndEnqueue(
          endpoint: 'quality-issues',
          payload: {
            'request_id': 'req-delivered-2',
            'description': 'Wrong batch received',
          },
          idempotencyKey: 'qi-key-2',
        );
        requestsClient.reportQualityIssueResult = QualityIssue(
          id: 'issue-created-2',
          purchaseRequestId: 'req-delivered-2',
          reportedByMembershipId: 'member-1',
          description: 'Wrong batch received',
          photos: const [],
          createdAt: DateTime.now(),
        );

        await replay.processQueue();

        expect(requestsClient.reportQualityIssueCalls, [
          {
            'requestId': 'req-delivered-2',
            'description': 'Wrong batch received',
          },
        ]);
        expect(requestsClient.uploadQualityIssuePhotoCalls, isEmpty);
        expect(queue.pending, isEmpty);
      },
    );

    test(
      'marks quality issue replay failed when create still cannot reach API',
      () async {
        final item = await queue.createAndEnqueue(
          endpoint: 'quality-issues',
          payload: {
            'request_id': 'req-delivered-3',
            'description': 'Spoiled goods',
            'photo_local_path': '/documents/photo.jpg',
          },
          idempotencyKey: 'qi-key-3',
        );
        requestsClient.reportQualityIssueError = _OfflineError();

        await replay.processQueue();

        final pending = queue.pending.single;
        expect(pending.idempotencyKey, item.idempotencyKey);
        expect(pending.status, QueueItemStatus.failed);
        expect(pending.retries, 1);
        expect(requestsClient.uploadQualityIssuePhotoCalls, isEmpty);
      },
    );
  });
}
