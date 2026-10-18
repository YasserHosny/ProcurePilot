import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';
import 'package:procurepilot_mobile/core/api/session_http_client.dart';
import 'package:procurepilot_mobile/core/auth/auth_service.dart';

import '../../test_helpers.dart';

void main() {
  late AuthService auth;
  late FakeStorage storage;
  late int refreshes;
  late int refreshStatus;
  late SessionHttpClient transport;
  late List<http.Request> sent;
  late MobileApiClient mobile;
  late ApprovalsApiClient approvals;
  late RequestsApiClient requests;
  setUp(() async {
    storage = FakeStorage()
      ..values['access_token'] = 'old'
      ..values['refresh_token'] = 'refresh';
    refreshes = 0;
    refreshStatus = 200;
    sent = [];
    auth = AuthService(
      storage: storage,
      httpClient: MockClient((_) async {
        refreshes++;
        return http.Response(
          jsonEncode({'access_token': 'new', 'refresh_token': 'rotated'}),
          refreshStatus,
        );
      }),
      supabaseUrl: 'https://auth.test',
      supabaseAnonKey: 'test-key',
    );
    await auth.loadStoredSession();
    transport = SessionHttpClient(
      inner: MockClient((request) async {
        sent.add(request);
        final ok = request.headers['Authorization'] == 'Bearer new';
        return http.Response(ok ? '{"items":[]}' : '{}', ok ? 200 : 401);
      }),
      authService: auth,
      apiBaseUrl: 'https://api.test/api/v1',
    );
    mobile = MobileApiClient(
      apiBaseUrl: 'https://api.test/api/v1',
      httpClient: transport,
    );
    approvals = ApprovalsApiClient(
      apiBaseUrl: 'https://api.test/api/v1',
      httpClient: transport,
    );
    requests = RequestsApiClient(
      apiBaseUrl: 'https://api.test/api/v1',
      httpClient: transport,
    );
  });
  test('each API client retries a 401 with the renewed token', () async {
    final calls = <Future<void> Function()>[
      () async {
        await mobile.listLowStockReports();
      },
      () async {
        await approvals.listPendingApprovals();
      },
      () async {
        await requests.listRequests();
      },
    ];
    for (final call in calls) {
      auth.accessToken = 'old';
      sent.clear();
      await call();
      expect(sent.map((r) => r.headers['Authorization']), [
        'Bearer old',
        'Bearer new',
      ]);
    }
    expect(refreshes, 3);
    expect(storage.values['refresh_token'], 'rotated');
  });
  test('parallel 401s share one refresh', () async {
    await Future.wait([
      mobile.listLowStockReports(),
      approvals.listPendingApprovals(),
      requests.listRequests(),
    ]);
    expect(refreshes, 1);
    expect(
      sent.where((r) => r.headers['Authorization'] == 'Bearer new'),
      hasLength(3),
    );
  });
  test('late 401 uses the rotated token without refreshing again', () async {
    final lateResponse = Completer<http.Response>();
    final lateStarted = Completer<void>();
    transport = SessionHttpClient(
      inner: MockClient((request) async {
        sent.add(request);
        if (request.url.path.endsWith('/late') &&
            request.headers['Authorization'] == 'Bearer old') {
          lateStarted.complete();
          return lateResponse.future;
        }
        final ok = request.headers['Authorization'] == 'Bearer new';
        return http.Response('{}', ok ? 200 : 401);
      }),
      authService: auth,
      apiBaseUrl: 'https://api.test/api/v1',
    );
    final late = transport.get(Uri.parse('https://api.test/api/v1/late'));
    await lateStarted.future;
    expect(
      (await transport.get(Uri.parse('https://api.test/api/v1/first')))
          .statusCode,
      200,
    );
    lateResponse.complete(http.Response('{}', 401));
    expect((await late).statusCode, 200);
    expect(refreshes, 1);
    expect(sent, hasLength(4));
  });

  test('refresh failure signs out and clears persisted tokens', () async {
    refreshStatus = 400;
    await expectLater(
      mobile.listLowStockReports(),
      throwsA(isA<AuthException>()),
    );
    expect(refreshes, 1);
    expect(sent, hasLength(1));
    expect(auth.sessionExpired, isTrue);
    expect(auth.accessToken, isNull);
    expect(auth.refreshToken, isNull);
    expect(storage.values, isEmpty);
  });
  test('second 401 signs out without retry loop', () async {
    transport = SessionHttpClient(
      inner: MockClient((request) async {
        sent.add(request);
        return http.Response('{}', 401);
      }),
      authService: auth,
      apiBaseUrl: 'https://api.test/api/v1',
    );
    final response = await transport.get(
      Uri.parse('https://api.test/api/v1/requests'),
    );
    expect(response.statusCode, 401);
    expect(sent, hasLength(2));
    expect(refreshes, 1);
    expect(auth.sessionExpired, isTrue);
  });
  test(
    'multipart retry preserves body, boundary and idempotency key',
    () async {
      final request =
          http.MultipartRequest(
              'POST',
              Uri.parse('https://api.test/api/v1/photos'),
            )
            ..headers['Idempotency-Key'] = 'same-key'
            ..files.add(
              http.MultipartFile.fromString(
                'file',
                'photo-bytes',
                filename: 'photo.jpg',
              ),
            );
      final response = await transport.send(request);
      await response.stream.drain<void>();
      expect(sent, hasLength(2));
      expect(sent[1].bodyBytes, sent[0].bodyBytes);
      expect(sent[1].headers['content-type'], sent[0].headers['content-type']);
      expect(sent[1].headers['Idempotency-Key'], 'same-key');
    },
  );
  test(
    'non API and lookalike paths do not refresh or receive a token',
    () async {
      for (final url in [
        'https://other.test/api/v1/requests',
        'https://api.test/api/v10/requests',
      ]) {
        final response = await transport.get(Uri.parse(url));
        expect(response.statusCode, 401);
        expect(sent.last.headers['Authorization'], isNull);
      }
      expect(refreshes, 0);
      expect(auth.accessToken, 'old');
    },
  );
  test(
    'a refresh in flight cannot restore an explicitly signed-out session',
    () async {
      final response = Completer<http.Response>();
      auth = AuthService(
        storage: storage,
        httpClient: MockClient((_) => response.future),
        supabaseUrl: 'https://auth.test',
        supabaseAnonKey: 'test-key',
      );
      await auth.loadStoredSession();
      final refreshing = auth.refreshSession();
      await auth.signOut();
      response.complete(
        http.Response('{"access_token":"new","refresh_token":"rotated"}', 200),
      );
      await expectLater(refreshing, throwsA(isA<AuthException>()));
      expect(auth.accessToken, isNull);
      expect(storage.values, isEmpty);
    },
  );
}
