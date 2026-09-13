import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/models.dart';
import 'package:procurepilot_mobile/core/api/requests_api_client.dart';

void main() {
  const apiBaseUrl = 'https://api.procurepilot.test/api/v1';

  group('RequestsApiClient - Quality Issues', () {
    test('reportQualityIssue POSTs to /requests/{id}/quality-issues and parses QualityIssue', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.toString(), '$apiBaseUrl/requests/req-123/quality-issues');
        expect(request.headers['Content-Type'], 'application/json');
        expect(request.headers['Authorization'], 'Bearer test-token');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['description'], 'Damaged packaging');

        return http.Response(
          jsonEncode({
            'id': 'qi-uuid-1',
            'purchase_request_id': 'req-123',
            'reported_by_membership_id': 'member-uuid-1',
            'description': 'Damaged packaging',
            'photos': [],
            'created_at': '2026-09-13T12:00:00Z',
          }),
          201,
        );
      });

      final apiClient = RequestsApiClient(apiBaseUrl: apiBaseUrl, httpClient: client)
        ..accessToken = 'test-token';

      final issue = await apiClient.reportQualityIssue('req-123', 'Damaged packaging');

      expect(issue.id, 'qi-uuid-1');
      expect(issue.purchaseRequestId, 'req-123');
      expect(issue.reportedByMembershipId, 'member-uuid-1');
      expect(issue.description, 'Damaged packaging');
      expect(issue.photos, isEmpty);
      expect(issue.createdAt, DateTime.parse('2026-09-13T12:00:00Z'));
    });

    test('reportQualityIssue throws ApiException on 409 not_delivered', () async {
      final client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'code': 'conflict',
            'message': 'Request is not delivered',
            'details': {'reason': 'not_delivered'},
            'trace_id': 'trace-123',
          }),
          409,
        );
      });

      final apiClient = RequestsApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);

      expect(
        () => apiClient.reportQualityIssue('req-not-delivered', 'Broken'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'statusCode', 409)
              .having((e) => e.details?['reason'], 'reason', 'not_delivered'),
        ),
      );
    });

    test('uploadQualityIssuePhoto sends multipart POST to /quality-issues/{id}/photos', () async {
      final tempDir = await Directory.systemTemp.createTemp('upload_test');
      final testFile = File('${tempDir.path}/test_image.jpg');
      await testFile.writeAsBytes([1, 2, 3, 4, 5]);

      try {
        final client = MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.toString(), '$apiBaseUrl/quality-issues/issue-456/photos');
          expect(request.headers['Authorization'], 'Bearer upload-token');
          expect(
            request.headers['content-type']?.startsWith('multipart/form-data'),
            isTrue,
          );

          return http.Response(
            jsonEncode({
              'id': 'photo-uuid-1',
              'delivery_quality_issue_id': 'issue-456',
              'url': 'https://signed.storage.url/photo1.jpg',
              'created_at': '2026-09-13T12:05:00Z',
            }),
            201,
          );
        });

        final apiClient = RequestsApiClient(apiBaseUrl: apiBaseUrl, httpClient: client)
          ..accessToken = 'upload-token';

        final photo = await apiClient.uploadQualityIssuePhoto('issue-456', testFile.path);

        expect(photo.id, 'photo-uuid-1');
        expect(photo.deliveryQualityIssueId, 'issue-456');
        expect(photo.url, 'https://signed.storage.url/photo1.jpg');
        expect(photo.createdAt, DateTime.parse('2026-09-13T12:05:00Z'));
      } finally {
        await tempDir.delete(recursive: true);
      }
    });

    test('listQualityIssues GETs /requests/{id}/quality-issues and parses QualityIssueList', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.toString(), '$apiBaseUrl/requests/req-789/quality-issues');
        return http.Response(
          jsonEncode({
            'items': [
              {
                'id': 'qi-1',
                'purchase_request_id': 'req-789',
                'reported_by_membership_id': 'm-1',
                'description': 'Item broken',
                'photos': [
                  {
                    'id': 'p-1',
                    'delivery_quality_issue_id': 'qi-1',
                    'url': 'https://url/p1.jpg',
                    'created_at': '2026-09-13T12:00:00Z',
                  }
                ],
                'created_at': '2026-09-13T12:00:00Z',
              }
            ],
          }),
          200,
        );
      });

      final apiClient = RequestsApiClient(apiBaseUrl: apiBaseUrl, httpClient: client);
      final list = await apiClient.listQualityIssues('req-789');

      expect(list.items, hasLength(1));
      expect(list.items.first.description, 'Item broken');
      expect(list.items.first.photos, hasLength(1));
      expect(list.items.first.photos.first.url, 'https://url/p1.jpg');
    });
  });
}
