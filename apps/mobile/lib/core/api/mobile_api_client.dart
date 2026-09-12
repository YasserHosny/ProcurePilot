import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Typed Dart client for the R2.2 mobile API surface.
///
/// Covers [POST /devices], [DELETE /devices/{id}], [GET /low-stock-reports]
/// and [POST /low-stock-reports] exactly as declared in
/// `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`.
///
/// [apiBaseUrl] is this project's own FastAPI backend (base path `/api/v1`,
/// `Authorization: Bearer <supabase_jwt>` per CLAUDE.md's API conventions —
/// the same backend apps/web talks to, at its own origin, e.g.
/// `https://api.procurepilot.example.com/api/v1`) — a DIFFERENT server from
/// the Supabase project. `AuthService` is the only place that talks to the
/// Supabase project directly (its own `/auth/v1/token` endpoint); this
/// client never does, and sends only `Authorization`/`Content-Type`/
/// `Idempotency-Key` headers — no `apikey` header, which is a
/// Supabase-gateway convention apps/api's own auth middleware does not
/// expect.
class MobileApiClient {
  MobileApiClient({
    required this.apiBaseUrl,
    http.Client? httpClient,
  }) : _httpClient = httpClient ?? http.Client();

  final String apiBaseUrl;
  final http.Client _httpClient;

  /// Bearer token used for authenticated endpoints. Set by the auth core
  /// after sign-in or refresh.
  String? accessToken;

  /// Registers or refreshes a device push-token registration.
  Future<DeviceRegistration> registerDevice({
    required DevicePlatform platform,
    required String pushToken,
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$apiBaseUrl/devices');
    final body = jsonEncode(
      DeviceRegistrationCreate(platform: platform, pushToken: pushToken).toJson(),
    );
    final response = await _httpClient.post(
      uri,
      headers: _headers(idempotencyKey: idempotencyKey),
      body: body,
    );
    _checkResponse(response);
    return DeviceRegistration.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Removes the caller's own device registration (sign-out).
  Future<void> deleteDevice(String deviceId, {String? idempotencyKey}) async {
    final uri = Uri.parse('$apiBaseUrl/devices/$deviceId');
    final response = await _httpClient.delete(
      uri,
      headers: _headers(idempotencyKey: idempotencyKey),
    );
    _checkResponse(response);
  }

  /// Lists low-stock reports visible to the caller.
  Future<LowStockReportList> listLowStockReports({
    String? branchId,
    String? workspaceProductId,
    String? cursor,
    int limit = 50,
  }) async {
    final query = <String, String>{
      if (branchId != null) 'branch_id': branchId,
      if (workspaceProductId != null) 'workspace_product_id': workspaceProductId,
      if (cursor != null) 'cursor': cursor,
      'limit': limit.toString(),
    };
    final uri = Uri.parse('$apiBaseUrl/low-stock-reports')
        .replace(queryParameters: query);
    final response = await _httpClient.get(uri, headers: _headers());
    _checkResponse(response);
    return LowStockReportList.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  /// Records a low-stock report.
  Future<LowStockReport> createLowStockReport({
    required String branchId,
    required String workspaceProductId,
    String? countRemaining,
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$apiBaseUrl/low-stock-reports');
    final body = jsonEncode(
      LowStockReportCreate(
        branchId: branchId,
        workspaceProductId: workspaceProductId,
        countRemaining: countRemaining,
      ).toJson(),
    );
    final response = await _httpClient.post(
      uri,
      headers: _headers(idempotencyKey: idempotencyKey),
      body: body,
    );
    _checkResponse(response);
    return LowStockReport.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Map<String, String> _headers({String? idempotencyKey}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
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
