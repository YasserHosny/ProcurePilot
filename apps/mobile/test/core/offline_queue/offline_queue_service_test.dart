import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:procurepilot_mobile/core/offline_queue/offline_queue_service.dart';
import 'package:uuid/uuid.dart';

class _FixedUuid extends Uuid {
  _FixedUuid(this.value);

  final String value;

  @override
  String v4({
    @Deprecated('use config instead. Removal in 5.0.0')
    Map<String, dynamic>? options,
    dynamic config,
  }) =>
      value;
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('procurepilot_test');
    Hive.init(tempDir.path);
  });

  tearDownAll(() async {
    Hive.resetAdapters();
    await tempDir.delete(recursive: true);
  });

  group('OfflineQueueService', () {
    late Box<String> box;

    setUp(() async {
      box = await Hive.openBox<String>('queue_test');
      await box.clear();
    });

    tearDown(() async {
      await box.deleteFromDisk();
    });

    test('createDraft stamps idempotency key at creation time', () async {
      final queue = OfflineQueueService(
        box: box,
        uuid: _FixedUuid('idempotency-123'),
      );

      final item = await queue.createDraft(
        endpoint: 'low-stock-reports',
        payload: {
          'branch_id': 'branch-1',
          'workspace_product_id': 'product-1',
        },
      );

      expect(item.idempotencyKey, 'idempotency-123');
      expect(item.status, QueueItemStatus.draft);
    });

    test('enqueue promotes a draft to queued', () async {
      final queue = OfflineQueueService(box: box);
      final draft = await queue.createDraft(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b1', 'workspace_product_id': 'p1'},
      );

      final queued = await queue.enqueue(draft);

      expect(queued.status, QueueItemStatus.queued);
      expect(queued.idempotencyKey, draft.idempotencyKey);
    });

    test('pending includes queued and failed items, not confirmed', () async {
      final queue = OfflineQueueService(box: box);
      final queued = await queue.createAndEnqueue(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b1', 'workspace_product_id': 'p1'},
      );
      final failedDraft = await queue.createDraft(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b2', 'workspace_product_id': 'p2'},
      );
      final failed = await queue.enqueue(failedDraft);
      await queue.markFailed(failed.idempotencyKey);
      final confirmed = await queue.createAndEnqueue(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b3', 'workspace_product_id': 'p3'},
      );
      await queue.markConfirmed(confirmed.idempotencyKey);

      final pending = queue.pending;

      expect(pending.map((i) => i.idempotencyKey),
          containsAll([queued.idempotencyKey, failed.idempotencyKey]));
      expect(
        pending.any((i) => i.idempotencyKey == confirmed.idempotencyKey),
        isFalse,
      );
    });

    test('retry keeps the same idempotency key', () async {
      final queue = OfflineQueueService(box: box);
      final item = await queue.createAndEnqueue(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b1', 'workspace_product_id': 'p1'},
      );
      final originalKey = item.idempotencyKey;

      await queue.markFailed(originalKey);
      await queue.markFailed(originalKey);
      final failed = queue.pending.firstWhere((i) => i.idempotencyKey == originalKey);

      expect(failed.idempotencyKey, originalKey);
      expect(failed.retries, 2);
    });

    test('markConfirmed removes item from pending', () async {
      final queue = OfflineQueueService(box: box);
      final item = await queue.createAndEnqueue(
        endpoint: 'low-stock-reports',
        payload: {'branch_id': 'b1', 'workspace_product_id': 'p1'},
      );

      await queue.markConfirmed(item.idempotencyKey);

      expect(queue.pending, isEmpty);
    });
  });
}
