import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/mobile_api_client.dart';
import 'package:procurepilot_mobile/core/api/models.dart';

void main() {
  const apiBaseUrl = 'https://api.procurepilot.test/api/v1';

  group('MobileApiClient', () {
    test('POST /devices sends idempotency key and parses response, never an apikey header', () async {
      final client = MockClient((request) async {
        expect(
          request.url.toString(),
          '$apiBaseUrl/devices',
        );
        expect(request.headers.containsKey('apikey'), isFalse,
            reason: 'apikey is a Supabase-gateway header; apps/api does not expect it');
        expect(request.headers['Idempotency-Key'], 'idem-1');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['platform'], 'android');
        expect(body['push_token'], 'token-1');
        return http.Response(
          jsonEncode({
            'id': 'd1',
            'member_id': 'm1',
            'platform': 'android',
            'push_token': 'token-1',
            'last_seen_at': '2026-09-12T10:00:00Z',
          }),
          200,
        );
      });
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      final device = await api.registerDevice(
        platform: DevicePlatform.android,
        pushToken: 'token-1',
        idempotencyKey: 'idem-1',
      );

      expect(device.id, 'd1');
      expect(device.platform, DevicePlatform.android);
    });

    test('sends the bearer token when set', () async {
      final client = MockClient((request) async {
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response('', 204);
      });
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client)
        ..accessToken = 'test-token';

      await api.deleteDevice('d1');
    });

    test('DELETE /devices/{id} calls the correct path', () async {
      final client = MockClient((request) async {
        expect(request.method, 'DELETE');
        expect(
          request.url.toString(),
          '$apiBaseUrl/devices/d1',
        );
        return http.Response('', 204);
      });
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      await api.deleteDevice('d1');
    });

    test('POST /low-stock-reports sends decimal count as string', () async {
      final client = MockClient((request) async {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['branch_id'], 'b1');
        expect(body['workspace_product_id'], 'p1');
        expect(body['count_remaining'], '12.50');
        expect(request.headers['Idempotency-Key'], 'idem-2');
        return http.Response(
          jsonEncode({
            'id': 'r1',
            'branch_id': 'b1',
            'member_id': 'm1',
            'workspace_product_id': 'p1',
            'count_remaining': '12.50',
            'created_at': '2026-09-12T10:00:00Z',
          }),
          201,
        );
      });
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      final report = await api.createLowStockReport(
        branchId: 'b1',
        workspaceProductId: 'p1',
        countRemaining: '12.50',
        idempotencyKey: 'idem-2',
      );

      expect(report.id, 'r1');
      expect(report.countRemaining, '12.50');
    });

    test('GET /low-stock-reports parses cursor list', () async {
      final client = MockClient((request) async {
        expect(request.url.toString(), startsWith('$apiBaseUrl/low-stock-reports'));
        expect(request.url.queryParameters['limit'], '10');
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'r1',
                'branch_id': 'b1',
                'member_id': 'm1',
                'workspace_product_id': 'p1',
                'count_remaining': '5',
                'created_at': '2026-09-12T10:00:00Z',
              },
            ],
            'next_cursor': 'cursor-1',
          }),
          200,
        );
      });
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      final list = await api.listLowStockReports(limit: 10);

      expect(list.items.length, 1);
      expect(list.items.first.workspaceProductId, 'p1');
      expect(list.nextCursor, 'cursor-1');
    });

    test('error response throws ApiException with envelope fields', () async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode({
            'code': 'not_found',
            'message': 'No such branch',
            'trace_id': 'trace-1',
          }),
          404,
        ),
      );
      final api = MobileApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      expect(
        () => api.deleteDevice('missing'),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'not_found'),
        ),
      );
    });
  });
}
