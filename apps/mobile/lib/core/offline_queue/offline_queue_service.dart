import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:uuid/uuid.dart';

/// Local status of an offline queue item.
enum QueueItemStatus {
  draft,
  queued,
  confirmed,
  failed,
}

/// A queued mutation that carries its [idempotencyKey] stamped at creation
/// time, not at send time.
@immutable
class QueueItem {
  const QueueItem({
    required this.idempotencyKey,
    required this.endpoint,
    required this.payload,
    required this.status,
    required this.createdAt,
    required this.retries,
  });

  final String idempotencyKey;
  final String endpoint;
  final Map<String, dynamic> payload;
  final QueueItemStatus status;
  final DateTime createdAt;
  final int retries;

  factory QueueItem.fromJson(Map<String, dynamic> json) {
    return QueueItem(
      idempotencyKey: json['idempotency_key'] as String,
      endpoint: json['endpoint'] as String,
      payload: json['payload'] as Map<String, dynamic>,
      status: QueueItemStatus.values.byName(json['status'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
      retries: json['retries'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'idempotency_key': idempotencyKey,
        'endpoint': endpoint,
        'payload': payload,
        'status': status.name,
        'created_at': createdAt.toIso8601String(),
        'retries': retries,
      };

  QueueItem copyWith({
    QueueItemStatus? status,
    int? retries,
  }) {
    return QueueItem(
      idempotencyKey: idempotencyKey,
      endpoint: endpoint,
      payload: payload,
      status: status ?? this.status,
      createdAt: createdAt,
      retries: retries ?? this.retries,
    );
  }
}

/// Local persistence for the offline submission queue.
///
/// Items are stored as JSON strings keyed by their idempotency key so retries
/// reuse the same key automatically.
class OfflineQueueService {
  OfflineQueueService({required this.box, Uuid? uuid})
      : uuid = uuid ?? const Uuid();

  final Box<String> box;
  final Uuid uuid;

  /// Creates a local draft with a fresh UUID stamped as the idempotency key.
  Future<QueueItem> createDraft({
    required String endpoint,
    required Map<String, dynamic> payload,
  }) async {
    final item = QueueItem(
      idempotencyKey: uuid.v4(),
      endpoint: endpoint,
      payload: payload,
      status: QueueItemStatus.draft,
      createdAt: DateTime.now().toUtc(),
      retries: 0,
    );
    await _save(item);
    return item;
  }

  /// Promotes a draft to [QueueItemStatus.queued].
  Future<QueueItem> enqueue(QueueItem item) async {
    final queued = item.copyWith(status: QueueItemStatus.queued);
    await _save(queued);
    return queued;
  }

  /// Convenience helper that creates and enqueues in one call.
  Future<QueueItem> createAndEnqueue({
    required String endpoint,
    required Map<String, dynamic> payload,
  }) async {
    final draft = await createDraft(endpoint: endpoint, payload: payload);
    return enqueue(draft);
  }

  /// All items that still need to be sent.
  List<QueueItem> get pending {
    return box.values
        .map((raw) => QueueItem.fromJson(jsonDecode(raw) as Map<String, dynamic>))
        .where(
          (item) =>
              item.status == QueueItemStatus.queued ||
              item.status == QueueItemStatus.failed,
        )
        .toList();
  }

  /// Marks an item as successfully confirmed by the server.
  Future<void> markConfirmed(String idempotencyKey) async {
    final raw = box.get(idempotencyKey);
    if (raw == null) return;
    final item = QueueItem.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    await _save(item.copyWith(status: QueueItemStatus.confirmed));
  }

  /// Records a failed send attempt and increments the retry counter.
  Future<void> markFailed(String idempotencyKey) async {
    final raw = box.get(idempotencyKey);
    if (raw == null) return;
    final item = QueueItem.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    await _save(
      item.copyWith(
        status: QueueItemStatus.failed,
        retries: item.retries + 1,
      ),
    );
  }

  /// Deletes a queued item (used once the server confirms it, or for tests).
  Future<void> remove(String idempotencyKey) async {
    await box.delete(idempotencyKey);
  }

  Future<void> _save(QueueItem item) async {
    await box.put(item.idempotencyKey, jsonEncode(item.toJson()));
  }
}
