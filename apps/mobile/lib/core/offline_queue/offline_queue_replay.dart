import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../api/mobile_api_client.dart';
import 'offline_queue_service.dart';

/// Replays pending offline submissions when connectivity returns, reusing the
/// idempotency key that was stamped at creation time.
class OfflineQueueReplay {
  OfflineQueueReplay({
    required this.queue,
    required this.apiClient,
    Connectivity? connectivity,
  }) : connectivity = connectivity ?? Connectivity();

  final OfflineQueueService queue;
  final MobileApiClient apiClient;
  final Connectivity connectivity;
  StreamSubscription<List<ConnectivityResult>>? _subscription;

  /// Starts listening to connectivity changes.
  void start() {
    _subscription = connectivity.onConnectivityChanged.listen(_onChanged);
  }

  /// Stops listening to connectivity changes.
  void stop() {
    _subscription?.cancel();
    _subscription = null;
  }

  void _onChanged(List<ConnectivityResult> results) {
    final result = results.isNotEmpty ? results.first : ConnectivityResult.none;
    if (result != ConnectivityResult.none) {
      processQueue();
    }
  }

  /// Sends every pending item using its original idempotency key.
  ///
  /// Visible for testing; normally triggered by connectivity events.
  @visibleForTesting
  Future<void> processQueue() async {
    for (final item in queue.pending) {
      try {
        await _send(item);
        await queue.markConfirmed(item.idempotencyKey);
      } on Exception {
        await queue.markFailed(item.idempotencyKey);
      }
    }
  }

  Future<void> _send(QueueItem item) async {
    switch (item.endpoint) {
      case 'low-stock-reports':
        await apiClient.createLowStockReport(
          branchId: item.payload['branch_id'] as String,
          workspaceProductId: item.payload['workspace_product_id'] as String,
          countRemaining: item.payload['count_remaining'] as String?,
          idempotencyKey: item.idempotencyKey,
        );
      case 'requests':
        // Wired to the existing /requests endpoints in later user-story work.
        throw UnimplementedError('Request queue replay not yet wired');
      default:
        throw UnsupportedError('Unknown offline endpoint: ${item.endpoint}');
    }
  }
}
