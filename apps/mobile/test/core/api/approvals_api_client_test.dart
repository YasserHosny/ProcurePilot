import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:procurepilot_mobile/core/api/approvals_api_client.dart';
import 'package:procurepilot_mobile/core/api/models.dart';

import '../../features/approvals/split_approval_fixtures.dart';

void main() {
  const apiBaseUrl = 'https://api.procurepilot.test/api/v1';

  test('pending approvals parse a split request with no budget', () {
    final item = splitApprovalRequests().first.toJson();
    item['budget_status'] = {
      'remaining_amount': null,
      'exceeds': false,
      'status': 'no_budget',
      'reason_code': 'no_budget_at_cost_centre_level',
    };

    final result = PendingApprovalsList.fromJson({
      'items': [item],
      'next_cursor': null,
    });

    expect(result.items, hasLength(1));
    expect(result.items.single.requestGroup!.id, splitGroupId);
    final budget = result.items.single.budgetStatus!;
    expect(budget.remainingAmount, isNull);
    expect(budget.status, 'no_budget');
    expect(budget.reasonCode, 'no_budget_at_cost_centre_level');
    expect(budget.toJson(), {
      'exceeds': false,
      'status': 'no_budget',
      'reason_code': 'no_budget_at_cost_centre_level',
    });
  });

  test('budget status retains money with optional metadata absent', () {
    final json = {
      'remaining_amount': {'amount': '40.00', 'currency': 'USD'},
      'exceeds': true,
    };
    final budget = BudgetStatus.fromJson(json);
    expect(budget.remainingAmount!.toJson(), json['remaining_amount']);
    expect(budget.exceeds, isTrue);
    expect(budget.status, isNull);
    expect(budget.reasonCode, isNull);
    expect(budget.toJson(), json);
    expect(const BudgetStatus(remainingAmount: null, exceeds: false).toJson(), {
      'exceeds': false,
    });
  });

  test(
    'pending approvals retain split money, siblings and supplier context',
    () async {
      final requests = splitApprovalRequests();
      final client = ApprovalsApiClient(
        apiBaseUrl: apiBaseUrl,
        httpClient: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/api/v1/approvals/pending');
          return http.Response.bytes(
            utf8.encode(
              jsonEncode({
                'items': requests.map((r) => r.toJson()).toList(),
                'next_cursor': 'next-page',
              }),
            ),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final result = await client.listPendingApprovals();
      expect(result.nextCursor, 'next-page');
      expect(result.items, hasLength(2));
      final group = result.items.first.requestGroup!;
      expect(group.id, splitGroupId);
      expect(group.rfqId, 'rfq-1234-5678');
      expect(group.position, 1);
      expect(group.size, 2);
      expect(group.combinedTotal.toJson(), {
        'amount': '4063.00',
        'currency': 'SAR',
      });
      expect(group.bestSingleTotal!.toJson(), {
        'amount': '4137.00',
        'currency': 'SAR',
      });
      expect(group.saving!.toJson(), {'amount': '74.00', 'currency': 'SAR'});
      expect(group.siblingRequestIds, ['split-req-2']);
      expect(result.items.first.source!.supplierName, 'الذهبي');
    },
  );

  test(
    'ungrouped and nullable split fields parse without inventing savings',
    () {
      final json = splitApprovalRequests().first.toJson();
      final groupJson = json['request_group'] as Map<String, dynamic>;
      groupJson.remove('best_single_total');
      groupJson.remove('saving');
      final request = PurchaseRequest.fromJson(json);
      expect(request.requestGroup!.bestSingleTotal, isNull);
      expect(request.requestGroup!.saving, isNull);
      expect(
        PurchaseRequest.fromJson(request.toJson()).requestGroup!.saving,
        isNull,
      );

      json['request_group'] = null;
      json['source'] = null;
      expect(PurchaseRequest.fromJson(json).requestGroup, isNull);
      expect(PurchaseRequest.fromJson(json).source, isNull);
      json.remove('request_group');
      expect(PurchaseRequest.fromJson(json).requestGroup, isNull);
    },
  );

  for (final action in ['approve', 'reject']) {
    test(
      '$action sends one group mutation with a trimmed comment and UUID key',
      () async {
        final calls = <http.Request>[];
        final client = ApprovalsApiClient(
          apiBaseUrl: apiBaseUrl,
          httpClient: MockClient((request) async {
            calls.add(request);
            expect(request.method, 'POST');
            expect(
              request.url.toString(),
              '$apiBaseUrl/request-groups/$splitGroupId/$action',
            );
            expect(request.headers['Content-Type'], 'application/json');
            expect(request.headers['Authorization'], 'Bearer test-token');
            expect(
              request.headers['Idempotency-Key'],
              matches(
                r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
              ),
            );
            expect(jsonDecode(request.body), {'comment': 'Decision reason'});
            return http.Response.bytes(
              utf8.encode(
                jsonEncode(
                  splitApprovalRequests().map((r) => r.toJson()).toList(),
                ),
              ),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }),
        )..accessToken = 'test-token';

        final result = action == 'approve'
            ? await client.approveGroup(
                splitGroupId,
                comment: '  Decision reason  ',
              )
            : await client.rejectGroup(
                splitGroupId,
                comment: '  Decision reason  ',
              );
        expect(calls, hasLength(1));
        expect(result.map((r) => r.id), ['split-req-1', 'split-req-2']);
        expect(result.every((r) => r.requestGroup!.id == splitGroupId), isTrue);
      },
    );

    for (final status in [403, 409]) {
      test('$action preserves the $status error envelope', () async {
        final client = ApprovalsApiClient(
          apiBaseUrl: apiBaseUrl,
          httpClient: MockClient(
            (_) async => http.Response(
              jsonEncode({
                'code': status == 403 ? 'forbidden' : 'conflict',
                'message': 'Decision refused',
                'details': {
                  'reason': status == 403 ? 'not_assigned' : 'not_submitted',
                },
                'trace_id': 'trace-group',
              }),
              status,
            ),
          ),
        );
        await expectLater(
          action == 'approve'
              ? client.approveGroup(splitGroupId)
              : client.rejectGroup(splitGroupId, comment: 'Reason'),
          throwsA(
            isA<ApiException>()
                .having((e) => e.statusCode, 'statusCode', status)
                .having(
                  (e) => e.details?['reason'],
                  'reason',
                  status == 403 ? 'not_assigned' : 'not_submitted',
                )
                .having((e) => e.traceId, 'traceId', 'trace-group'),
          ),
        );
      });
    }
  }
}
