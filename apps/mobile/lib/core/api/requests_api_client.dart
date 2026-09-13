import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Typed Dart client for the R2.1 Requests + Approvals contract (008).
///
/// This is intentionally separate from [MobileApiClient], which covers the
/// R2.2-specific mobile surface (`/devices`, `/low-stock-reports`), and from
/// [ApprovalsApiClient], which covers the approver-facing
/// `GET /approvals/pending` surface.
///
/// This client is the mobile app's caller for the requester-side
/// `/requests` CRUD surface, its existing human decision endpoints, plus the supporting organisation/catalogue
/// lookups (`GET /organisation/branches`, `GET /organisation/cost-centres`,
/// `GET /products`) needed by the request form. It must never reference
/// a mobile-specific decision path.
class RequestsApiClient {
  RequestsApiClient({required this.apiBaseUrl, http.Client? httpClient})
    : _httpClient = httpClient ?? http.Client();

  final String apiBaseUrl;
  final http.Client _httpClient;

  /// Bearer token used for authenticated endpoints. Set by the auth core
  /// after sign-in or refresh.
  String? accessToken;

  /// Lists purchase requests visible to the caller.
  Future<PurchaseRequestList> listRequests({
    String? status,
    String? branchId,
    String? cursor,
    int limit = 50,
  }) async {
    final query = <String, String>{
      if (status != null) 'status': status,
      if (branchId != null) 'branch_id': branchId,
      if (cursor != null) 'cursor': cursor,
      'limit': limit.clamp(1, 100).toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/requests')
        .replace(queryParameters: query);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return PurchaseRequestList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Creates a new purchase request in `draft` status.
  Future<PurchaseRequest> createRequest(
    PurchaseRequestCreate body, {
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$apiBaseUrl/requests');
    final response = await _httpClient.post(
      uri,
      headers: _headers(idempotencyKey: idempotencyKey),
      body: jsonEncode(body.toJson()),
    );
    _checkResponse(response);
    return PurchaseRequest.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Gets a single purchase request.
  Future<PurchaseRequest> getRequest(String requestId) async {
    final uri = Uri.parse('$apiBaseUrl/requests/$requestId');
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return PurchaseRequest.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Updates a draft purchase request.
  ///
  /// A 409 response means the request is no longer a draft; callers should
  /// surface it as an expected error state rather than crashing.
  Future<PurchaseRequest> updateRequest(
    String requestId,
    PurchaseRequestUpdate body,
  ) async {
    final uri = Uri.parse('$apiBaseUrl/requests/$requestId');
    final response = await _httpClient.patch(
      uri,
      headers: _headers(),
      body: jsonEncode(body.toJson()),
    );
    _checkResponse(response);
    return PurchaseRequest.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Submits a draft purchase request.
  Future<PurchaseRequest> submitRequest(
    String requestId, {
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$apiBaseUrl/requests/$requestId/submit');
    final response = await _httpClient.post(
      uri,
      headers: _headers(idempotencyKey: idempotencyKey),
    );
    _checkResponse(response);
    return PurchaseRequest.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Approves a pending purchase request using the existing 008 endpoint.
  Future<PurchaseRequest> approveRequest(String requestId, {String? comment}) {
    return _decideRequest(requestId, action: 'approve', comment: comment);
  }

  /// Rejects a pending purchase request using the existing 008 endpoint.
  Future<PurchaseRequest> rejectRequest(String requestId, {String? comment}) {
    return _decideRequest(requestId, action: 'reject', comment: comment);
  }

  Future<PurchaseRequest> _decideRequest(
    String requestId, {
    required String action,
    String? comment,
  }) async {
    final uri = Uri.parse('$apiBaseUrl/requests/$requestId/$action');
    final trimmedComment = comment?.trim();
    final response = await _httpClient.post(
      uri,
      headers: _headers(),
      body: jsonEncode({
        if (trimmedComment != null && trimmedComment.isNotEmpty)
          'comment': trimmedComment,
      }),
    );
    _checkResponse(response);
    return PurchaseRequest.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Lists active branches for the branch selector.
  Future<BranchList> listBranches({String? cursor, int limit = 100}) async {
    final query = <String, String>{
      if (cursor != null) 'cursor': cursor,
      'limit': limit.clamp(1, 100).toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/organisation/branches')
        .replace(queryParameters: query);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return BranchList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Lists cost centres for the optional cost-centre selector.
  Future<CostCentreList> listCostCentres({
    String? cursor,
    int limit = 100,
  }) async {
    final query = <String, String>{
      if (cursor != null) 'cursor': cursor,
      'limit': limit.clamp(1, 100).toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/organisation/cost-centres')
        .replace(queryParameters: query);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return CostCentreList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Searches the catalogue by product name for the line-item picker.
  Future<CatalogueProductList> searchCatalogue({
    required String query,
    String? cursor,
    int limit = 20,
  }) async {
    final params = <String, String>{
      'q': query,
      if (cursor != null) 'cursor': cursor,
      'limit': limit.clamp(1, 100).toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/products')
        .replace(queryParameters: params);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return CatalogueProductList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Map<String, String> _headers({String? idempotencyKey}) {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (accessToken != null && accessToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $accessToken';
    }
    if (idempotencyKey != null && idempotencyKey.isNotEmpty) {
      headers['Idempotency-Key'] = idempotencyKey;
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
