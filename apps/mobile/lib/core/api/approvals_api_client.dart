import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Typed Dart client for the R2.1 Requests + Approvals contract (008).
///
/// This is intentionally separate from [MobileApiClient], which covers the
/// R2.2-specific mobile surface (`/devices`, `/low-stock-reports`). The
/// endpoint below already exists and is unchanged; this client is simply the
/// mobile app's first Dart caller of it.
class ApprovalsApiClient {
  ApprovalsApiClient({required this.apiBaseUrl, http.Client? httpClient})
    : _httpClient = httpClient ?? http.Client();

  final String apiBaseUrl;
  final http.Client _httpClient;

  /// Bearer token used for authenticated endpoints. Set by the auth core
  /// after sign-in or refresh.
  String? accessToken;

  /// Lists purchase requests currently pending the signed-in approver's
  /// decision.
  ///
  /// Known pilot-scale simplification: this returns only the first page
  /// (capped at [limit] = 100). Counting exhaustively across pages is not
  /// required for this release because a single approver is not expected to
  /// have more than 100 pending requests at once.
  Future<PendingApprovalsList> listPendingApprovals({
    String? cursor,
    int limit = 100,
  }) async {
    final query = <String, String>{
      if (cursor != null) 'cursor': cursor,
      'limit': limit.clamp(1, 100).toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/approvals/pending')
        .replace(queryParameters: query);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return PendingApprovalsList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Map<String, String> _headers() {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (accessToken != null && accessToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $accessToken';
    }
    return headers;
  }

  void _checkResponse(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;

    final Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException(
        statusCode: response.statusCode,
        code: 'unknown_error',
        message: response.body,
        traceId: '',
      );
    }

    throw ApiException(
      statusCode: response.statusCode,
      code: body['code'] as String? ?? 'unknown_error',
      message: body['message'] as String? ?? 'Unexpected API error',
      details: body['details'] as Map<String, dynamic>?,
      traceId: body['trace_id'] as String? ?? '',
    );
  }
}

/// Cursor-paginated list of pending approvals.
///
/// Pending approval rows now carry the full [PurchaseRequest] context because
/// the mobile approval flow is authorized to render and decide on them.
class PendingApprovalsList {
  const PendingApprovalsList({required this.items, this.nextCursor});

  final List<PurchaseRequest> items;
  final String? nextCursor;

  factory PendingApprovalsList.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>? ?? const [];
    final items = rawItems
        .map((e) => PurchaseRequest.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
    return PendingApprovalsList(
      items: items,
      nextCursor: json['next_cursor'] as String?,
    );
  }
}
