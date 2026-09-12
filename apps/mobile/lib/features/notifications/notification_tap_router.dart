import 'package:flutter/widgets.dart';

import '../../core/api/requests_api_client.dart';

/// Routes notification taps to the request detail screen.
class NotificationTapRouter {
  const NotificationTapRouter({
    required this.requestsApiClient,
    required this.navigatorKey,
  });

  final RequestsApiClient requestsApiClient;
  final GlobalKey<NavigatorState> navigatorKey;

  Future<void> route(Map<String, String> payload) async {
    final requestId = payload['purchase_request_id'];
    if (requestId == null || requestId.isEmpty) return;

    final request = await requestsApiClient.getRequest(requestId);
    navigatorKey.currentState?.pushNamed(
      '/requests/detail',
      arguments: request,
    );
  }
}
