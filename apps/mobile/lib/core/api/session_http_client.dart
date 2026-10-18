import 'package:http/http.dart' as http;

import '../auth/auth_service.dart';

/// Shared by all ProcurePilot clients. Auth itself uses the raw transport so a
/// rejected refresh cannot recurse. Replays preserve bodies (including multipart
/// boundaries) and idempotency keys, and never retry more than once.
class SessionHttpClient extends http.BaseClient {
  SessionHttpClient({
    required this.inner,
    required this.authService,
    required String apiBaseUrl,
  }) : _apiBase = Uri.parse(apiBaseUrl);

  final http.Client inner;
  final AuthService authService;
  final Uri _apiBase;
  Future<void>? _refreshing;

  bool _isOwnApi(Uri uri) =>
      uri.origin == _apiBase.origin &&
      (uri.path == _apiBase.path ||
          uri.path.startsWith(
            '${_apiBase.path.replaceFirst(RegExp(r'/$'), '')}/',
          ));

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (!_isOwnApi(request.url)) return inner.send(request);

    // Finalize once: multipart streams cannot be sent twice. Buffer the encoded
    // request so the retry sends exactly the same bytes and content type.
    final bytes = await request.finalize().toBytes();
    Future<http.StreamedResponse> attempt(String? token) {
      final replay = http.Request(request.method, request.url)
        ..followRedirects = request.followRedirects
        ..maxRedirects = request.maxRedirects
        ..persistentConnection = request.persistentConnection
        ..headers.addAll(request.headers)
        ..bodyBytes = bytes;
      replay.headers.remove('Authorization');
      if (token != null && token.isNotEmpty) {
        replay.headers['Authorization'] = 'Bearer $token';
      }
      return inner.send(replay);
    }

    final sentToken = authService.accessToken;
    final response = await attempt(sentToken);
    if (response.statusCode != 401 || sentToken == null) return response;
    await response.stream.drain<void>();

    try {
      // A late 401 from the previous token can use the already renewed session.
      if (authService.accessToken == sentToken) {
        await (_refreshing ??= _refresh());
      }
    } catch (_) {
      await authService.expireSession();
      throw const AuthException('Session refresh failed');
    }
    if (authService.accessToken == null) {
      throw const AuthException('Session ended');
    }
    final retried = await attempt(authService.accessToken);
    if (retried.statusCode == 401) await authService.expireSession();
    return retried;
  }

  Future<void> _refresh() async {
    try {
      await authService.refreshSession();
    } finally {
      _refreshing = null;
    }
  }

  @override
  void close() => inner.close();
}
