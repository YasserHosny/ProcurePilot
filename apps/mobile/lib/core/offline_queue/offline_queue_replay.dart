import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../api/mobile_api_client.dart';
import '../api/models.dart';
import '../api/requests_api_client.dart';
import 'offline_queue_service.dart';

/// Replays pending offline submissions when connectivity returns, reusing the
/// idempotency key that was stamped at creation time.
class OfflineQueueReplay {
  OfflineQueueReplay({
    required this.queue,
    required this.apiClient,
    required this.requestsApiClient,
    Connectivity? connectivity,
  }) : connectivity = connectivity ?? Connectivity();

  final OfflineQueueService queue;
  final MobileApiClient apiClient;
  final RequestsApiClient requestsApiClient;
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
        await _sendRequest(item);
      default:
        throw UnsupportedError('Unknown offline endpoint: ${item.endpoint}');
    }
  }

  Future<void> _sendRequest(QueueItem item) async {
    final created = await requestsApiClient.createRequest(
      _requestCreateFromPayload(item.payload),
      idempotencyKey: item.idempotencyKey,
    );
    try {
      await requestsApiClient.submitRequest(created.id);
    } on ApiException catch (e) {
      if (e.statusCode != 409 || e.details?['reason'] != 'not_draft') {
        rethrow;
      }
      final current = await requestsApiClient.getRequest(created.id);
      if (!_isPastDraft(current.status)) {
        rethrow;
      }
    }
  }

  bool _isPastDraft(String status) {
    return status == 'submitted' ||
        status == 'pending' ||
        status == 'approved' ||
        status == 'rejected';
  }

  PurchaseRequestCreate _requestCreateFromPayload(
    Map<String, dynamic> payload,
  ) {
    final lines = (payload['lines'] as List<dynamic>).map((line) {
      final json = line as Map<String, dynamic>;
      return PurchaseRequestLineInput(
        workspaceProductId: json['workspace_product_id'] as String,
        quantity: json['quantity'] as String,
        note: json['note'] as String?,
      );
    }).toList();
    return PurchaseRequestCreate(
      branchId: payload['branch_id'] as String,
      costCentreId: payload['cost_centre_id'] as String?,
      requiredByDate: payload['required_by_date'] as String,
      lines: lines,
    );
  }
}
